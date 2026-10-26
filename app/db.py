"""기록 저장소 (SQLite). 종목별 현재 구간, 알림 이력, 마지막 확인 결과를 남긴다."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- 종목별로 지금 들어가 있는 가장 깊은 매수 검토 구간 (없으면 NULL)
CREATE TABLE IF NOT EXISTS zone_state (
    symbol TEXT PRIMARY KEY,
    level INTEGER
);
-- 관심 종목 화면에 보여줄 마지막 확인 결과
CREATE TABLE IF NOT EXISTS snapshot (
    symbol TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alert (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    market_date TEXT NOT NULL,
    kind TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    level INTEGER,
    price REAL,
    high REAL,
    drawdown REAL,
    message TEXT NOT NULL
);
"""


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute("REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
        self.conn.commit()

    def get_level(self, symbol: str) -> int | None:
        row = self.conn.execute("SELECT level FROM zone_state WHERE symbol = ?", (symbol,)).fetchone()
        return row["level"] if row else None

    def set_level(self, symbol: str, level: int | None) -> None:
        self.conn.execute("REPLACE INTO zone_state (symbol, level) VALUES (?, ?)", (symbol, level))
        self.conn.commit()

    def save_snapshot(self, symbol: str, data: dict) -> None:
        self.conn.execute(
            "REPLACE INTO snapshot (symbol, data) VALUES (?, ?)",
            (symbol, json.dumps(data, ensure_ascii=False)),
        )
        self.conn.commit()

    def get_snapshot(self, symbol: str) -> dict | None:
        row = self.conn.execute("SELECT data FROM snapshot WHERE symbol = ?", (symbol,)).fetchone()
        return json.loads(row["data"]) if row else None

    def snapshots(self) -> list[dict]:
        rows = self.conn.execute("SELECT data FROM snapshot").fetchall()
        return [json.loads(r["data"]) for r in rows]

    def alert_exists(self, symbol: str, kind: str, level: int | None, market_date: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM alert WHERE symbol = ? AND kind = ? AND level IS ? AND market_date = ?",
            (symbol, kind, level, market_date),
        ).fetchone()
        return row is not None

    def add_alert(self, **fields) -> dict:
        fields.setdefault("created_at", now_kst())
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        cur = self.conn.execute(f"INSERT INTO alert ({cols}) VALUES ({marks})", tuple(fields.values()))
        self.conn.commit()
        return {"id": cur.lastrowid, **fields}

    def alerts(self, symbol: str | None = None, limit: int = 200) -> list[dict]:
        sql, args = "SELECT * FROM alert", []
        if symbol:
            sql += " WHERE symbol = ?"
            args.append(symbol)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def reset(self) -> None:
        """연습을 처음부터 다시 할 때 쓴다."""
        self.conn.executescript("DELETE FROM zone_state; DELETE FROM snapshot; DELETE FROM alert; DELETE FROM meta;")
        self.conn.commit()
