"""기록 저장소 (SQLite). 종목별 현재 구간, 3분할 계획, 알림 이력을 남긴다.

연습 "처음부터"는 구간·알림 기록만 지우고 3분할 계획은 남긴다."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- 종목별로 지금 들어가 있는 가장 깊은 알림 구간, 경계선 여유 반영 (없으면 NULL)
CREATE TABLE IF NOT EXISTS zone_state (
    symbol TEXT PRIMARY KEY,
    level INTEGER
);
-- 내 종목별 지금 들어가 있는 수익(+)·손실(-) 구간과 그때의 평단
CREATE TABLE IF NOT EXISTS holding_state (
    symbol TEXT PRIMARY KEY,
    level INTEGER,
    avg_price REAL NOT NULL
);
-- 종목별 3분할 총 투자금 (원)
CREATE TABLE IF NOT EXISTS split_plan (
    symbol TEXT PRIMARY KEY,
    total_krw INTEGER NOT NULL
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

    def get_holding_state(self, symbol: str) -> dict | None:
        row = self.conn.execute("SELECT level, avg_price FROM holding_state WHERE symbol = ?", (symbol,)).fetchone()
        return dict(row) if row else None

    def set_holding_state(self, symbol: str, level: int | None, avg_price: float) -> None:
        self.conn.execute("REPLACE INTO holding_state (symbol, level, avg_price) VALUES (?, ?, ?)",
                          (symbol, level, avg_price))
        self.conn.commit()

    def get_split_total(self, symbol: str) -> int | None:
        row = self.conn.execute("SELECT total_krw FROM split_plan WHERE symbol = ?", (symbol,)).fetchone()
        return row["total_krw"] if row else None

    def set_split_total(self, symbol: str, total_krw: int | None) -> None:
        if total_krw:
            self.conn.execute("REPLACE INTO split_plan (symbol, total_krw) VALUES (?, ?)", (symbol, total_krw))
        else:
            self.conn.execute("DELETE FROM split_plan WHERE symbol = ?", (symbol,))
        self.conn.commit()

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
        self.conn.executescript("DELETE FROM zone_state; DELETE FROM holding_state; DELETE FROM alert; DELETE FROM meta;")
        self.conn.commit()
