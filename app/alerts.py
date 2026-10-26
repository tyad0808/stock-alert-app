"""알림 필터: 언제 알릴지, 언제 막을지 정한다."""

from . import config


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
