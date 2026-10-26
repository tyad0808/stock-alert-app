"""시세 확인 1회: 시세 조회 → 원칙 엔진 → 알림 필터 → 기록.

서버에서는 장중 10~30분마다 이 파일을 실행한다:  python -m app.checker
"""

from . import config
from .alerts import held_level, is_outlier, newly_entered_zone
from .db import DB, now_kst
from .providers import get_provider
from .providers.base import PriceProvider
from .rules import Bar, drawdown_pct, high_52w, tier, zone_level

DATA_CHECK = "data_check"


def _trusted_prev_close(bars: list[Bar]) -> float:
    """어제 종가. 어제 값이 오류 데이터였다면 그 전 정상 값을 쓴다."""
    i = len(bars) - 2
    while i > 0 and is_outlier(bars[i].close, bars[i - 1].close):
        i -= 1
    return bars[i].close


def quote(stock: dict, bars: list[Bar]) -> dict:
    """종목 하나의 지금 상태: 현재가, 1년 고점, 고점 대비 하락률, 구간. 알림과는 상관없이 계산만 한다."""
    today = bars[-1]
    price = today.close
    prev_close = _trusted_prev_close(bars)
    high = high_52w(bars)
    dd = drawdown_pct(price, high)
    warn = is_outlier(price, prev_close)
    level = None if warn else zone_level(dd)
    return {
        "symbol": stock["symbol"], "name": stock["name"], "date": today.date,
        "price": price, "prev_close": prev_close,
        "change_pct": round((price / prev_close - 1) * 100, 2) if prev_close > 0 else 0,
        "high": high, "drawdown": round(dd, 2),
        "new_high": price >= high,
        "level": level, "tier": tier(level),
        "data_warning": warn,
    }


def check_stock(db: DB, stock: dict, bars: list[Bar]) -> dict | None:
    """종목 하나를 확인한다. 새 알림이 생기면 그 알림을 돌려준다."""
    if len(bars) < 2:
        return None
    q = quote(stock, bars)
    symbol, name, day = q["symbol"], q["name"], q["date"]

    if q["data_warning"]:
        # 구간 기록은 그대로 두고 "확인 필요"만 알린다
        if db.alert_exists(symbol, DATA_CHECK, None, day):
            return None
        return db.add_alert(
            market_date=day, kind=DATA_CHECK, symbol=symbol, name=name,
            level=None, price=q["price"], high=None, drawdown=None,
            message=f"하루 {q['change_pct']:+.1f}% 변동 — 데이터 확인 필요 (알림 판단에서 제외)",
        )

    prev_level = db.get_level(symbol)
    level = held_level(prev_level, q["drawdown"])
    entered = newly_entered_zone(prev_level, level)
    db.set_level(symbol, level)
    if entered is None:
        return None

    kind = tier(entered)["key"]
    if db.alert_exists(symbol, kind, entered, day):
        return None
    return db.add_alert(
        market_date=day, kind=kind, symbol=symbol, name=name,
        level=entered, price=q["price"], high=q["high"], drawdown=q["drawdown"],
        message=f"1년 고점 대비 -{entered}% 진입 · 현재가 ${q['price']:,.2f} / 1년 고점 ${q['high']:,.2f}",
    )


def run_check(db: DB, provider: PriceProvider | None = None) -> list[dict]:
    provider = provider or get_provider(db)
    new_alerts = []
    for stock in config.load_watchlist():
        alert = check_stock(db, stock, provider.daily_bars(stock["symbol"]))
        if alert:
            new_alerts.append(alert)
    db.set_meta("last_check", now_kst())
    return new_alerts


if __name__ == "__main__":
    database = DB(config.DATA_DIR / "app.db")
    for a in run_check(database):
        print(f"[알림] {a['name']} {a['message']}")
    print("확인 완료")
