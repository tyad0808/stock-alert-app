"""폰 알림: 실제 알림 서버에는 보내지 않고 문구·기기 목록 관리만 확인한다."""

from datetime import datetime

import pytest

from app import push
from app.db import DB, KST

NINE = datetime(2026, 10, 27, 9, 0, tzinfo=KST)
SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "x", "auth": "y"}}


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "t.db")


def test_no_briefing_warns(db):
    title, body = push.morning_message(db, NINE)
    assert "브리핑이 없습니다" in title


def test_morning_message_counts_alerts(db):
    db.save_briefing("2026-10-27", {"date": "2026-10-27", "market_day": True,
                                    "issues": {"stocks": [{"items": [1]}, {"items": []}]}})
    for kind in ("buy", "buy", "profit"):
        db.add_alert(created_at="2026-10-27T03:00:00+09:00", market_date="2026-10-26", kind=kind,
                     symbol="X", name="X", level=20, price=1, high=1, drawdown=-20, message="m")
    title, body = push.morning_message(db, NINE)
    assert title == "10/27 아침 브리핑"
    assert body == "밤사이 새 알림 · 매수권장 2 · 수익 1\nTop 10 이슈 1종목"


def test_send_all_removes_dead_devices(db):
    db.add_push_sub(SUB)
    db.add_push_sub({**SUB, "endpoint": "https://push.example/dead"})
    sent = []
    result = push.send_all(db, "t", "b", send=lambda sub, payload: sent.append(payload) or "dead" not in sub["endpoint"])
    assert result == {"sent": 1, "removed": 1, "failed": 0}
    assert [s["endpoint"] for s in db.push_subs()] == [SUB["endpoint"]]
    assert '"url": "/#/brief"' in sent[0]


def test_vapid_key_created_once(tmp_path, monkeypatch):
    pytest.importorskip("py_vapid")
    monkeypatch.setattr(push, "VAPID_FILE", tmp_path / "vapid.pem")
    k1 = push.public_key()
    assert push.public_key() == k1 and len(k1) == 87  # 65바이트 공개 열쇠


def test_subscribe_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main
    from app import config

    monkeypatch.setattr(main, "db", DB(tmp_path / "api.db"))
    monkeypatch.setattr(config, "APP_PASSWORD", "")
    client = TestClient(main.app)
    assert client.post("/api/push/subscribe", json=SUB).json() == {"ok": True}
    assert client.post("/api/push/subscribe", json={**SUB, "endpoint": "http://evil"}).status_code == 422
    assert main.db.push_subs() == [SUB]
    client.post("/api/push/unsubscribe", json={"endpoint": SUB["endpoint"]})
    assert main.db.push_subs() == []
