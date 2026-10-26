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
