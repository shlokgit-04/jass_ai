"""
Habit frequency storage — pairs with brain.habit_learning for shortcut creation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from memory.database import Database, get_database

logger = logging.getLogger(__name__)


class HabitStore:
    def __init__(self, db: Optional[Database] = None) -> None:
        self._db = db or get_database()

    def bump(self, pattern: str) -> int:
        """Increment habit count for normalized pattern; return new count."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            row = self._db.fetchone(
                "SELECT id, count FROM habits WHERE pattern = ?",
                (pattern,),
            )
            if row is None:
                self._db.execute(
                    """
                    INSERT INTO habits (pattern, count, last_seen_at)
                    VALUES (?, 1, ?)
                    """,
                    (pattern, now),
                )
                return 1
            new_count = int(row["count"]) + 1
            self._db.execute(
                """
                UPDATE habits SET count = ?, last_seen_at = ? WHERE id = ?
                """,
                (new_count, now, row["id"]),
            )
            return new_count
        except Exception as exc:
            logger.exception("habit_store.bump failed: %s", exc)
            return 0

    def attach_shortcut(self, pattern: str, shortcut_phrase: str) -> None:
        try:
            self._db.execute(
                """
                UPDATE habits SET shortcut_phrase = ? WHERE pattern = ?
                """,
                (shortcut_phrase, pattern),
            )
        except Exception as exc:
            logger.exception("habit_store.attach_shortcut failed: %s", exc)

    def list_habits(self, limit: int = 50) -> list[dict]:
        rows = self._db.fetchall(
            """
            SELECT * FROM habits ORDER BY count DESC LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in rows]
