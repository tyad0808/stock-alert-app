"""브리핑 재료 모으기: 종목 뉴스 제목(야후 파이낸스 RSS), 미국 공시(SEC), 실적 발표 일정(나스닥).

모두 키 없이 쓰는 공개 자료다. 여기서 모은 것은 브리핑 3·4면에만 쓰고, 알림 판단에는 절대 쓰지 않는다.
"""

import json
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .. import config

TIMEOUT = 15
BROWSER_UA = "Mozilla/5.0 (compatible; stock-alert-app/1.0)"


class SourceError(RuntimeError):
    pass


def _get(url: str, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            return res.read()
    except (urllib.error.URLError, TimeoutError) as e:
        raise SourceError(f"{url.split('/')[2]} 접속 실패: {e}") from None


# ---- 뉴스 제목 ----

def news(symbol: str, since: datetime, limit: int = 8) -> list[dict]:
    """since 이후 뉴스 제목: [{title, link, source, published}] (최신순)."""
    yahoo = symbol.replace(".", "-")  # BRK.B → BRK-B
    raw = _get(f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={yahoo}&region=US&lang=en-US")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise SourceError(f"뉴스 형식 오류: {e}") from None
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        try:
            published = parsedate_to_datetime(it.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if not title or not link.startswith("http") or published < since:
            continue
        items.append({"title": title, "link": link, "source": "Yahoo Finance",
                      "published": published.isoformat(timespec="minutes")})
    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:limit]


# ---- 공시 (SEC EDGAR) ----

SEC_HEADERS = {"User-Agent": config.SEC_USER_AGENT, "Accept-Encoding": "identity"}
FORMS = {
    "8-K": "주요 사항 보고(8-K)",
    "10-Q": "분기 보고서(10-Q)",
    "10-K": "연간 보고서(10-K)",
    "6-K": "해외기업 수시 보고(6-K)",
    "20-F": "해외기업 연간 보고서(20-F)",
}
# 8-K 항목 번호 → 내용 (자주 나오는 것만)
ITEMS_8K = {
    "1.01": "주요 계약 체결", "1.02": "주요 계약 종료", "2.01": "자산 인수·매각 완료", "2.02": "실적 발표",
    "2.05": "구조조정 비용", "5.02": "임원·이사 변경", "5.07": "주주총회 결과", "7.01": "투자자 대상 자료 공개",
    "8.01": "기타 주요 사항",
}
TICKER_CACHE_DAYS = 30


def _cik_map() -> dict[str, int]:
    """SEC 종목코드 → 회사번호(CIK). 한 달에 한 번만 새로 받는다."""
    path = config.DATA_DIR / "sec_tickers.json"
    if path.exists() and time.time() - path.stat().st_mtime < TICKER_CACHE_DAYS * 86400:
        return json.loads(path.read_text(encoding="utf-8"))
    data = json.loads(_get("https://www.sec.gov/files/company_tickers.json", SEC_HEADERS))
    mapping = {v["ticker"].upper(): int(v["cik_str"]) for v in data.values()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return mapping


def filings(symbol: str, since: date) -> list[dict]:
    """since(미국 날짜) 이후 주요 공시: [{form, label, title, date, link}]."""
    cik = _cik_map().get(symbol.replace(".", "-").upper())
    if cik is None:
        return []
    data = json.loads(_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", SEC_HEADERS))
    recent = data.get("filings", {}).get("recent", {})
    result = []
    for i, form in enumerate(recent.get("form", [])):
        filed = recent["filingDate"][i]
        if form not in FORMS or filed < since.isoformat():
            continue
        acc = recent["accessionNumber"][i].replace("-", "")
        doc = recent["primaryDocument"][i]
        items = [x.strip() for x in (recent.get("items", [""] * (i + 1))[i] or "").split(",") if x.strip()]
        detail = ", ".join(ITEMS_8K[x] for x in items if x in ITEMS_8K) if form == "8-K" else ""
        result.append({
            "form": form,
            "label": FORMS[form],
            "title": f"{FORMS[form]}{' · ' + detail if detail else ''}",
            "date": filed,
            "link": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}",
        })
    return result[:5]


# ---- 실적 발표 일정 (나스닥) ----

TIME_LABEL = {"time-pre-market": "장 시작 전", "time-after-hours": "장 마감 후"}


def earnings_week(symbols: set[str], today: date) -> list[dict]:
    """이번 주(오늘~금요일, 미국 날짜, 주말이면 다음 주) 실적 발표 예정: [{symbol, name, date, time}]."""
    result = []
    for i in range(7):
        d = today + timedelta(days=i)
        if d.weekday() == 5 and i > 0:
            break  # 토요일에 닿으면 이번 주 끝
        if d.weekday() > 4:
            continue
        raw = _get(f"https://api.nasdaq.com/api/calendar/earnings?date={d.isoformat()}",
                   {"Accept": "application/json"})
        try:
            rows = (json.loads(raw).get("data") or {}).get("rows") or []
        except ValueError:
            raise SourceError("실적 일정 형식 오류") from None
        for r in rows:
            sym = str(r.get("symbol", "")).upper().replace("/", ".")
            if sym in symbols:
                result.append({"symbol": sym, "name": r.get("name", ""), "date": d.isoformat(),
                               "time": TIME_LABEL.get(r.get("time", ""), "")})
    return result
