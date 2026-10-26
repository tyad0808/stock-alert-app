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
    start: int = config.BUY_ZONE_START,
    step: int = config.BUY_ZONE_STEP,
) -> int | None:
    """하락률이 들어가 있는 가장 깊은 구간. -30% 미만으로 안 빠졌으면 None.

    예: -29.9 → None, -30.0 → 30, -37.2 → 35, -50.0 → 50
    """
    fall = round(-drawdown, 6)  # 부동소수점 오차로 -35%가 34.9999%가 되는 것 방지
    if fall < start:
        return None
    return start + step * math.floor((fall - start) / step)


def zone_price(high: float, level: int) -> float:
    """해당 구간에 들어가는 가격. 예: 고점 $200, 35구간 → $130"""
    return high * (1 - level / 100)


def next_zone(level: int | None, step: int = config.BUY_ZONE_STEP) -> int:
    """다음으로 알림이 울릴 구간."""
    return config.BUY_ZONE_START if level is None else level + step
