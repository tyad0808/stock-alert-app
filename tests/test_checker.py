"""시세 확인 전체 흐름: 구간 진입 알림, 단계, 경계선 여유, 하루 1회 제한, 이상값."""

import pytest

from app.checker import DATA_CHECK, LOSS, PROFIT, check_holding, check_stock, quote
from app.db import DB
from app.rules import Bar

STOCK = {"symbol": "TEST", "name": "테스트"}


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "test.db")


def bars(*closes):
    """고점 $200 하루 뒤에 원하는 종가들이 하루씩 이어지는 시세."""
    out = [Bar("2026-01-01", 200, 200)]
    for i, c in enumerate(closes):
        out.append(Bar(f"2026-02-{i + 1:02d}", c, c))
    return out


def test_quote_reports_any_level():
    q = quote(STOCK, bars(198, 196))  # -2%
    assert q["drawdown"] == -2.0 and q["level"] is None and q["tier"] is None
    q = quote(STOCK, bars(170, 164))  # -18%
    assert q["level"] == 15 and q["tier"]["label"] == "매수검토"
    q = quote(STOCK, bars(165, 158))  # -21%
    assert q["level"] == 20 and q["tier"]["label"] == "매수권장"


def test_new_high_flag():
    assert quote(STOCK, bars(190, 205))["new_high"] is True
    assert quote(STOCK, bars(190, 195))["new_high"] is False


@pytest.mark.parametrize("price, kind, level", [
    (188, "review", 5),    # -6%
    (178, "review", 10),   # -11%
    (168, "review", 15),   # -16%
    (158, "buy", 20),      # -21%
    (148, "buy", 25),      # -26%
    (118, "buy", 40),      # -41%
])
def test_alert_kind_by_tier(db, price, kind, level):
    alert = check_stock(db, STOCK, bars(price * 1.05, price))
    assert alert["kind"] == kind and alert["level"] == level


def test_first_entry_alerts_once(db):
    history = bars(150, 139)  # -30.5%
    assert check_stock(db, STOCK, history)["level"] == 30
    assert check_stock(db, STOCK, history) is None  # 같은 날 다시 확인해도 없음


def test_deeper_zone_alerts(db):
    check_stock(db, STOCK, bars(150, 139))
    alert = check_stock(db, STOCK, bars(150, 139, 129))  # -35.5%
    assert alert["kind"] == "buy" and alert["level"] == 35


def test_big_drop_sends_single_deepest_alert(db):
    check_stock(db, STOCK, bars(195))
    alert = check_stock(db, STOCK, bars(195, 117))  # -2.5% → -41.5% 하루에
    assert alert["level"] == 40
    assert len(db.alerts()) == 1


def test_wobble_near_boundary_no_repeat(db):
    # -35% 경계선 근처에서 흔들림: -35.5 → -34 → -35.5 → 반복 알림 없음
    check_stock(db, STOCK, bars(135, 129))
    assert check_stock(db, STOCK, bars(135, 129, 132)) is None
    assert check_stock(db, STOCK, bars(135, 129, 132, 129)) is None
    assert len(db.alerts()) == 1


def test_reentry_after_real_recovery_alerts_again(db):
    check_stock(db, STOCK, bars(135, 129))                     # 35 진입
    check_stock(db, STOCK, bars(135, 129, 133.5))              # -33.25%: 2%p 미만 회복
    assert db.get_level("TEST") == 35
    check_stock(db, STOCK, bars(135, 129, 133.5, 134.5))       # -32.75%: 2%p 이상 회복
    assert db.get_level("TEST") == 30
    alert = check_stock(db, STOCK, bars(135, 129, 133.5, 134.5, 129))  # 다시 -35.5%
    assert alert["level"] == 35


def test_reentry_same_day_is_blocked(db):
    check_stock(db, STOCK, bars(150, 139))
    check_stock(db, STOCK, bars(150, 160))  # 같은 날짜에 크게 회복 (-20%)
    assert check_stock(db, STOCK, bars(150, 139)) is None  # 같은 날짜 재진입 → 하루 1번


def test_outlier_is_flagged_not_alerted(db):
    check_stock(db, STOCK, bars(195))
    alert = check_stock(db, STOCK, bars(195, 60))  # 하루 -69%
    assert alert["kind"] == DATA_CHECK
    assert db.get_level("TEST") is None  # 구간 기록은 바뀌지 않음
    assert quote(STOCK, bars(195, 60))["data_warning"] is True


def test_day_after_outlier_uses_trusted_close(db):
    check_stock(db, STOCK, bars(195, 60))
    # 다음 날 정상 가격 $194: 오류 값 $60이 아니라 $195와 비교 → 이상값 아님
    assert check_stock(db, STOCK, bars(195, 60, 194)) is None
    assert quote(STOCK, bars(195, 60, 194))["data_warning"] is False


# ---------- 내 종목 ----------

HOLD = {"symbol": "TEST", "name": "테스트", "qty": 10, "avg_price": 100.0}


def hbars(*closes):
    return [Bar(f"2026-03-{i + 1:02d}", c, c) for i, c in enumerate(closes)]


def test_holding_profit_steps(db):
    assert check_holding(db, HOLD, hbars(100, 105)) is None           # +5%
    a = check_holding(db, HOLD, hbars(100, 105, 111))                 # +11%
    assert a["kind"] == PROFIT and a["level"] == 10
    assert "보유 10주" in a["message"]
    a = check_holding(db, HOLD, hbars(100, 105, 111, 121))            # +21%
    assert a["level"] == 20


def test_holding_loss_steps(db):
    assert check_holding(db, HOLD, hbars(100, 85)) is None            # -15%
    a = check_holding(db, HOLD, hbars(100, 85, 79))                   # -21%
    assert a["kind"] == LOSS and a["level"] == -20
    assert "-20%" in a["message"]


def test_holding_avg_change_resets_quietly(db):
    check_holding(db, HOLD, hbars(100, 111))                          # +10 알림
    # 추가 매수로 평단 $100 → $90: 현재가 $111은 새 평단 대비 +23%지만 바뀐 순간엔 알리지 않음
    new_avg = {**HOLD, "avg_price": 90.0, "qty": 20}
    assert check_holding(db, new_avg, hbars(100, 111, 111)) is None
    assert db.get_holding_state("TEST") == {"level": 20, "avg_price": 90.0}
    # 이후 +30% 진입은 새 평단 기준으로 알림
    assert check_holding(db, new_avg, hbars(100, 111, 111, 118))["level"] == 30
