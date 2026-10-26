"""시세 확인 전체 흐름: 구간 진입 알림, 하루 1회 제한, 재진입, 이상값."""

import pytest

from app.checker import BUY_REVIEW, DATA_CHECK, check_stock
from app.db import DB
from app.rules import Bar

STOCK = {"symbol": "TEST", "name": "테스트"}


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "test.db")


def bars(*closes, start_day=1):
    """고점 $200 하루 뒤에 원하는 종가들이 이어지는 시세."""
    out = [Bar("2026-01-01", 200, 200)]
    for i, c in enumerate(closes):
        out.append(Bar(f"2026-02-{start_day + i:02d}", c, c))
    return out


def test_first_entry_alerts_once(db):
    history = bars(150, 139)  # -30.5%
    alert = check_stock(db, STOCK, history)
    assert alert["kind"] == BUY_REVIEW and alert["level"] == 30
    # 같은 날 다시 확인해도 알림 없음
    assert check_stock(db, STOCK, history) is None


def test_deeper_zone_alerts(db):
    check_stock(db, STOCK, bars(150, 139))
    alert = check_stock(db, STOCK, bars(150, 139, 129))  # -35.5%
    assert alert["level"] == 35


def test_big_drop_sends_single_deepest_alert(db):
    check_stock(db, STOCK, bars(150))
    alert = check_stock(db, STOCK, bars(150, 117))  # -41.5% (하루 -22%)
    assert alert["level"] == 40
    assert len(db.alerts()) == 1


def test_reentry_after_recovery_alerts_again(db):
    check_stock(db, STOCK, bars(150, 139))              # 30 진입
    assert check_stock(db, STOCK, bars(150, 139, 150)) is None  # 회복 (-25%)
    alert = check_stock(db, STOCK, bars(150, 139, 150, 138))    # 다른 날 재진입
    assert alert["level"] == 30


def test_reentry_same_day_is_blocked(db):
    day = bars(150, 139)
    check_stock(db, STOCK, day)
    check_stock(db, STOCK, bars(150, 150))  # 같은 날짜에 회복
    # 같은 날짜에 다시 진입 → 하루 1번 제한
    assert check_stock(db, STOCK, bars(150, 139)) is None


def test_outlier_is_flagged_not_alerted(db):
    check_stock(db, STOCK, bars(180))
    alert = check_stock(db, STOCK, bars(180, 60))  # 하루 -67%
    assert alert["kind"] == DATA_CHECK
    assert db.get_level("TEST") is None  # 구간 기록은 바뀌지 않음
    assert db.get_snapshot("TEST")["data_warning"] is True


def test_day_after_outlier_uses_trusted_close(db):
    check_stock(db, STOCK, bars(180, 60))
    # 다음 날 정상 가격 $175: 오류 값 $60이 아니라 $180과 비교 → 이상값 아님
    assert check_stock(db, STOCK, bars(180, 60, 175)) is None
    assert db.get_snapshot("TEST")["data_warning"] is False
