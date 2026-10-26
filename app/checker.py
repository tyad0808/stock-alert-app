"""시세 확인 1회: 시세 조회 → 원칙 엔진 → 알림 필터 → 기록.

서버에서는 장중 10~30분마다 이 파일을 실행한다:  python -m app.checker
"""

from . import config
from .alerts import held_level, held_pl_level, is_outlier, newly_entered_pl, newly_entered_zone
from .db import DB, now_kst
from .providers import get_provider
from .providers.base import PriceProvider
from .rules import Bar, drawdown_pct, high_52w, pl_level, return_pct, split_plan, tier, zone_level

DATA_CHECK = "data_check"
PROFIT = "profit"
LOSS = "loss"


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


def holding_quote(h: dict, bars: list[Bar]) -> dict:
    """내 종목 하나의 지금 상태: 평단 대비 수익률, 평가금액, 수익·손실 구간."""
    q = quote(h, bars)
    ret = return_pct(q["price"], h["avg_price"])
    return {
        **q,
        "qty": h["qty"], "avg_price": h["avg_price"],
        "return_pct": round(ret, 2),
        "value_usd": round(q["price"] * h["qty"], 2),
        "cost_usd": round(h["avg_price"] * h["qty"], 2),
        "pl_level": None if q["data_warning"] else pl_level(ret),
    }


def split_for(db: DB, symbol: str, price: float, fx: float | None, holding: dict | None) -> dict | None:
    """그 종목의 3분할 계획. 총 투자금을 넣은 적이 없거나 환율을 모르면 None."""
    total = db.get_split_total(symbol)
    if not total or not fx:
        return None
    invested = holding["qty"] * holding["avg_price"] * fx if holding else 0
    return {**split_plan(total, invested, price * fx), "fx": fx}


def _data_check_alert(db: DB, q: dict) -> dict | None:
    if db.alert_exists(q["symbol"], DATA_CHECK, None, q["date"]):
        return None
    return db.add_alert(
        market_date=q["date"], kind=DATA_CHECK, symbol=q["symbol"], name=q["name"],
        level=None, price=q["price"], high=None, drawdown=None,
        message=f"하루 {q['change_pct']:+.1f}% 변동 — 데이터 확인 필요 (알림 판단에서 제외)",
    )


def check_stock(db: DB, stock: dict, bars: list[Bar], split: dict | None = None) -> dict | None:
    """Top 10 종목 하나를 확인한다. 새 알림이 생기면 그 알림을 돌려준다."""
    if len(bars) < 2:
        return None
    q = quote(stock, bars)
    if q["data_warning"]:
        # 구간 기록은 그대로 두고 "확인 필요"만 알린다
        return _data_check_alert(db, q)

    symbol = q["symbol"]
    prev_level = db.get_level(symbol)
    level = held_level(prev_level, q["drawdown"])
    entered = newly_entered_zone(prev_level, level)
    db.set_level(symbol, level)
    if entered is None:
        return None

    kind = tier(entered)["key"]
    if db.alert_exists(symbol, kind, entered, q["date"]):
        return None
    message = f"1년 고점 대비 -{entered}% 진입 · 현재가 ${q['price']:,.2f} / 1년 고점 ${q['high']:,.2f}"
    if split and split["next"]:
        message += f" · 다음 분할 {split['next']['n']}차 {split['next']['amount']:,}원"
    return db.add_alert(
        market_date=q["date"], kind=kind, symbol=symbol, name=q["name"],
        level=entered, price=q["price"], high=q["high"], drawdown=q["drawdown"], message=message,
    )


def check_holding(db: DB, h: dict, bars: list[Bar]) -> dict | None:
    """내 종목 하나를 확인한다: 평단 대비 수익 +10%마다, 손실 -20%마다."""
    if len(bars) < 2:
        return None
    q = holding_quote(h, bars)
    if q["data_warning"]:
        return _data_check_alert(db, q)

    symbol = q["symbol"]
    state = db.get_holding_state(symbol)
    if state and abs(state["avg_price"] - h["avg_price"]) > 0.005:
        # 추가 매수 등으로 평단이 바뀌면 새 평단 기준으로 다시 시작한다 (바뀐 순간에는 알리지 않음)
        db.set_holding_state(symbol, q["pl_level"], h["avg_price"])
        return None
    prev_level = state["level"] if state else None
    level = held_pl_level(prev_level, q["return_pct"])
    entered = newly_entered_pl(prev_level, level)
    db.set_holding_state(symbol, level, h["avg_price"])
    if entered is None:
        return None

    kind = PROFIT if entered > 0 else LOSS
    if db.alert_exists(symbol, kind, entered, q["date"]):
        return None
    return db.add_alert(
        market_date=q["date"], kind=kind, symbol=symbol, name=q["name"],
        level=entered, price=q["price"], high=None, drawdown=None,
        message=f"평단 대비 {entered:+d}% 진입 · 현재가 ${q['price']:,.2f} / 평단 ${h['avg_price']:,.2f} / 보유 {h['qty']:g}주",
    )


def run_check(db: DB, provider: PriceProvider | None = None) -> list[dict]:
    provider = provider or get_provider(db)
    holdings = provider.holdings()
    held = {h["symbol"]: h for h in holdings}
    fx = provider.fx_rate()
    new_alerts = []
    for stock in config.load_watchlist():
        bars = provider.daily_bars(stock["symbol"])
        split = split_for(db, stock["symbol"], bars[-1].close, fx, held.get(stock["symbol"])) if bars else None
        alert = check_stock(db, stock, bars, split)
        if alert:
            new_alerts.append(alert)
    for h in holdings:
        alert = check_holding(db, h, provider.daily_bars(h["symbol"]))
        if alert:
            new_alerts.append(alert)
    db.set_meta("last_check", now_kst())
    return new_alerts


if __name__ == "__main__":
    database = DB(config.DATA_DIR / "app.db")
    for a in run_check(database):
        print(f"[알림] {a['name']} {a['message']}")
    print("확인 완료")
