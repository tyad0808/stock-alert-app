"""원칙 엔진: 가격만 보고 1년 고점 대비 하락률과 알림 구간을 계산한다."""

import math
from dataclasses import dataclass

from . import config


@dataclass(frozen=True)
class Bar:
    """하루치 시세. high는 그날 장중 최고가."""

    date: str
    close: float
    high: float


def high_52w(bars: list[Bar]) -> float:
    """최근 1년(252 거래일) 장중 최고가."""
    return max(b.high for b in bars[-config.WINDOW_DAYS:])


def drawdown_pct(price: float, high: float) -> float:
    """1년 고점 대비 하락률(%). 고점보다 낮으면 음수. 예: -35.0"""
    return (price / high - 1) * 100


def zone_level(
    drawdown: float,
    start: int = config.ZONE_START,
    step: int = config.ZONE_STEP,
) -> int | None:
    """하락률이 들어가 있는 가장 깊은 구간. -5% 미만으로 안 빠졌으면 None.

    예: -4.9 → None, -5.0 → 5, -37.2 → 35, -50.0 → 50
    """
    fall = round(-drawdown, 6)  # 부동소수점 오차로 -35%가 34.9999%가 되는 것 방지
    if fall < start:
        return None
    return start + step * math.floor((fall - start) / step)


def tier(level: int | None) -> dict | None:
    """구간이 속한 단계. 예: 10 → 매수검토, 20 → 매수권장"""
    if level is None:
        return None
    for start, key, label in config.TIERS:
        if level >= start:
            return {"key": key, "label": label}
    return None


def zone_price(high: float, level: int) -> float:
    """해당 구간에 들어가는 가격. 예: 고점 $200, 35구간 → $130"""
    return high * (1 - level / 100)


def return_pct(price: float, avg_price: float) -> float:
    """평단 대비 수익률(%). 예: 평단 $100, 현재가 $115 → +15.0"""
    return (price / avg_price - 1) * 100


def pl_level(ret: float) -> int | None:
    """내 종목 알림 구간. 수익이면 양수, 손실이면 음수, 둘 다 아니면 None.

    예: +9.9 → None, +10 → 10, +27 → 20, -19.9 → None, -20 → -20, -45 → -40
    """
    r = round(ret, 6)
    if r >= config.PROFIT_STEP:
        return config.PROFIT_STEP * math.floor(r / config.PROFIT_STEP)
    if r <= -config.LOSS_STEP:
        return -config.LOSS_STEP * math.floor(-r / config.LOSS_STEP)
    return None


def split_plan(total_krw: int, invested_krw: float, price_krw: float) -> dict:
    """3분할(30/30/40) 계획. 지금까지 산 금액으로 몇 차까지 샀는지 표시한다.

    한 차수 금액의 95% 이상 샀으면 그 차수는 산 것으로 본다 (환율·주수 단위 오차 감안).
    """
    parts, cum = [], 0
    for n, ratio in enumerate(config.SPLIT_RATIOS, start=1):
        amount = round(total_krw * ratio / 100)
        cum += amount
        parts.append({
            "n": n, "ratio": ratio, "amount": amount,
            "shares": round(amount / price_krw, 1) if price_krw > 0 else None,
            "done": invested_krw >= cum - amount * 0.05,
        })
    nxt = next((p for p in parts if not p["done"]), None)
    return {
        "total": total_krw, "parts": parts,
        "invested": round(invested_krw), "remaining": max(0, round(total_krw - invested_krw)),
        "next": nxt,
    }
