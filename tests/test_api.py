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


def test_watchlist_sorted_by_drawdown(client):
    stocks = client.get("/api/watchlist").json()["stocks"]
    assert len(stocks) == 10
    dds = [s["drawdown"] for s in stocks]
    assert dds == sorted(dds)


def test_initial_alerts_for_stocks_already_down(client):
    # 연습 시작일에 이미 -30% 이상인 종목: NVDA(-33), META(-41), TSM(-31)
    alerts = client.get("/api/alerts").json()["alerts"]
    assert {a["symbol"] for a in alerts} == {"NVDA", "META", "TSM"}


def test_practice_run_through(client):
    res = client.post("/api/practice/advance", json={"days": 60}).json()
    assert res["can_advance"] is False
    kinds = {(a["symbol"], a["kind"]) for a in client.get("/api/alerts").json()["alerts"]}
    assert ("TSLA", "data_check") in kinds   # 오류 데이터 하루
    assert ("TSLA", "buy_review") in kinds   # -30% 진입
    assert ("GOOGL", "buy_review") in kinds  # 잠깐 -30% 진입
    meta_levels = {a["level"] for a in client.get("/api/alerts").json()["alerts"]
                   if a["symbol"] == "META"}
    assert {40, 45, 50} <= meta_levels
    # 고점 근처 종목은 알림 없음
    assert ("MSFT", "buy_review") not in kinds


def test_reset(client):
    client.post("/api/practice/advance", json={"days": 10})
    client.post("/api/practice/reset")
    assert len(client.get("/api/alerts").json()["alerts"]) == 3


def test_stock_detail(client):
    d = client.get("/api/stock/NVDA").json()
    assert len(d["series"]) == 252
    assert d["zones"][0] == {"level": 30, "price": pytest.approx(d["high"] * 0.7, abs=0.01)}


def test_login_required(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APP_PASSWORD", "pw1234")
    from app import config, main
    importlib.reload(config)
    importlib.reload(main)
    with TestClient(main.app) as c:
        assert c.get("/api/watchlist").status_code == 401
        assert c.post("/api/login", json={"password": "wrong"}).status_code == 401
        assert c.post("/api/login", json={"password": "pw1234"}).status_code == 200
        assert c.get("/api/watchlist").status_code == 200
