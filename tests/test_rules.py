"""원칙 엔진과 알림 필터가 기획서 4장 규칙대로 움직이는지 확인한다."""

import pytest

from app.alerts import is_outlier, newly_entered_zone
from app.rules import Bar, drawdown_pct, high_52w, next_zone, zone_level, zone_price


@pytest.mark.parametrize("dd, level", [
    (-10, None), (-20, None), (-29.99, None),
    (-30, 30), (-34.9, 30), (-35, 35), (-37.2, 35),
    (-50, 50), (-55, 55), (-72, 70),
])
def test_zone_level(dd, level):
    assert zone_level(dd) == level


def test_zone_level_float_error():
    # $200 고점에서 $130이면 정확히 -35% 구간
    assert zone_level(drawdown_pct(130, 200)) == 35


def test_zone_prices_match_plan_table():
    # 기획서 4장 표: 1년 고점 $200일 때
    assert [zone_price(200, lv) for lv in (30, 35, 40, 45, 50, 55)] == \
        pytest.approx([140, 130, 120, 110, 100, 90])


def test_next_zone():
    assert next_zone(None) == 30
    assert next_zone(35) == 40


def test_high_52w_uses_last_year_only():
    old = [Bar("old", 999, 999)]
    year = [Bar(str(i), 100, 100 + i % 10) for i in range(252)]
    assert high_52w(old + year) == 109


@pytest.mark.parametrize("prev, new, entered", [
    (None, None, None),
    (None, 30, 30),   # 처음 -30% 진입
    (30, 30, None),   # 같은 구간 유지 → 반복 알림 없음
    (30, 35, 35),     # 더 깊어짐
    (None, 40, 40),   # 한 번에 여러 구간 → 가장 깊은 1개만
    (40, 35, None),   # 회복 → 알림 없음
    (35, 40, 40),     # 회복 후 다시 깊어짐 → 재알림
    (30, None, None), # 구간 이탈
])
def test_newly_entered_zone(prev, new, entered):
    assert newly_entered_zone(prev, new) == entered


def test_outlier():
    assert is_outlier(50, 100)       # 하루 -50%
    assert is_outlier(250, 100)      # 하루 +150%
    assert is_outlier(0, 100)
    assert not is_outlier(70, 100)   # 하루 -30%는 실제로 있을 수 있음
