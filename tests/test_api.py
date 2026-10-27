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


STOCKS = {"NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "BRK.B", "TSM"}


def test_initial_alerts_by_tier(client):
    got = {(a["symbol"], a["kind"]) for a in alerts(client)
           if a["kind"] in ("buy", "review") and a["symbol"] in STOCKS}
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
    # 신고가 근처라 하락 알림은 없고, 보유 종목 수익 알림만 있음
    assert {k for s, k in got if s == "AVGO"} == {"profit"}


def test_reset(client):
    first = len(alerts(client))
    client.post("/api/practice/advance", json={"days": 10})
    assert len(alerts(client)) > first
    client.post("/api/practice/reset")
    assert len(alerts(client)) == first  # 처음 상태로 돌아감
    stock_alerts = [a for a in alerts(client) if a["symbol"] in STOCKS and a["kind"] in ("buy", "review")]
    assert len(stock_alerts) == 8


def test_etf_board(client):
    d = client.get("/api/etf").json()
    syms = [s["symbol"] for s in d["stocks"]]
    assert syms[:3] == ["VOO", "IVV", "SPY"] and len(syms) == 13
    assert {"SOXL", "TQQQ", "SOXX"} <= set(syms)
    assert d["stocks"][0]["rank"] == 1 and d["stocks"][-1]["extra"] is True
    assert client.get("/api/stock/SOXL").status_code == 200


def test_stock_detail(client):
    d = client.get("/api/stock/NVDA").json()
    assert len(d["series"]) == 252
    assert d["zones"][0]["level"] == 5
    assert d["zones"][0]["price"] == pytest.approx(d["high"] * 0.95, abs=0.01)
    assert client.get("/api/stock/XXXX").status_code == 404


def test_initial_holding_alerts(client):
    got = {(a["symbol"], a["kind"], a["level"]) for a in alerts(client) if a["kind"] in ("profit", "loss")}
    # MSFT +14% → +10, AVGO +21% → +20, PLTR +26% → +20, NVDA -16%는 -20 전이라 없음
    assert got == {("MSFT", "profit", 10), ("AVGO", "profit", 20), ("PLTR", "profit", 20)}


def test_holding_alerts_over_practice(client):
    client.post("/api/practice/advance", json={"days": 60})
    got = {(a["symbol"], a["kind"], a["level"]) for a in alerts(client) if a["kind"] in ("profit", "loss")}
    assert ("NVDA", "loss", -20) in got     # -22%까지 빠짐
    assert ("AVGO", "profit", 30) in got    # +30%까지 오름
    pltr = [a for a in alerts(client) if a["symbol"] == "PLTR"]
    assert len(pltr) == 2  # +20 → 내려왔다가(+9%) → 다시 +20


def test_holdings_summary(client):
    d = client.get("/api/holdings").json()
    assert {h["symbol"] for h in d["holdings"]} == {"NVDA", "MSFT", "AVGO", "PLTR"}
    pltr = next(h for h in d["holdings"] if h["symbol"] == "PLTR")
    assert pltr["in_top10"] is False
    assert pltr["return_pct"] == pytest.approx(25.71, abs=0.01)
    t = d["total"]
    assert t["value_usd"] == pytest.approx(sum(h["value_usd"] for h in d["holdings"]))
    assert t["value_krw"] == round(t["value_usd"] * 1400)


def test_board_marks_held(client):
    stocks = {s["symbol"]: s for s in client.get("/api/board").json()["stocks"]}
    assert stocks["NVDA"]["held"] and not stocks["META"]["held"]


def test_detail_for_holding_outside_top10(client):
    d = client.get("/api/stock/PLTR").json()
    assert d["in_top10"] is False
    assert d["holding"]["qty"] == 50
    levels = [p["level"] for p in d["holding"]["pl_prices"]]
    assert levels[:3] == [10, 20, 30] and -20 in levels and -40 in levels


def test_split_plan(client):
    # NVDA: 20주 × 평단 $160 × 1,400원 = 448만 원 투자됨
    d = client.post("/api/split/NVDA", json={"total_krw": 10_000_000}).json()["split"]
    assert [p["amount"] for p in d["parts"]] == [3_000_000, 3_000_000, 4_000_000]
    assert [p["done"] for p in d["parts"]] == [True, False, False]
    assert d["next"]["n"] == 2
    assert d["remaining"] == 10_000_000 - 4_480_000
    assert client.get("/api/stock/NVDA").json()["split"]["total"] == 10_000_000
    # 지우기
    assert client.post("/api/split/NVDA", json={"total_krw": 0}).json()["split"] is None
    assert client.post("/api/split/XXXX", json={"total_krw": 1}).status_code == 404


def test_split_shown_in_drop_alert(client):
    client.post("/api/split/META", json={"total_krw": 10_000_000})
    client.post("/api/practice/advance", json={"days": 12})  # META -45% 진입
    meta = [a for a in alerts(client) if a["symbol"] == "META" and a["level"] == 45]
    assert "다음 분할 1차 3,000,000원" in meta[0]["message"]


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
