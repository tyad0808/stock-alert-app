"""감시 목록 자동 갱신: 순위가 바뀌면 목록과 안내 문장이 바뀐다."""

import json

import pytest

from app import universe
from app.db import DB


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "t.db")


class Ranked:
    def __init__(self, stocks, etf):
        self.data = {"stocks": stocks, "etf": etf}

    def rankings(self, kind):
        if isinstance(self.data[kind], Exception):
            raise self.data[kind]
        return self.data[kind]


def rows(*symbols):
    return [{"symbol": s, "name": s} for s in symbols]


STOCKS = ["NVDA", "MSFT", "AAPL", "GOOGL", "GOOG", "AMZN", "META", "AVGO", "LLY", "BRK.A", "BRK.B", "TSM", "TSLA"]


def test_defaults_without_rankings(db):
    assert len(universe.stocks(db)) == 10
    assert [e["symbol"] for e in universe.etfs(db)][-3:] == ["SOXL", "TQQQ", "SOXX"]


def test_refresh_picks_top10_skipping_duplicate_classes(db):
    etf = rows("VOO", "IVV", "SPY", "VTI", "QQQ", "VUG", "VEA", "IEFA", "VTV", "BND", "SOXX")
    notes = universe.refresh(db, Ranked(rows(*STOCKS), etf))
    syms = [s["symbol"] for s in universe.stocks(db)]
    assert syms == ["NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "AVGO", "LLY", "BRK.B", "TSM"]
    assert universe.stocks(db)[0]["name"] == "엔비디아"  # 한국어 이름은 우리 목록 것
    assert notes == ["주식 Top 10 변경: LLY 들어옴 · 테슬라 빠짐"]
    # SOXX 가 Top 10 안에 없으니 extra 로 한 번만
    etfs = [e["symbol"] for e in universe.etfs(db)]
    assert etfs.count("SOXX") == 1
    assert universe.note(db)["notes"] == notes


def test_failure_keeps_list_and_retries_later(db):
    universe.refresh(db, Ranked(RuntimeError("키움 오류"), RuntimeError("키움 오류")))
    assert len(universe.stocks(db)) == 10  # 기본 목록 그대로
    assert db.get_meta("universe_date") is None  # 다음 확인 때 다시 시도
    universe.refresh(db, Ranked(rows(*STOCKS), RuntimeError("키움 오류")))
    assert "LLY" in [s["symbol"] for s in universe.stocks(db)]
    assert universe.refresh(db, Ranked(rows("X"), rows())) == []  # 오늘은 이미 갱신함


def test_sample_provider_has_no_rankings(db):
    from app.providers.sample import SampleProvider

    assert universe.refresh(db, SampleProvider()) == []
