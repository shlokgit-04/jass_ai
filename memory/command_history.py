"""
Persistent logging of all interpreted commands and outcomes.
"""

from __future__ import annotations

import logging
from typing import Optional

from memory.database import Database, get_database

logger = logging.getLogger(__name__)


class CommandHistoryStore:
    """Append-only style command log backed by SQLite."""

    def __init__(self, db: Optional[Database] = None) -> None:
        self._db = db or get_database()

    def log(
        self,
        source: str,
        raw_text: Optional[str],
        normalized_command: Optional[str],
        result_status: str,
        details: Optional[str] = None,
    ) -> None:
        try:
            self._db.execute(
                """
                INSERT INTO command_history
                    (source, raw_text, normalized_command, result_status, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source, raw_text, normalized_command, result_status, details),
            )
        except Exception as exc:
            logger.exception("command_history.log failed: %s", exc)

    def recent(self, limit: int = 100) -> list[dict]:
        rows = self._db.fetchall(
            """
            SELECT * FROM command_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in rows]
