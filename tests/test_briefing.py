"""아침 브리핑: 외부 자료(뉴스·공시·일정·Claude)는 흉내 내고, 연습용 시세로 만든다."""

import json
from datetime import datetime

import pytest

from app import config
from app.briefing import build as build_mod
from app.briefing import sources, summarize as summ
from app.checker import run_check
from app.db import DB, KST
from app.providers.sample import SampleProvider

TUESDAY = datetime(2026, 10, 27, 8, 50, tzinfo=KST)
MONDAY = datetime(2026, 10, 26, 8, 50, tzinfo=KST)


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "t.db")


@pytest.fixture(autouse=True)
def fake_sources(monkeypatch):
    monkeypatch.setattr(sources, "news", lambda symbol, since, limit=8: [
        {"title": f"{symbol} reports quarterly results", "link": f"https://news.example/{symbol}",
         "source": "Yahoo Finance", "published": "2026-10-26T21:00+00:00"}] if symbol == "NVDA" else [])
    monkeypatch.setattr(sources, "filings", lambda symbol, since: [
        {"form": "8-K", "label": "주요 사항 보고(8-K)", "title": "주요 사항 보고(8-K) · 실적 발표",
         "date": "2026-10-26", "link": "https://www.sec.gov/x"}] if symbol == "MSFT" else [])
    monkeypatch.setattr(sources, "translate_ko", lambda text: "엔비디아 분기 실적 발표" if "results" in text else None)
    monkeypatch.setattr(sources, "earnings_week", lambda symbols, today: [
        {"symbol": "AAPL", "name": "Apple Inc.", "date": "2026-10-29", "time": "장 마감 후"}])
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")


def test_opinion_filter():
    assert summ.is_opinion("지금이 매수 기회다")
    assert summ.is_opinion("주가가 오를 것으로 보인다")
    assert not summ.is_opinion("3분기 매출 351억 달러를 발표했다")


def test_summarize_keeps_only_facts_with_own_links(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-ant-test")
    news = {"NVDA": [{"title": "Nvidia posts record revenue", "link": "https://a"}],
            "MSFT": [{"title": "Is Microsoft a buy?", "link": "https://b"}]}
    reply = {"stocks": [
        {"symbol": "NVDA", "items": [
            {"text": "엔비디아가 분기 최대 매출을 발표했다", "sources": [1]},
            {"text": "엔비디아 주가가 더 오를 것으로 보인다", "sources": [1]},  # 의견 → 버림
            {"text": "근거 없는 줄", "sources": []},                          # 원문 없음 → 버림
            {"text": "다른 종목 원문을 단 줄", "sources": [2]},                 # 남의 원문 → 버림
        ]},
        {"symbol": "XXXX", "items": [{"text": "목록에 없는 종목", "sources": [1]}]},
    ]}
    prompts = []
    result = summ.summarize(news, {"NVDA": "엔비디아"}, call=lambda p: prompts.append(p) or json.dumps(reply))
    assert result == {"NVDA": [{"text": "엔비디아가 분기 최대 매출을 발표했다", "link": "https://a"}]}
    assert "1. Nvidia posts record revenue" in prompts[0]


def test_translate_skips_opinion_headlines():
    news = {"NVDA": [
        {"title": "Is Nvidia stock a buy now?", "link": "https://1"},
        {"title": "Analysts raise Nvidia price target", "link": "https://2"},
        {"title": "3 Best AI Stocks to Own", "link": "https://3"},
        {"title": "Nvidia announces new data center chip", "link": "https://4"},
        {"title": "Nvidia shares close lower", "link": "https://5"},
    ]}
    result = summ.translate_headlines(news, lambda t: None)  # 번역 실패 → 영어 그대로
    assert [x["link"] for x in result["NVDA"]] == ["https://4", "https://5"]
    assert result["NVDA"][0]["text"] == "Nvidia announces new data center chip"
    assert result["NVDA"][0]["translated"] is False


def test_translated_opinion_is_dropped():
    news = {"NVDA": [{"title": "Nvidia expands supply deal", "link": "https://1"}]}
    assert summ.translate_headlines(news, lambda t: "엔비디아, 주가가 오를 것으로 보인다") == {}


def test_summarize_without_key_returns_nothing():
    assert summ.summarize({"NVDA": [{"title": "t", "link": "https://a"}]}, {}, call=lambda p: 1 / 0) == {}


def test_build_weekday_has_all_pages(db):
    provider = SampleProvider()
    run_check(db, provider)
    b = build_mod.build(db, provider, now=TUESDAY)
    assert b["date"] == "2026-10-27" and b["market_day"]
    assert b["account"]["value_usd"] > 0
    zones = b["zones"]["stocks"]
    assert zones and all(z["tier"] for z in zones)
    assert [z["drawdown"] for z in zones] == sorted(z["drawdown"] for z in zones)
    assert all(z["new"] for z in zones)  # 첫 브리핑: 처음 확인에서 생긴 알림이 모두 NEW
    issues = {s["symbol"]: s for s in b["issues"]["stocks"]}
    assert len(issues) == 10
    assert issues["MSFT"]["items"][0]["kind"] == "filing"
    # Claude 키가 없으면 영어 제목을 무료 자동 번역 (원문 제목도 함께)
    assert issues["NVDA"]["items"] == [{"text": "엔비디아 분기 실적 발표", "original": "NVDA reports quarterly results",
                                        "link": "https://news.example/NVDA", "translated": True, "kind": "news"}]
    assert b["issues"]["mode"] == "translate"
    assert b["schedule"]["earnings"][0]["name"] == "애플"


def test_monday_has_only_account_and_schedule(db):
    b = build_mod.build(db, SampleProvider(), now=MONDAY)
    assert not b["market_day"]
    assert "zones" not in b and "issues" not in b
    assert "account" in b and "schedule" in b


def test_one_page_error_does_not_stop_briefing(db, monkeypatch):
    def broken(symbols, today):
        raise sources.SourceError("nasdaq 접속 실패")

    monkeypatch.setattr(sources, "earnings_week", broken)
    b = build_mod.build(db, SampleProvider(), now=TUESDAY)
    assert b["schedule"] == {"error": "nasdaq 접속 실패"}
    assert "error" not in b["account"]


def test_new_only_after_previous_briefing(db):
    provider = SampleProvider()
    run_check(db, provider)
    first = build_mod.build(db, provider, now=TUESDAY)
    db.save_briefing("2026-10-26", first)  # 어제 브리핑이 있었다고 치면, 그 뒤 새 알림이 없으니 NEW 없음
    b = build_mod.build(db, provider, now=TUESDAY)
    assert not any(z["new"] for z in b["zones"]["stocks"])


def test_briefing_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main

    monkeypatch.setattr(main, "db", DB(tmp_path / "api.db"))
    monkeypatch.setattr(config, "APP_PASSWORD", "")
    client = TestClient(main.app)
    assert client.get("/api/briefing").json() == {"briefing": None, "dates": []}
    made = client.post("/api/briefing").json()
    assert made["briefing"]["date"] == made["dates"][0]
    again = client.get(f"/api/briefing?date={made['dates'][0]}").json()
    assert again["briefing"]["created_at"] == made["briefing"]["created_at"]
