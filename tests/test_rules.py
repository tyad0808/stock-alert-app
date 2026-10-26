"""원칙 엔진과 알림 필터가 기획서 4장 규칙대로 움직이는지 확인한다."""

import pytest

from app.alerts import held_level, held_pl_level, is_outlier, newly_entered_pl, newly_entered_zone
from app.rules import Bar, drawdown_pct, high_52w, pl_level, return_pct, split_plan, tier, zone_level, zone_price


@pytest.mark.parametrize("dd, level", [
    (-2, None), (-4.99, None),
    (-5, 5), (-9.9, 5), (-10, 10), (-20, 20), (-25, 25), (-30, 30),
    (-34.9, 30), (-35, 35), (-37.2, 35), (-50, 50), (-72, 70),
])
def test_zone_level(dd, level):
    assert zone_level(dd) == level


def test_zone_level_float_error():
    # $200 고점에서 $130이면 정확히 -35% 구간
    assert zone_level(drawdown_pct(130, 200)) == 35


@pytest.mark.parametrize("level, key", [
    (None, None), (5, "review"), (10, "review"), (15, "review"),
    (20, "buy"), (25, "buy"), (35, "buy"), (60, "buy"),
])
def test_tier(level, key):
    t = tier(level)
    assert (t["key"] if t else None) == key


def test_tier_labels():
    assert tier(15)["label"] == "매수검토"
    assert tier(20)["label"] == "매수권장"


def test_zone_prices():
    # 1년 고점 $200일 때
    assert [zone_price(200, lv) for lv in (5, 10, 25, 30, 35, 40)] == \
        pytest.approx([190, 180, 150, 140, 130, 120])


def test_high_52w_uses_last_year_only():
    old = [Bar("old", 999, 999)]
    year = [Bar(str(i), 100, 100 + i % 10) for i in range(252)]
    assert high_52w(old + year) == 109


@pytest.mark.parametrize("prev, dd, held", [
    (None, -3, None),
    (None, -36, 35),    # 처음 진입
    (30, -36, 35),      # 더 깊어지면 바로 새 구간
    (35, -34, 35),      # -35 기준에서 1%p 회복 → 아직 35
    (35, -33.1, 35),    # 1.9%p 회복 → 아직 35
    (35, -33, 30),      # 2%p 회복 → 30으로
    (35, -27, 25),      # 크게 회복 → 여유 반영한 구간 (-29% 기준)
    (15, -13.5, 15),    # -15 기준에서 1.5%p 회복 → 아직 15
    (15, -12.9, 10),    # 2%p 이상 회복 → 10구간으로
    (5, -2.9, None),    # -5 기준에서 2%p 이상 회복 → 구간 벗어남
])
def test_held_level(prev, dd, held):
    assert held_level(prev, dd) == held


@pytest.mark.parametrize("prev, new, entered", [
    (None, None, None),
    (None, 5, 5),     # 처음 -5% 진입
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


# ---------- 내 종목: 수익 +10%마다, 손실 -20%마다 ----------

def test_return_pct():
    assert return_pct(115, 100) == pytest.approx(15)


@pytest.mark.parametrize("ret, level", [
    (0, None), (9.99, None), (10, 10), (19.9, 10), (27, 20), (105, 100),
    (-10, None), (-19.99, None), (-20, -20), (-39.9, -20), (-45, -40),
])
def test_pl_level(ret, level):
    assert pl_level(ret) == level


@pytest.mark.parametrize("prev, ret, held", [
    (None, 15, 10),
    (10, 21, 20),       # 수익 더 커짐
    (20, 18.5, 20),     # +20에서 1.5%p 내려옴 → 아직 20
    (20, 17.9, 10),     # 2%p 이상 내려옴 → 10
    (10, 5, None),      # 수익 구간 벗어남
    (-20, -18.5, -20),  # -20에서 1.5%p 올라옴 → 아직 -20
    (-20, -17.9, None), # 2%p 이상 올라옴 → 벗어남
    (-20, -41, -40),    # 손실 더 깊어짐
    (20, -25, -20),     # 수익에서 손실로 급변
])
def test_held_pl_level(prev, ret, held):
    assert held_pl_level(prev, ret) == held


@pytest.mark.parametrize("prev, new, entered", [
    (None, 10, 10), (10, 20, 20), (20, 10, None), (20, 20, None),
    (None, -20, -20), (-20, -40, -40), (-40, -20, None),
    (10, -20, -20), (-20, 10, 10), (None, None, None),
])
def test_newly_entered_pl(prev, new, entered):
    assert newly_entered_pl(prev, new) == entered


def test_split_plan_parts():
    p = split_plan(10_000_000, 0, 140 * 1400)
    assert [x["amount"] for x in p["parts"]] == [3_000_000, 3_000_000, 4_000_000]
    assert p["parts"][0]["shares"] == pytest.approx(15.3, abs=0.1)  # 기획서 예시: 약 15주
    assert p["next"]["n"] == 1 and p["remaining"] == 10_000_000


@pytest.mark.parametrize("invested, done", [
    (0, [False, False, False]),
    (2_900_000, [True, False, False]),   # 1차 금액의 95% 이상 → 1차 완료
    (5_700_000, [True, False, False]),   # 2차 누적 600만에 5,850,000 미만
    (5_900_000, [True, True, False]),
    (10_000_000, [True, True, True]),
])
def test_split_plan_progress(invested, done):
    p = split_plan(10_000_000, invested, 200_000)
    assert [x["done"] for x in p["parts"]] == done
