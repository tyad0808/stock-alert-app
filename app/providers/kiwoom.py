"""키움 REST API 시세 공급원. 조회 전용이다.

부를 수 있는 키움 기능은 READ_ONLY_APIS 의 조회 기능(+로그인 토큰)뿐이다.
주문·환전 신청 같은 기능은 목록에 없어서, 코드 어디에서 불러도 _call 이 막는다.

서버에서 연결 점검:  python -m app.providers.kiwoom
"""

import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

from .. import config
from ..db import KST
from ..rules import Bar
from .base import PriceProvider

BASE_URL = "https://api.kiwoom.com"
TOKEN_PATH = "/oauth2/token"

# api-id → 주소. 전부 조회 기능이다.
READ_ONLY_APIS = {
    "usa06012": "/api/us/chart",     # 미국주식 일 차트
    "ust21070": "/api/us/acnt",      # 미국주식 원장잔고확인 (보유 종목·평단)
    "ust31301": "/api/us/exchange",  # 환율 조회
    "usa10099": "/api/us/stkinfo",   # 미국주식 종목리스트 (BRK.B 처럼 표기가 다른 종목의 코드 찾기)
    "usa20550": "/api/us/rkinfo",    # 미국주식 시가총액 상위 (주식 Top 10 자동 갱신)
}

# 거래소 코드: ND 나스닥, NY 뉴욕, NA 아멕스
EXCHANGES = ("ND", "NY", "NA")
# 순위 응답의 거래소 표기 → 위 코드 (표기가 여러 가지라 넉넉히)
RANK_EXCHANGES = {"ND": "ND", "NAS": "ND", "NASDAQ": "ND", "2": "ND", "NY": "NY", "NYS": "NY", "NYSE": "NY", "1": "NY",
                  "NA": "NA", "AMS": "NA", "AMEX": "NA", "3": "NA"}

MIN_BARS = config.WINDOW_DAYS + 5  # 1년 고점 계산에 필요한 만큼
MAX_PAGES = 4
REQUEST_GAP = 0.25  # 초당 4회 이하로 부른다

# 화면이 1분마다 새로 고쳐도 키움을 매번 부르지 않도록 잠깐 기억해 둔다 (서버 프로세스마다 따로)
BARS_TTL = 50
FULL_TTL = 6 * 3600
HOLDINGS_TTL = 50
FX_TTL = 600

_cache: dict[str, tuple[float, object]] = {}
_exchange_of: dict[str, str] = {}  # 종목 → "키움 종목코드|거래소" (찾은 뒤 기억)
_lock = threading.Lock()
_last_call = 0.0


class KiwoomError(RuntimeError):
    pass


def _num(s) -> float:
    """키움 숫자 문자열을 숫자로. 가격 앞의 +/- 는 전일 대비 방향 표시라서 뗀다."""
    if s is None:
        return 0.0
    s = str(s).strip().replace(",", "").lstrip("+-")
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


_refreshing: set[str] = set()


def _cached(key: str, ttl: float, make):
    """기억해 둔 값을 바로 돌려준다. 오래됐으면 일단 그 값을 주고 뒤에서 새로 받아 둔다 (화면이 기다리지 않게)."""
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    if hit:
        if key not in _refreshing:
            _refreshing.add(key)

            def refresh():
                try:
                    _cache[key] = (time.monotonic(), make())
                except Exception:  # noqa: BLE001 — 다음 요청 때 다시 시도한다
                    pass
                finally:
                    _refreshing.discard(key)

            threading.Thread(target=refresh, daemon=True).start()
        return hit[1]
    value = make()
    _cache[key] = (time.monotonic(), value)
    return value


