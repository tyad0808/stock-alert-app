"""알림 필터: 언제 알릴지, 언제 막을지 정한다."""

from . import config
from .rules import zone_level


def held_level(prev_level: int | None, drawdown: float) -> int | None:
    """경계선 여유를 둔 현재 구간 (알림 판단용 기록).

    더 깊어지면 바로 새 구간으로 본다. 회복할 때는 기준보다 2%p 더 올라와야 벗어난 것으로 본다.
    예: -35% 구간에 있다가 -33.5%로 회복 → 아직 35구간 / -32.9%까지 회복 → 30구간
    """
    now = zone_level(drawdown)
    if prev_level is None or (now is not None and now >= prev_level):
        return now
    # 딱 2%p 회복한 경우도 벗어난 것으로 보도록 아주 작은 값을 더한다
    held = zone_level(drawdown - config.HYSTERESIS + 1e-6)
    return None if held is None else min(prev_level, held)


def newly_entered_zone(prev_level: int | None, new_level: int | None) -> int | None:
    """이번에 새로 들어간 구간 중 가장 깊은 것. 새로 들어간 구간이 없으면 None.

    - 더 깊은 구간으로 내려갔을 때만 알린다. (-30 → -35: 35구간 알림)
    - 한 번에 여러 구간을 내려가면 가장 깊은 1개만 알린다. (-28 → -41: 40구간 1번)
    - 회복해서 구간을 벗어나면 기록만 바꾸고, 다시 내려오면 또 알린다.
    """
    if new_level is None:
        return None
    if prev_level is None or new_level > prev_level:
        return new_level
    return None


def is_outlier(price: float, prev_close: float) -> bool:
    """하루에 50% 이상 움직이거나 가격이 0 이하면 데이터 오류로 본다."""
    if price <= 0 or prev_close <= 0:
        return True
    return abs(price / prev_close - 1) >= config.OUTLIER_DAILY_CHANGE
