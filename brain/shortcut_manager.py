"""
Loads and applies user shortcuts from SQLite (phrase -> full expansion).
"""

from __future__ import annotations

import logging
from typing import Optional

from memory.database import Database, get_database

logger = logging.getLogger(__name__)


class ShortcutManager:
    def __init__(self, db: Optional[Database] = None) -> None:
        self._db = db or get_database()

    def register(self, phrase: str, expansion: str) -> None:
        phrase = phrase.strip().lower()
        if not phrase or not expansion.strip():
            return
        try:
            self._db.execute(
                """
                INSERT INTO shortcuts (phrase, expansion, hit_count, active)
                VALUES (?, ?, 0, 1)
                ON CONFLICT(phrase) DO UPDATE SET expansion = excluded.expansion
                """,
                (phrase, expansion.strip()),
            )
        except Exception as exc:
            logger.exception("shortcut register failed: %s", exc)

    def expand(self, text: str) -> str:
        """If text (lowered) matches a shortcut phrase exactly, return expansion."""
        key = text.strip().lower()
        if not key:
            return text
        try:
            row = self._db.fetchone(
                "SELECT expansion FROM shortcuts WHERE phrase = ? AND active = 1",
                (key,),
            )
            if row:
                self._db.execute(
                    "UPDATE shortcuts SET hit_count = hit_count + 1 WHERE phrase = ?",
                    (key,),
                )
                return str(row["expansion"])
        except Exception as exc:
            logger.exception("shortcut expand failed: %s", exc)
        return text

    def list_all(self, limit: int = 200) -> list[dict]:
        rows = self._db.fetchall(
            """
            SELECT phrase, expansion, hit_count, active FROM shortcuts
            ORDER BY hit_count DESC LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in rows]