class KiwoomProvider(PriceProvider):
    name = "키움증권"
    is_practice = False

    def __init__(self, db=None, app_key: str | None = None, app_secret: str | None = None):
        self.db = db
        self.app_key = (app_key if app_key is not None else config.KIWOOM_APP_KEY).strip()
        self.app_secret = (app_secret if app_secret is not None else config.KIWOOM_APP_SECRET).strip()
        if not self.app_key or not self.app_secret:
            raise KiwoomError("키움 키가 설정되지 않았습니다 (.env 의 KIWOOM_APP_KEY, KIWOOM_APP_SECRET)")

    # ---- 통신 ----

    def _post(self, path: str, body: dict, headers: dict) -> tuple[dict, dict]:
        global _last_call
        with _lock:
            wait = _last_call + REQUEST_GAP - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last_call = time.monotonic()
        req = urllib.request.Request(
            BASE_URL + path, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json;charset=UTF-8", **headers},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                return json.loads(res.read().decode() or "{}"), dict(res.headers)
        except urllib.error.HTTPError as e:
            try:
                data = json.loads(e.read().decode() or "{}")
            except ValueError:
                data = {}
            raise KiwoomError(f"키움 응답 오류 {e.code}: {data.get('return_msg') or e.reason}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise KiwoomError(f"키움 서버에 연결할 수 없습니다: {e}") from None

    def _token(self, refresh: bool = False) -> str:
        if not refresh:
            hit = _cache.get("token")
            if hit and hit[0] > time.time():
                return hit[1]
            if self.db is not None:
                saved = self.db.get_meta("kiwoom_token")
                if saved:
                    token, exp = saved.split("|", 1)
                    if float(exp) > time.time():
                        _cache["token"] = (float(exp), token)
                        return token
        data, _ = self._post(TOKEN_PATH, {
            "grant_type": "client_credentials", "appkey": self.app_key, "secretkey": self.app_secret,
        }, {})
        token = data.get("token")
        if not token:
            raise KiwoomError(f"키움 로그인 실패: {data.get('return_msg') or '토큰을 받지 못했습니다'}")
        try:
            exp = datetime.strptime(data["expires_dt"], "%Y%m%d%H%M%S").replace(tzinfo=KST).timestamp()
        except (KeyError, ValueError):
            exp = time.time() + 6 * 3600
        exp -= 600  # 만료 10분 전에 새로 받는다
        _cache["token"] = (exp, token)
        if self.db is not None:
            self.db.set_meta("kiwoom_token", f"{token}|{exp}")
        return token

    def _call(self, api_id: str, body: dict, next_key: str = "") -> tuple[dict, str]:
        """조회 기능 하나를 부른다. 돌려주는 값: (응답, 다음 페이지 키)."""
        if api_id not in READ_ONLY_APIS:
            raise KiwoomError(f"허용되지 않은 키움 기능입니다: {api_id} (조회 전용)")
        token = self._token()
        for attempt in range(2):
            headers = {
                "api-id": api_id, "authorization": f"Bearer {token}",
                "cont-yn": "Y" if next_key else "N", "next-key": next_key,
            }
            data, res_headers = self._post(READ_ONLY_APIS[api_id], body, headers)
            code = data.get("return_code", 0)
            if code in (0, "0"):
                lower = {k.lower(): v for k, v in res_headers.items()}
                more = lower.get("cont-yn") == "Y"
                return data, (lower.get("next-key", "") if more else "")
            # 토큰이 만료·무효(8005)면 한 번만 새로 받아서 다시 시도.
            # 키움은 새 토큰을 받으면 옛 토큰을 끊으므로, 다른 작업(시세 확인·브리핑)이 이미
            # 새로 받아 둔 토큰이 있으면 그것부터 쓴다
            if attempt == 0 and _token_error(code, data.get("return_msg")):
                _cache.pop("token", None)
                fresh = self._token()
                token = fresh if fresh != token else self._token(refresh=True)
                continue
            raise KiwoomError(f"키움 조회 실패 ({api_id}): {data.get('return_msg') or code}")
        raise KiwoomError(f"키움 조회 실패 ({api_id})")

    # ---- 시세 ----

    def _chart(self, symbol: str, exchange: str, pages: int = MAX_PAGES) -> list[Bar]:
        rows, next_key = [], ""
        today = datetime.now(KST).strftime("%Y%m%d")
        for _ in range(pages):
            data, next_key = self._call("usa06012", {
                "stex_tp": exchange, "stk_cd": symbol, "strt_dt": today,
                "upd_stkpc_tp": "1", "exrt_appl_tp": "0",
            }, next_key)
            rows += data.get("result_list") or []
            if len(rows) >= MIN_BARS or not next_key:
                break
        bars = {}
        for r in rows:
            dt, close = str(r.get("dt", "")), _num(r.get("cur_prc"))
            if len(dt) != 8 or close <= 0:
                continue
            day = f"{dt[:4]}-{dt[4:6]}-{dt[6:]}"
            bars[day] = Bar(date=day, close=close, high=max(_num(r.get("high_pric")), close))
        return [bars[d] for d in sorted(bars)]

    def _listing_candidates(self, symbol: str) -> list[tuple[str, str]]:
        """(키움 종목코드, 거래소) 시도 순서. 한 번 찾으면 기억해 둔다."""
        saved = _exchange_of.get(symbol)
        if saved is None and self.db is not None:
            saved = self.db.get_meta(f"kiwoom_listing:{symbol}")
        first = [tuple(saved.split("|", 1))] if saved and "|" in saved else []
        from .. import universe

        known = (universe.find(self.db, symbol) or {}).get("exchange")
        exchanges = [known] + [e for e in EXCHANGES if e != known] if known else list(EXCHANGES)
        # BRK.B 처럼 점이 들어간 종목은 증권사마다 적는 법이 다르다
        codes = [symbol]
        if "." in symbol:
            codes += [symbol.replace(".", c) for c in ("/", " ", "-", "")]
        rest = [(c, e) for c in codes for e in exchanges]
        return first + [x for x in rest if x not in first]

    def _find_listing(self, symbol: str) -> tuple[str, str] | None:
        """키움 종목 목록에서 점·빗금 같은 기호를 빼고 같은 코드를 찾는다. 예: BRK.B → BRKB"""
        want = re.sub(r"[^A-Z0-9]", "", symbol.upper())
        for exchange in dict.fromkeys(e for _, e in self._listing_candidates(symbol)):
            next_key = ""
            for _ in range(30):
                data, next_key = self._call("usa10099", {"stex_tp": exchange}, next_key)
                for item in data.get("list") or []:
                    code = str(item.get("stk_cd", "")).strip()
                    if re.sub(r"[^A-Z0-9]", "", code.upper()) == want:
                        return code, exchange
                if not next_key:
                    break
        return None

    def daily_bars(self, symbol: str) -> list[Bar]:
        def load():
            # 1년치 전체는 몇 시간에 한 번만 받고, 그사이에는 최근 한 쪽만 받아 이어 붙인다
            full = _cache.get(f"full:{symbol}")
            listing = _exchange_of.get(symbol, "")
            if full and "|" in listing and time.monotonic() - full[0] < FULL_TTL:
                try:
                    recent = self._chart(*listing.split("|", 1), pages=1)
                except KiwoomError:
                    recent = []
                if recent:
                    merged = {b.date: b for b in full[1]}
                    merged.update({b.date: b for b in recent})
                    return [merged[d] for d in sorted(merged)]
            bars = load_full()
            _cache[f"full:{symbol}"] = (time.monotonic(), bars)
            return bars

        def load_full():
            last_error = None
            for code, exchange in self._listing_candidates(symbol):
                try:
                    bars = self._chart(code, exchange)
                except KiwoomError as e:
                    last_error = e
                    continue
                if len(bars) >= 2:
                    found = f"{code}|{exchange}"
                    if _exchange_of.get(symbol) != found:
                        _exchange_of[symbol] = found
                        if self.db is not None:
                            self.db.set_meta(f"kiwoom_listing:{symbol}", found)
                    return bars
            # 그래도 없으면 키움 종목 목록에서 같은 종목을 찾아 그 코드로 부른다
            listing = self._find_listing(symbol)
            if listing:
                bars = self._chart(*listing)
                if len(bars) >= 2:
                    found = "|".join(listing)
                    _exchange_of[symbol] = found
                    if self.db is not None:
                        self.db.set_meta(f"kiwoom_listing:{symbol}", found)
                    return bars
            raise KiwoomError(f"{symbol} 시세를 찾지 못했습니다 ({last_error or '종목코드·거래소 확인 필요'})")
        return _cached(f"bars:{symbol}", BARS_TTL, load)

    # ---- 순위 ----

    def rankings(self, kind: str) -> list[dict]:
        """주식 시가총액 상위. [{symbol, name, exchange}] 순위순."""
        body = {"stex_tp": "0", "inds_cd": "", "stk_tp": "1", "trde_qty_tp": "0", "stk_cnd": "0",
                "pric_cnd": "0", "trde_prica_cnd": "0"}
        data, _ = self._call("usa20550", body)
        rows = sorted(data.get("result_list") or [], key=lambda r: _num(r.get("rank")) or 9999)
        result = []
        for r in rows:
            code = str(r.get("stk_cd", "")).strip()
            if not code:
                continue
            # 키움은 종류주를 BRKb 처럼 적는다 → BRK.B
            m = re.fullmatch(r"([A-Z]+)([a-z])", code)
            symbol = f"{m[1]}.{m[2].upper()}" if m else code
            exchange = RANK_EXCHANGES.get(str(r.get("stex_tp", "")).strip().upper())
            if exchange:
                _exchange_of.setdefault(symbol, f"{code}|{exchange}")
            result.append({"symbol": symbol, "name": str(r.get("stk_nm") or symbol).strip(),
                           **({"exchange": exchange} if exchange else {})})
        return result

    # ---- 계좌 ----

    # 잔고 조회 요청 방식. 문서와 실제가 달라서, 되는 방식을 차례로 시도하고 기억한다
    BALANCE_BODIES = (
        {"stex_tp": "", "stk_cd": ""},
        {},
        {"stex_tp": "%", "stk_cd": "%"},
    )

    def _balance_rows(self) -> list[dict]:
        saved = self.db.get_meta("kiwoom_balance_body") if self.db is not None else None
        order = list(range(len(self.BALANCE_BODIES)))
        if saved is not None and saved.isdigit() and int(saved) < len(order):
            order.remove(int(saved))
            order.insert(0, int(saved))
        last_error = None
        for i in order:
            try:
                data, next_key = self._call("ust21070", self.BALANCE_BODIES[i])
            except KiwoomError as e:
                last_error = e
                continue
            if self.db is not None and saved != str(i):
                self.db.set_meta("kiwoom_balance_body", str(i))
            _cache["balance_body"] = (0, i)
            return _unique_rows(self._balance_pages(self.BALANCE_BODIES[i], data, next_key))
        # 전체 조회가 안 되면 감시 목록 종목만 하나씩 확인한다 (Top 10 밖 종목은 빠질 수 있음)
        rows = []
        from .. import universe

        for st in universe.everything(self.db):
            try:
                data, _ = self._call("ust21070", {"stex_tp": st.get("exchange", "ND"), "stk_cd": st["symbol"]})
            except KiwoomError:
                continue
            rows += data.get("result_list") or []
        if not rows and last_error:
            raise last_error
        _cache["balance_body"] = (0, "종목별")
        return rows

    def _balance_pages(self, body: dict, data: dict, next_key: str) -> list[dict]:
        """잔고 첫 페이지 + 다음 페이지들 (보유 종목이 많을 때)."""
        rows = list(data.get("result_list") or [])
        for _ in range(5):
            if not next_key:
                break
            data, next_key = self._call("ust21070", body, next_key)
            rows += data.get("result_list") or []
        return rows

    def holdings(self) -> list[dict]:
        def load():
            result = []
            for r in self._balance_rows():
                # 키움이 BRK/B 처럼 적어도 감시 목록과 같은 BRK.B 로 맞춘다
                symbol = re.sub(r"[/ ]", ".", str(r.get("stk_cd", "")).strip())
                # qty 는 결제가 끝난 수량이라 어제 산 종목은 0 으로 온다 (미국 주식은 다음 날 결제).
                # 영웅문처럼 결제 전 수량까지 보려면 poss_qty(보유·매도 가능 수량)를 함께 본다
                qty = max(_num(r.get("qty")), _num(r.get("poss_qty")))
                avg = _num(r.get("frgn_stk_book_uv"))
                if not symbol or qty <= 0 or avg <= 0 or (r.get("crnc_code") or "USD") != "USD":
                    continue
                result.append({
                    "symbol": symbol,
                    "name": str(r.get("frgn_stk_nm") or symbol).strip(),
                    "qty": qty,
                    "avg_price": round(avg, 4),
                })
            return result
        return [dict(h) for h in _cached("holdings", HOLDINGS_TTL, load)]

    def fx_rate(self) -> float | None:
        def load():
            data, _ = self._call("ust31301", {"exch_tp": "1"})
            # 우대 적용 전 환율(매매기준율에 가까움)을 먼저, 없으면 적용 환율
            for key in ("spcl_bf_exrt", "aplc_exrt", "buy_aplc_exrt"):
                rate = _num(data.get(key))
                if rate > 0:
                    return rate
            return None
        return _cached("fx", FX_TTL, load)


def _token_error(code, msg) -> bool:
    return str(code) == "8005" or bool(re.search(r"토큰|token|인증", str(msg or ""), re.I))


def _unique_rows(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        key = str(r.get("stk_cd", "")).strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _shared_db():
    """점검도 앱과 같은 토큰을 쓴다 (새 토큰을 받으면 앱이 쓰던 토큰이 끊기기 때문)."""
    from ..db import DB

    return DB(config.DATA_DIR / "app.db")


def _diagnose_balance() -> None:
    """잔고 조회를 요청 방식별로 나눠 보여준다 (빠진 종목 찾기용). 키는 찍지 않는다."""
    p = KiwoomProvider(db=_shared_db())
    for body in KiwoomProvider.BALANCE_BODIES:
        try:
            data, nxt = p._call("ust21070", body)
        except KiwoomError as e:
            print(f"✖ {body}: {e}")
            continue
        rows = data.get("result_list") or []
        print(f"✔ {body}: {len(rows)}종목{' (다음 페이지 있음)' if nxt else ''}")
        for r in rows:
            qty = {k: v for k, v in r.items() if "qty" in k or k.endswith("_uv") or k in ("crnc_code", "stex_tp", "stex_nm")}
            print(f"    {r.get('stk_cd')} {qty}")


def _diagnose() -> None:
    """서버에서 키움 연결을 점검한다. 키는 화면에 찍지 않는다."""
    ok = True

    def step(title, fn):
        nonlocal ok
        try:
            print(f"✔ {title}: {fn()}")
        except Exception as e:  # noqa: BLE001 — 점검용이라 모든 오류를 그대로 보여준다
            ok = False
            print(f"✖ {title}: {e}")

    try:
        p = KiwoomProvider(db=_shared_db())
    except KiwoomError as e:
        print(f"✖ {e}")
        raise SystemExit(1)

    step("로그인(토큰)", lambda: "성공" if p._token() else "실패")
    step("환율", lambda: f"{p.fx_rate()}원")
    step("보유 종목", lambda: (", ".join(
        f"{h['symbol']} {h['qty']:g}주 평단 ${h['avg_price']:,.2f}" for h in p.holdings()) or "없음")
        + f" (요청 방식 {_cache.get('balance_body', (0, '?'))[1]})")
    from .. import universe

    step("주식 시가총액 순위", lambda: ", ".join(r["symbol"] for r in p.rankings("stocks")[:12]))
    for st in universe.everything():
        step(f"{st['symbol']} 시세", lambda st=st: (lambda b: (
            f"{len(b)}일치 {b[0].date}~{b[-1].date}, 최근 종가 ${b[-1].close:,.2f}, "
            f"1년 고점 ${max(x.high for x in b[-config.WINDOW_DAYS:]):,.2f} ({_exchange_of.get(st['symbol'], '')})"
        ))(p.daily_bars(st["symbol"])))
    print("\n점검 완료: 모두 정상" if ok else "\n점검 완료: ✖ 표시된 항목을 확인하세요")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    import sys

    _diagnose_balance() if "--balance" in sys.argv else _diagnose()
