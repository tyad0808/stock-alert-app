"""앱 서버. 폰 앱(web/)에 화면을 보내고, 화면이 쓰는 데이터를 API로 준다."""

import hashlib
import hmac
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .checker import quote, run_check
from .db import DB, now_kst
from .providers import get_provider
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
        run_check(db)
    yield


app = FastAPI(title="주식 알림 앱", lifespan=lifespan)


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in OPEN_PATHS and not _logged_in(request):
        return JSONResponse({"detail": "로그인이 필요합니다"}, status_code=401)
    return await call_next(request)


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
    }


def _quotes(provider) -> list[dict]:
    return [quote(st, provider.daily_bars(st["symbol"])) for st in config.load_watchlist()]


@app.get("/api/board")
def board():
    """시세판: Top 10 전체의 현재가와 1년 고점 대비. 알림과 상관없이 열 때마다 새로 계산한다."""
    return {"stocks": _quotes(get_provider(db)), "updated": now_kst()}


@app.get("/api/stock/{symbol}")
def stock(symbol: str):
    item = next((s for s in config.load_watchlist() if s["symbol"] == symbol), None)
    if item is None:
        raise HTTPException(404, "감시 목록에 없는 종목입니다")
    bars = get_provider(db).daily_bars(symbol)
    q = quote(item, bars)
    deepest = max(q["level"] or 0, 50) + config.ZONE_STEP
    zones = [{"level": lv, "price": round(zone_price(q["high"], lv), 2), "tier": tier(lv)}
             for lv in range(config.ZONE_START, deepest + 1, config.ZONE_STEP)]
    return {
        **q,
        "series": [{"date": b.date, "close": b.close} for b in bars[-config.WINDOW_DAYS:]],
        "zones": zones,
        "alerts": db.alerts(symbol=symbol, limit=50),
    }


@app.get("/api/alerts")
def alerts():
    return {"alerts": db.alerts()}


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
