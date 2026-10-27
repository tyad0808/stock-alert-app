"""아침 브리핑 만들기 (매일 오전 9시 전).

Top 10 이슈(전일 등락·공시·뉴스)와 이번 주 일정. 계좌·구간 종목은 다른 탭에서 바로 보이므로 넣지 않는다.
뉴스·공시·일정은 읽을거리일 뿐 알림 판단에 쓰지 않는다.
일·월요일 아침은 전날 미국 장이 없어서 일정만 담는다.
"""

from datetime import date, datetime, timedelta, timezone

from .. import config
from ..checker import quote
from ..db import DB, KST, now_kst
from ..providers import get_provider
from . import sources
from .summarize import SummaryError, summarize, translate_headlines

US_EASTERN = timezone(timedelta(hours=-5))  # 날짜 계산용 (서머타임 차이는 하루 단위 계산에 영향 없음)


def _safe(fn):
    """한 면에서 오류가 나도 브리핑은 나가야 한다 (브리핑이 오는 것 자체가 생존 확인)."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e) or e.__class__.__name__}


def _issues(quotes, since_utc: datetime, us_since: date) -> dict:
    news, files, errors = {}, {}, []
    for q in quotes:
        try:
            news[q["symbol"]] = sources.news(q["symbol"], since_utc)
        except sources.SourceError as e:
            errors.append(f"뉴스: {e}")
            news[q["symbol"]] = []
        try:
            files[q["symbol"]] = sources.filings(q["symbol"], us_since)
        except sources.SourceError as e:
            errors.append(f"공시: {e}")
            files[q["symbol"]] = []
    summary, mode = {}, "translate"
    if config.ANTHROPIC_API_KEY:
        try:
            summary = summarize(news, {q["symbol"]: q["name"] for q in quotes})
            mode = "claude"
        except SummaryError as e:
            errors.append(f"뉴스 요약: {e} (자동 번역으로 대신 보여줍니다)")
    if mode != "claude":
        summary = translate_headlines(news, sources.translate_ko)
    stocks = []
    for q in quotes:
        items = [{"text": f["title"], "link": f["link"], "kind": "filing"} for f in files[q["symbol"]]]
        items += [{**s, "kind": "news"} for s in summary.get(q["symbol"], [])]
        stocks.append({"symbol": q["symbol"], "name": q["name"], "change_pct": q["change_pct"],
                       "drawdown": q["drawdown"], "items": items})
    result = {"stocks": stocks, "mode": mode}
    if errors:
        result["warnings"] = sorted(set(errors))[:5]
    return result


def _schedule(symbols: set[str], names: dict[str, str], us_today: date) -> dict:
    rows = sources.earnings_week(symbols, us_today)
    for r in rows:
        r["name"] = names.get(r["symbol"], r["name"])
    return {"earnings": rows}


def build(db: DB, provider=None, now: datetime | None = None) -> dict:
    provider = provider or get_provider(db)
    now = now or datetime.now(KST)
    today = now.astimezone(KST).date()
    market_day = today.weekday() not in (6, 0)  # 일(6)·월(0) 아침은 전날 미국 장이 없다

    watch = config.load_watchlist()
    names = {s["symbol"]: s["name"] for s in watch}
    data = {
        "date": today.isoformat(),
        "created_at": now_kst(),
        "market_day": market_day,
        "is_practice": provider.is_practice,
    }
    if market_day:
        quotes = _safe(lambda: [quote(s, provider.daily_bars(s["symbol"])) for s in watch])
        if isinstance(quotes, dict):
            data["issues"] = quotes
        else:
            since_utc = now.astimezone(timezone.utc) - timedelta(hours=30)
            us_since = (now.astimezone(US_EASTERN) - timedelta(days=1)).date()
            data["issues"] = _safe(lambda: _issues(quotes, since_utc, us_since))
    holdings = _safe(provider.holdings)
    held = {h["symbol"] for h in holdings} if isinstance(holdings, list) else set()
    data["schedule"] = _safe(lambda: _schedule(set(names) | held, names, now.astimezone(US_EASTERN).date()))
    return data


def run(db: DB, force: bool = False) -> dict | None:
    """오늘 브리핑을 만들어 저장한다. 이미 있으면 force 일 때만 다시 만든다."""
    today = datetime.now(KST).date().isoformat()
    if db.briefing(today) and not force:
        return None
    data = build(db)
    db.save_briefing(data["date"], data)
    return data
