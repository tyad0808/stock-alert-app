"""시세 확인 1회: 시세 조회 → 원칙 엔진 → 알림 필터 → 기록.

서버에서는 장중 10~30분마다 이 파일을 실행한다:  python -m app.checker
"""

from . import config
from .alerts import is_outlier, newly_entered_zone
from .db import DB, now_kst
from .providers import get_provider
from .providers.base import PriceProvider
from .rules import Bar, drawdown_pct, high_52w, next_zone, zone_level, zone_price

BUY_REVIEW = "buy_review"
DATA_CHECK = "data_check"


def _trusted_prev_close(bars: list[Bar]) -> float:
    """어제 종가. 어제 값이 오류 데이터였다면 그 전 정상 값을 쓴다."""
    i = len(bars) - 2
    while i > 0 and is_outlier(bars[i].close, bars[i - 1].close):
        i -= 1
    return bars[i].close


def check_stock(db: DB, stock: dict, bars: list[Bar]) -> dict | None:
    """종목 하나를 확인한다. 새 알림이 생기면 그 알림을 돌려준다."""
    symbol, name = stock["symbol"], stock["name"]
    if len(bars) < 2:
        return None
    today = bars[-1]
    price = today.close
    prev_close = _trusted_prev_close(bars)

    if is_outlier(price, prev_close):
        change = (price / prev_close - 1) * 100 if prev_close > 0 else 0
        # 이전 정상 값은 그대로 두고 "확인 필요" 표시만 붙인다
        db.save_snapshot(symbol, {
            **(db.get_snapshot(symbol) or {}),
            "symbol": symbol, "name": name, "data_warning": True, "date": today.date,
        })
        if db.alert_exists(symbol, DATA_CHECK, None, today.date):
            return None
        return db.add_alert(
            market_date=today.date, kind=DATA_CHECK, symbol=symbol, name=name,
            level=None, price=price, high=None, drawdown=None,
            message=f"하루 {change:+.1f}% 변동 — 데이터 확인 필요 (알림 판단에서 제외)",
        )

    high = high_52w(bars)
    dd = drawdown_pct(price, high)
    level = zone_level(dd)
    prev_level = db.get_level(symbol)
    entered = newly_entered_zone(prev_level, level)
    db.set_level(symbol, level)

    nxt = next_zone(level)
    db.save_snapshot(symbol, {
        "symbol": symbol, "name": name, "date": today.date,
        "price": price, "prev_close": prev_close,
        "change_pct": round((price / prev_close - 1) * 100, 2),
        "high": high, "drawdown": round(dd, 2), "level": level,
        "next_level": nxt, "next_price": round(zone_price(high, nxt), 2),
        "data_warning": False,
    })

    if entered is None or db.alert_exists(symbol, BUY_REVIEW, entered, today.date):
        return None
    return db.add_alert(
        market_date=today.date, kind=BUY_REVIEW, symbol=symbol, name=name,
        level=entered, price=price, high=high, drawdown=round(dd, 2),
        message=f"1년 고점 대비 -{entered}% 진입 · 현재가 ${price:,.2f} / 1년 고점 ${high:,.2f}",
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
