"""키움 공급원: 실제 키움 서버 없이, 응답을 흉내 내서 확인한다."""

import re
from pathlib import Path

import pytest

from app.providers import kiwoom
from app.providers.kiwoom import KiwoomError, KiwoomProvider, _num


@pytest.fixture(autouse=True)
def clear_cache():
    kiwoom._cache.clear()
    kiwoom._exchange_of.clear()
    yield
    kiwoom._cache.clear()
    kiwoom._exchange_of.clear()


def chart_rows(n, start_price=100.0, skip=0):
    """최근 날짜가 먼저 오는 일봉 (키움 순서). 가격 앞에 방향 부호가 붙는다."""
    rows = []
    for i in range(n):
        d = 20261023 - skip - i  # 날짜 형식만 맞으면 된다
        price = start_price + i
        rows.append({"dt": str(d), "cur_prc": f"-{price:.4f}", "high_pric": f"+{price + 1:.4f}"})
    return rows


class FakeProvider(KiwoomProvider):
    def __init__(self, responses):
        super().__init__(app_key="k", app_secret="s")
        self.responses = responses
        self.calls = []

    def _post(self, path, body, headers):
        self.calls.append((path, headers.get("api-id"), body))
        if path == kiwoom.TOKEN_PATH:
            return {"token": "T", "expires_dt": "20991231235959", "return_code": 0}, {}
        return self.responses(headers["api-id"], body, headers)


def test_num_strips_direction_sign():
    assert _num("-123.45") == 123.45
    assert _num("+1,234.5") == 1234.5
    assert _num("") == 0.0
    assert _num(None) == 0.0


def test_missing_keys():
    with pytest.raises(KiwoomError):
        KiwoomProvider(app_key="", app_secret="")


def test_daily_bars_sorted_oldest_first_and_paged():
    pages = {"": (chart_rows(200), "K1"), "K1": (chart_rows(200, 300.0, skip=200), "")}

    def respond(api_id, body, headers):
        rows, nxt = pages[headers["next-key"]]
        return {"return_code": 0, "result_list": rows}, ({"cont-yn": "Y", "next-key": nxt} if nxt else {})

    p = FakeProvider(respond)
    bars = p.daily_bars("NVDA")
    assert [c[1] for c in p.calls if c[1]] == ["usa06012", "usa06012"]
    assert bars == sorted(bars, key=lambda b: b.date)
    assert bars[-1].close == 100.0 and bars[-1].high == 101.0
    assert p.calls[1][2]["stex_tp"] == "ND"  # 감시 목록의 거래소 코드를 쓴다


def test_daily_bars_cached():
    p = FakeProvider(lambda *_: ({"return_code": 0, "result_list": chart_rows(10)}, {}))
    p.daily_bars("NVDA")
    p.daily_bars("NVDA")
    assert len([c for c in p.calls if c[1] == "usa06012"]) == 1


def test_daily_bars_tries_other_exchange():
    def respond(api_id, body, headers):
        rows = chart_rows(10) if body["stex_tp"] == "NY" else []
        return {"return_code": 0, "result_list": rows}, {}

    p = FakeProvider(respond)
    assert len(p.daily_bars("PLTR")) == 10
    assert kiwoom._exchange_of["PLTR"] == "NY"


def test_holdings_and_fx():
    def respond(api_id, body, headers):
        if api_id == "ust21070":
            return {"return_code": 0, "result_list": [
                {"stk_cd": "NVDA", "frgn_stk_nm": "엔비디아", "qty": "20", "frgn_stk_book_uv": "160.1234",
                 "crnc_code": "USD", "stex_nm": "NASDAQ"},
                {"stk_cd": "OLD", "frgn_stk_nm": "판 종목", "qty": "0", "frgn_stk_book_uv": "10", "crnc_code": "USD"},
            ]}, {}
        return {"return_code": 0, "spcl_bf_exrt": "1,385.50", "aplc_exrt": "1390"}, {}

    p = FakeProvider(respond)
    assert p.holdings() == [{"symbol": "NVDA", "name": "엔비디아", "qty": 20.0, "avg_price": 160.1234}]
    assert kiwoom._exchange_of["NVDA"] == "ND"
    assert p.fx_rate() == 1385.5


def test_error_message():
    p = FakeProvider(lambda *_: ({"return_code": 1, "return_msg": "조회 오류"}, {}))
    with pytest.raises(KiwoomError, match="조회 오류"):
        p.holdings()


def test_only_read_only_apis_allowed():
    p = FakeProvider(lambda *_: ({"return_code": 0}, {}))
    with pytest.raises(KiwoomError, match="조회 전용"):
        p._call("ust12345", {})  # 목록에 없는 기능은 무엇이든 막힌다
    assert set(kiwoom.READ_ONLY_APIS) == {"usa06012", "ust21070", "ust31301"}


def test_no_order_code_in_provider():
    """주문 관련 키움 기능 주소·이름이 코드에 들어가지 않았는지 확인한다."""
    src = (Path(kiwoom.__file__)).read_text(encoding="utf-8")
    code = "\n".join(line for line in src.splitlines() if not line.strip().startswith("#"))
    assert not re.search(r"/api/us/ordr|/api/dostk/ordr|ord_qty|ord_uv", code)
