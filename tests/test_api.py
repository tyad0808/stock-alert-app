"""앱 서버 API와 연습용 데이터 흐름."""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APP_PASSWORD", "")
    from app import config, main
    importlib.reload(config)
    importlib.reload(main)
    with TestClient(main.app) as c:
        yield c


def alerts(client):
    return client.get("/api/alerts").json()["alerts"]


def test_board_has_all_ten_in_watchlist_order(client):
    stocks = client.get("/api/board").json()["stocks"]
    assert [s["symbol"] for s in stocks][:3] == ["NVDA", "MSFT", "AAPL"]
    assert len(stocks) == 10
    # -30%가 아니어도 모든 종목의 고점 대비 값이 있다
    assert all(isinstance(s["drawdown"], float) for s in stocks)


def test_initial_alerts_by_tier(client):
    got = {(a["symbol"], a["kind"]) for a in alerts(client)}
    assert got == {
        ("META", "buy"),       # -41%
        ("NVDA", "buy"),       # -33%
        ("TSM", "buy"),        # -31%
        ("TSLA", "buy"),       # -28%
        ("GOOGL", "buy"),      # -22%
        ("AAPL", "review"),    # -13%
        ("AMZN", "review"),    # -9%
        ("BRK.B", "review"),   # -7%
    }  # MSFT(-4.6%), AVGO(-0.4%)는 -5% 전이라 알림 없음


def test_practice_run_through(client):
    res = client.post("/api/practice/advance", json={"days": 60}).json()
    assert res["can_advance"] is False
    got = {(a["symbol"], a["kind"]) for a in alerts(client)}
    assert ("TSLA", "data_check") in got
    assert ("NVDA", "buy") in got
    meta_levels = {a["level"] for a in alerts(client) if a["symbol"] == "META"}
    assert {40, 45, 50} <= meta_levels
    assert not any(s == "AVGO" for s, _ in got)  # 신고가 근처는 알림 없음


def test_reset(client):
    client.post("/api/practice/advance", json={"days": 10})
    client.post("/api/practice/reset")
    assert len(alerts(client)) == 8


def test_stock_detail(client):
    d = client.get("/api/stock/NVDA").json()
    assert len(d["series"]) == 252
    assert d["zones"][0]["level"] == 5
    assert d["zones"][0]["price"] == pytest.approx(d["high"] * 0.95, abs=0.01)
    assert client.get("/api/stock/XXXX").status_code == 404


def test_login_required(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APP_PASSWORD", "pw1234")
    from app import config, main
    importlib.reload(config)
    importlib.reload(main)
    with TestClient(main.app) as c:
        assert c.get("/api/board").status_code == 401
        assert c.post("/api/login", json={"password": "wrong"}).status_code == 401
        assert c.post("/api/login", json={"password": "pw1234"}).status_code == 200
        assert c.get("/api/board").status_code == 200
