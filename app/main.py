"""앱 서버. 폰 앱(web/)에 화면을 보내고, 화면이 쓰는 데이터를 API로 준다."""

import hashlib
import hmac
import secrets
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, universe
from .checker import holding_quote, quote, run_check, split_for
from .db import DB, now_kst
from .providers import get_provider
from .providers.kiwoom import KiwoomError
from .rules import tier, zone_price

db = DB(config.DATA_DIR / "app.db")

# 로그인 유지용 값. APP_SECRET이 없으면 서버를 켤 때마다 새로 만든다 (다시 로그인 필요)
_secret = (config.APP_SECRET or secrets.token_hex(32)).encode()
SESSION_COOKIE = "session"
OPEN_PATHS = {"/api/login", "/api/status"}


def _session_token() -> str:
    return hmac.new(_secret, config.APP_PASSWORD.encode(), hashlib.sha256).hexdigest()


def _logged_in(request: Request) -> bool:
    if not config.APP_PASSWORD:
        return True
    return hmac.compare_digest(request.cookies.get(SESSION_COOKIE, ""), _session_token())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if db.get_meta("last_check") is None:
        try:
            run_check(db)
        except KiwoomError as e:
            # 키움이 잠깐 안 돼도 앱은 켜져 있어야 한다. 15분마다 도는 시세 확인이 다시 시도한다
            print(f"첫 시세 확인 실패: {e}")
    if not get_provider(db).is_practice:
        threading.Thread(target=_keep_warm, daemon=True).start()
    yield


WARM_EVERY = 60  # 초 (기억 시간 50초보다 길게 → 매번 새로 받음)


def _keep_warm():
    """실제 시세일 때, 화면을 열자마자 바로 보이도록 1분마다 미리 받아 둔다."""
    while True:
        try:
            provider = get_provider(db)
            symbols = [s["symbol"] for s in universe.everything(db)]
            symbols += [h["symbol"] for h in provider.holdings() if h["symbol"] not in symbols]
            for symbol in symbols:
                provider.daily_bars(symbol)
            provider.fx_rate()
        except Exception as e:  # noqa: BLE001 — 잠깐 실패해도 다음 회차에 다시 받는다
            print(f"시세 미리 받기 실패: {e}")
        time.sleep(WARM_EVERY)


app = FastAPI(title="주식 알림 앱", lifespan=lifespan)


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in OPEN_PATHS and not _logged_in(request):
        return JSONResponse({"detail": "로그인이 필요합니다"}, status_code=401)
    return await call_next(request)


@app.exception_handler(KiwoomError)
async def kiwoom_error(_request: Request, exc: KiwoomError):
    return JSONResponse({"detail": f"키움 시세를 가져오지 못했습니다. 잠시 뒤 다시 열어 주세요. ({exc})"},
                        status_code=503)


class LoginBody(BaseModel):
    password: str


@app.post("/api/login")
def login(body: LoginBody):
    if not config.APP_PASSWORD or not hmac.compare_digest(body.password, config.APP_PASSWORD):
        raise HTTPException(401, "비밀번호가 맞지 않습니다")
    res = JSONResponse({"ok": True})
    res.set_cookie(SESSION_COOKIE, _session_token(), httponly=True, samesite="strict",
                   max_age=60 * 60 * 24 * 30)
    return res


@app.post("/api/logout")
def logout():
    res = JSONResponse({"ok": True})
    res.delete_cookie(SESSION_COOKIE)
    return res


@app.get("/api/status")
def status(request: Request):
    provider = get_provider(db)
    return {
        "logged_in": _logged_in(request),
        "login_required": bool(config.APP_PASSWORD),
        "data_source": provider.name,
        "is_practice": provider.is_practice,
        "can_advance": getattr(provider, "can_advance", False),
        "last_check": db.get_meta("last_check"),
        "tiers": [{"start": st, "key": k, "label": lb} for st, k, lb in config.TIERS],
        "zone_step": config.ZONE_STEP,
        "hysteresis": config.HYSTERESIS,
        "profit_step": config.PROFIT_STEP,
        "loss_step": config.LOSS_STEP,
        "etfs": [e["symbol"] for e in universe.etfs(db)],
        "top10_updated": db.get_meta("universe_date"),
        "keep_days": config.KEEP_DAYS,
    }


