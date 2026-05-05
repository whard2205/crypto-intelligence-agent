from __future__ import annotations
import json
import os
import aiosqlite


class ReportHistoryRepository:
    """Async SQLite-backed store for IntelligenceReport records."""

    def __init__(self, db_path: str = "data/report_history.db") -> None:
        self._db_path = db_path

    async def init_db(self) -> None:
        parent = os.path.dirname(self._db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS report_history (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id           TEXT NOT NULL,
                    symbol           TEXT NOT NULL,
                    market_bias      TEXT,
                    confidence_score REAL,
                    llm_used         INTEGER DEFAULT 0,
                    report_json      TEXT NOT NULL,
                    generated_at     TEXT NOT NULL,
                    is_error         INTEGER DEFAULT 0
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_symbol_generated
                    ON report_history (symbol, generated_at DESC)
                """
            )
            await db.commit()

    async def save(self, report: dict) -> None:
        is_error = 1 if report.get("error") else 0
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO report_history
                    (run_id, symbol, market_bias, confidence_score,
                     llm_used, report_json, generated_at, is_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.get("run_id", ""),
                    report.get("symbol", ""),
                    report.get("market_bias"),
                    report.get("confidence_score"),
                    1 if report.get("llm_used") else 0,
                    json.dumps(report),
                    report.get("generated_at", ""),
                    is_error,
                ),
            )
            await db.commit()
        await self.prune(report.get("symbol", ""))

    async def get_latest(self, symbol: str, limit: int = 10) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT report_json FROM report_history
                WHERE symbol = ?
                ORDER BY generated_at DESC
                LIMIT ?
                """,
                (symbol, limit),
            )
            rows = await cursor.fetchall()
        return [json.loads(row["report_json"]) for row in rows]

    async def prune(self, symbol: str, keep: int = 100) -> None:
        """Delete rows beyond `keep` newest per symbol."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                DELETE FROM report_history
                WHERE symbol = ?
                  AND id NOT IN (
                      SELECT id FROM report_history
                      WHERE symbol = ?
                      ORDER BY generated_at DESC
                      LIMIT ?
                  )
                """,
                (symbol, symbol, keep),
            )
            await db.commit()
