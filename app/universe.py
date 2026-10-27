"""감시 목록: 주식 Top 10(시가총액)과 ETF(정해 둔 목록).

주식 Top 10은 키움 시가총액 순위로 하루 한 번 자동 갱신한다. 순위를 못 받으면 마지막으로 받은 목록,
그것도 없으면 config/watchlist.json 을 쓴다. ETF는 config/etf.json 그대로 본다.
"""

import json

from . import config
from .db import DB, KST

TOP_N = 10
# 같은 회사의 다른 주식 종류는 하나만 (알파벳 C, 버크셔 A)
SKIP = {"GOOG", "BRK.A"}


def _file(name: str) -> dict:
    return json.loads((config.ROOT / "config" / name).read_text(encoding="utf-8"))


def _saved(db: DB | None, kind: str) -> list[dict] | None:
    raw = db.get_meta(f"universe:{kind}") if db is not None else None
    return json.loads(raw) if raw else None


def stocks(db: DB | None = None) -> list[dict]:
    """주식 Top 10."""
    return _saved(db, "stocks") or _file("watchlist.json")["stocks"]


def etfs(db: DB | None = None) -> list[dict]:
    """ETF 탭: 정해 둔 목록 그대로."""
    return _file("etf.json")["stocks"]


def everything(db: DB | None = None) -> list[dict]:
    """알림을 확인할 전체 (주식 + ETF)."""
    out, seen = [], set()
    for s in stocks(db) + etfs(db):
        if s["symbol"] not in seen:
            seen.add(s["symbol"])
            out.append(s)
    return out


def find(db: DB | None, symbol: str) -> dict | None:
    return next((s for s in everything(db) if s["symbol"] == symbol), None)


def _pick(rows: list[dict], names: dict[str, str]) -> list[dict]:
    picked = []
    for r in rows:
        if r["symbol"] in SKIP or any(p["symbol"] == r["symbol"] for p in picked):
            continue
        picked.append({**r, "name": names.get(r["symbol"], r["name"])})
        if len(picked) == TOP_N:
            break
    return picked


def refresh(db: DB, provider) -> list[str]:
    """하루 한 번 순위를 새로 받는다. 돌려주는 값: 바뀐 내용 안내 문장들."""
    from datetime import datetime

    today = datetime.now(KST).date().isoformat()
    if db.get_meta("universe_date") == today or not hasattr(provider, "rankings"):
        return []
    # 한국어 이름은 우리 목록에 있는 이름을 먼저 쓴다
    names = {s["symbol"]: s["name"] for s in _file("watchlist.json")["stocks"] + stocks(db)}
    notes, ok = [], False
    for kind, label, current in (("stocks", "주식", stocks(db)),):
        try:
            new = _pick(provider.rankings(kind), names)
        except Exception as e:  # noqa: BLE001 — 순위를 못 받으면 어제 목록 그대로
            print(f"{label} 순위 갱신 실패: {e}")
            continue
        if len(new) < TOP_N:
            continue
        ok = True
        old_syms = {s["symbol"] for s in current}
        new_syms = {s["symbol"] for s in new}
        if old_syms != new_syms:
            came = [s["name"] for s in new if s["symbol"] not in old_syms]
            went = [s["name"] for s in current if s["symbol"] not in new_syms]
            notes.append(f"Top 10 변경: {', '.join(came)} 들어옴 · {', '.join(went)} 빠짐")
        db.set_meta(f"universe:{kind}", json.dumps(new, ensure_ascii=False))
    if ok:  # 실패했으면 15분 뒤 다시 시도
        db.set_meta("universe_date", today)
    if notes:
        db.set_meta("universe_note", json.dumps({"date": today, "notes": notes}, ensure_ascii=False))
    return notes


def note(db: DB) -> dict | None:
    """최근 목록 변경 안내 (화면 위쪽에 보여준다)."""
    raw = db.get_meta("universe_note")
    return json.loads(raw) if raw else None