def _board(items: list[dict]) -> list[dict]:
    provider = get_provider(db)
    held = {h["symbol"] for h in provider.holdings()}
    return [{**quote(st, provider.daily_bars(st["symbol"])), "held": st["symbol"] in held} for st in items]


@app.get("/api/board")
def board():
    """시세판: Top 10 전체의 현재가와 1년 고점 대비. 알림과 상관없이 열 때마다 새로 계산한다."""
    return {"stocks": _board(universe.stocks(db)), "updated": now_kst(), "note": universe.note(db)}


@app.get("/api/etf")
def etf_board():
    """ETF 시세판: 정해 둔 ETF. 알림 기준은 주식과 같다."""
    return {"stocks": _board(universe.etfs(db)), "updated": now_kst()}


@app.get("/api/holdings")
def holdings():
    """내 종목: 평단 대비 수익률과 평가금액. 계좌에서 조회만 한다."""
    provider = get_provider(db)
    fx = provider.fx_rate()
    top10 = {s["symbol"] for s in universe.everything(db)}
    rows = [{**holding_quote(h, provider.daily_bars(h["symbol"])), "in_top10": h["symbol"] in top10}
            for h in provider.holdings()]
    value = sum(r["value_usd"] for r in rows)
    cost = sum(r["cost_usd"] for r in rows)
    prev = sum(r["prev_close"] * r["qty"] for r in rows)
    return {
        "holdings": sorted(rows, key=lambda r: -r["value_usd"]),
        "total": {
            "value_usd": round(value, 2), "cost_usd": round(cost, 2),
            "profit_usd": round(value - cost, 2),
            "return_pct": round((value / cost - 1) * 100, 2) if cost else 0,
            "day_change_pct": round((value / prev - 1) * 100, 2) if prev else 0,
            "value_krw": round(value * fx) if fx else None,
        },
        "fx": fx,
        "updated": now_kst(),
    }


@app.get("/api/stock/{symbol}")
def stock(symbol: str):
    provider = get_provider(db)
    top10 = universe.find(db, symbol)
    held = next((h for h in provider.holdings() if h["symbol"] == symbol), None)
    if top10 is None and held is None:
        raise HTTPException(404, "감시 목록이나 내 종목에 없는 종목입니다")
    bars = provider.daily_bars(symbol)
    q = quote(top10 or held, bars)
    deepest = max(q["level"] or 0, 50) + config.ZONE_STEP
    zones = [{"level": lv, "price": round(zone_price(q["high"], lv), 2), "tier": tier(lv)}
             for lv in range(config.ZONE_START, deepest + 1, config.ZONE_STEP)]
    holding = None
    if held:
        holding = holding_quote(held, bars)
        top = max(holding["pl_level"] or 0, 0) + 2 * config.PROFIT_STEP
        avg = held["avg_price"]
        holding["pl_prices"] = (
            [{"level": lv, "price": round(avg * (1 + lv / 100), 2)}
             for lv in range(config.PROFIT_STEP, top + 1, config.PROFIT_STEP)]
            + [{"level": -lv, "price": round(avg * (1 - lv / 100), 2)}
               for lv in range(config.LOSS_STEP, 80, config.LOSS_STEP)]
        )
    return {
        **q,
        "in_top10": top10 is not None,
        "series": [{"date": b.date, "close": b.close} for b in bars[-config.WINDOW_DAYS:]],
        "zones": zones,
        "holding": holding,
        "split": split_for(db, symbol, q["price"], provider.fx_rate(), held),
        "fx": provider.fx_rate(),
        "alerts": db.alerts(symbol=symbol, limit=50),
    }


