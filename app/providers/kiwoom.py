"""키움 REST API 시세 공급원. 조회 전용이다.

부를 수 있는 키움 기능은 READ_ONLY_APIS 의 세 가지(+로그인 토큰)뿐이다.
주문·환전 신청 같은 기능은 목록에 없어서, 코드 어디에서 불러도 _call 이 막는다.

서버에서 연결 점검:  python -m app.providers.kiwoom
"""

import json
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
}

# 거래소 코드: ND 나스닥, NY 뉴욕, NA 아멕스
EXCHANGES = ("ND", "NY", "NA")
EXCHANGE_NAMES = {"나스닥": "ND", "NASDAQ": "ND", "뉴욕": "NY", "NYSE": "NY", "아멕스": "NA", "AMEX": "NA"}

MIN_BARS = config.WINDOW_DAYS + 5  # 1년 고점 계산에 필요한 만큼
MAX_PAGES = 4
REQUEST_GAP = 0.25  # 초당 4회 이하로 부른다

# 화면이 1분마다 새로 고쳐도 키움을 매번 부르지 않도록 잠깐 기억해 둔다 (서버 프로세스마다 따로)
BARS_TTL = 60
HOLDINGS_TTL = 60
FX_TTL = 600

_cache: dict[str, tuple[float, object]] = {}
_exchange_of: dict[str, str] = {}
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


def _cached(key: str, ttl: float, make):
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
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
        for attempt in range(2):
            headers = {
                "api-id": api_id, "authorization": f"Bearer {self._token(refresh=attempt > 0)}",
                "cont-yn": "Y" if next_key else "N", "next-key": next_key,
            }
            data, res_headers = self._post(READ_ONLY_APIS[api_id], body, headers)
            code = data.get("return_code", 0)
            if code in (0, "0"):
                lower = {k.lower(): v for k, v in res_headers.items()}
                more = lower.get("cont-yn") == "Y"
                return data, (lower.get("next-key", "") if more else "")
            # 토큰이 만료됐으면 한 번만 새로 받아서 다시 시도
            if attempt == 0 and "토큰" in str(data.get("return_msg", "")):
                continue
            raise KiwoomError(f"키움 조회 실패 ({api_id}): {data.get('return_msg') or code}")
        raise KiwoomError(f"키움 조회 실패 ({api_id})")

    # ---- 시세 ----

    def _chart(self, symbol: str, exchange: str) -> list[Bar]:
        rows, next_key = [], ""
        today = datetime.now(KST).strftime("%Y%m%d")
        for _ in range(MAX_PAGES):
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

    def _exchange_candidates(self, symbol: str) -> list[str]:
        known = _exchange_of.get(symbol) or next(
            (s.get("exchange") for s in config.load_watchlist() if s["symbol"] == symbol), None)
        return [known] + [e for e in EXCHANGES if e != known] if known else list(EXCHANGES)

    def daily_bars(self, symbol: str) -> list[Bar]:
        def load():
            for exchange in self._exchange_candidates(symbol):
                bars = self._chart(symbol, exchange)
                if len(bars) >= 2:
                    _exchange_of[symbol] = exchange
                    return bars
            raise KiwoomError(f"{symbol} 시세를 찾지 못했습니다 (거래소 코드 확인 필요)")
        return _cached(f"bars:{symbol}", BARS_TTL, load)

    # ---- 계좌 ----

    def holdings(self) -> list[dict]:
        def load():
            data, _ = self._call("ust21070", {"stex_tp": "%", "stk_cd": ""})
            result = []
            for r in data.get("result_list") or []:
                symbol = str(r.get("stk_cd", "")).strip()
                qty = _num(r.get("qty"))
                if not symbol or qty <= 0 or r.get("crnc_code", "USD") != "USD":
                    continue
                exchange = EXCHANGE_NAMES.get(str(r.get("stex_nm", "")).strip().upper()) \
                    or EXCHANGE_NAMES.get(str(r.get("stex_nm", "")).strip())
                if exchange:
                    _exchange_of.setdefault(symbol, exchange)
                result.append({
                    "symbol": symbol,
                    "name": str(r.get("frgn_stk_nm") or symbol).strip(),
                    "qty": qty,
                    "avg_price": round(_num(r.get("frgn_stk_book_uv")), 4),
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
        p = KiwoomProvider()
    except KiwoomError as e:
        print(f"✖ {e}")
        raise SystemExit(1)

    step("로그인(토큰)", lambda: "성공" if p._token() else "실패")
    step("환율", lambda: f"{p.fx_rate()}원")
    step("보유 종목", lambda: ", ".join(
        f"{h['symbol']} {h['qty']:g}주 평단 ${h['avg_price']:,.2f}" for h in p.holdings()) or "없음")
    for st in config.load_watchlist():
        step(f"{st['symbol']} 시세", lambda st=st: (lambda b: (
            f"{len(b)}일치 {b[0].date}~{b[-1].date}, 최근 종가 ${b[-1].close:,.2f}, "
            f"1년 고점 ${max(x.high for x in b[-config.WINDOW_DAYS:]):,.2f} ({_exchange_of.get(st['symbol'])})"
        ))(p.daily_bars(st["symbol"])))
    print("\n점검 완료: 모두 정상" if ok else "\n점검 완료: ✖ 표시된 항목을 확인하세요")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    _diagnose()
