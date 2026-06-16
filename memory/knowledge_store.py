"""
Simple knowledge snippets for RAG-style augmentation (embedding_ref reserved).
"""

from __future__ import annotations

import logging
from typing import Optional

from memory.database import Database, get_database

logger = logging.getLogger(__name__)


class KnowledgeStore:
    def __init__(self, db: Optional[Database] = None) -> None:
        self._db = db or get_database()

    def add(self, topic: str, content: str, embedding_ref: Optional[str] = None) -> None:
        try:
            self._db.execute(
                """
                INSERT OR IGNORE INTO knowledge (topic, content, embedding_ref)
                VALUES (?, ?, ?)
                """,
                (topic, content, embedding_ref),
            )
        except Exception as exc:
            logger.exception("knowledge_store.add failed: %s", exc)

    def search_topic(self, topic_substring: str, limit: int = 20) -> list[dict]:
        like = f"%{topic_substring}%"
        rows = self._db.fetchall(
            """
            SELECT * FROM knowledge WHERE topic LIKE ? ORDER BY id DESC LIMIT ?
            """,
            (like, limit),
        )
        return [dict(r) for r in rows]