class SplitBody(BaseModel):
    total_krw: int = Field(ge=0, le=10_000_000_000)


@app.post("/api/split/{symbol}")
def set_split(symbol: str, body: SplitBody):
    """3분할 총 투자금 저장 (0이면 삭제). 주문과는 무관한 메모다."""
    provider = get_provider(db)
    held = next((h for h in provider.holdings() if h["symbol"] == symbol), None)
    if held is None and universe.find(db, symbol) is None:
        raise HTTPException(404, "감시 목록이나 내 종목에 없는 종목입니다")
    db.set_split_total(symbol, body.total_krw)
    bars = provider.daily_bars(symbol)
    return {"split": split_for(db, symbol, bars[-1].close, provider.fx_rate(), held)}


@app.get("/api/briefing")
def briefing(date: str | None = None):
    """아침 브리핑. 날짜가 없으면 가장 최근 것, 지난 날짜 목록도 함께 준다."""
    return {"briefing": db.briefing(date), "dates": db.briefing_dates()}


@app.post("/api/briefing")
def make_briefing():
    """브리핑을 지금 새로 만든다 (설정 화면의 '지금 만들기')."""
    from .briefing.build import run

    return {"briefing": run(db, force=True), "dates": db.briefing_dates()}


class PushSub(BaseModel):
    endpoint: str = Field(pattern=r"^https://", max_length=1000)
    keys: dict[str, str]


@app.get("/api/push/key")
def push_key():
    from . import push

    return {"key": push.public_key(), "count": len(db.push_subs())}


@app.post("/api/push/subscribe")
def push_subscribe(sub: PushSub):
    """이 폰에 매일 9시 브리핑 알림을 받는다."""
    db.add_push_sub(sub.model_dump())
    return {"ok": True}


class PushEndpoint(BaseModel):
    endpoint: str


@app.post("/api/push/unsubscribe")
def push_unsubscribe(body: PushEndpoint):
    db.remove_push_sub(body.endpoint)
    return {"ok": True}


@app.post("/api/push/test")
def push_test():
    from . import push

    return push.send_all(db, "시험 알림", "알림이 잘 옵니다 👍")


def _alert_group(a: dict, etf_syms: set[str]) -> str:
    """알림 탭 구분: 내 종목(수익·손실) / ETF / 주식."""
    if a["kind"] in ("profit", "loss"):
        return "mine"
    return "etf" if a["symbol"] in etf_syms else "stock"


@app.get("/api/alerts")
def alerts():
    etf_syms = {e["symbol"] for e in universe.etfs(db)}
    return {"alerts": [{**a, "group": _alert_group(a, etf_syms)} for a in db.alerts()],
            "keep_days": config.KEEP_DAYS}


@app.post("/api/check")
def check_now():
    return {"new_alerts": run_check(db)}


class AdvanceBody(BaseModel):
    days: int = 1


def _require_practice():
    if not get_provider(db).is_practice:
        raise HTTPException(400, "연습용 데이터에서만 쓸 수 있습니다")


@app.post("/api/practice/advance")
def practice_advance(body: AdvanceBody):
    """연습용: 하루씩 앞으로 가면서 알림이 어떻게 오는지 본다."""
    _require_practice()
    new_alerts = []
    for _ in range(max(1, min(body.days, 60))):
        provider = get_provider(db)
        if not provider.can_advance:
            break
        db.set_meta("practice_offset", str(provider.offset + 1))
        new_alerts += run_check(db)
    return {"new_alerts": new_alerts, "can_advance": get_provider(db).can_advance}


@app.post("/api/practice/reset")
def practice_reset():
    _require_practice()
    db.reset()
    return {"new_alerts": run_check(db)}


WEB = config.ROOT / "web"


@app.get("/sw.js")
def service_worker():
    # 서비스워커는 최상위 주소에서 내려줘야 앱 전체를 관리할 수 있다
    return FileResponse(WEB / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
