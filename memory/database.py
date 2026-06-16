"""
JASS SQLite database layer.

Creates and manages the canonical schema: command_history, shortcuts, tasks,
habits, knowledge. All command-like events should be logged via this layer.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Iterable, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jass" / "jass.db"


class Database:
    """
    Thread-safe SQLite access with WAL mode for better concurrent reads/writes.
    """

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self._path = Path(db_path or _DEFAULT_DB_PATH)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self._path),
            check_same_thread=False,
            timeout=30.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        with self._lock:
            conn = self._connect()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _ensure_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS command_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    source TEXT NOT NULL,
                    raw_text TEXT,
                    normalized_command TEXT,
                    result_status TEXT,
                    details TEXT
                );

                CREATE TABLE IF NOT EXISTS shortcuts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    phrase TEXT NOT NULL UNIQUE,
                    expansion TEXT NOT NULL,
                    hit_count INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    name TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    last_run_at TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS habits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    pattern TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 1,
                    last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
                    shortcut_phrase TEXT
                );

                CREATE TABLE IF NOT EXISTS knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding_ref TEXT,
                    UNIQUE(topic, content)
                );

                CREATE INDEX IF NOT EXISTS idx_command_history_created
                    ON command_history(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_habits_pattern ON habits(pattern);
                """
            )

    def execute(
        self,
        sql: str,
        params: Iterable[Any] | tuple = (),
    ) -> sqlite3.Cursor:
        with self.connection() as conn:
            cur = conn.execute(sql, tuple(params))
            return cur

    def fetchall(self, sql: str, params: Iterable[Any] | tuple = ()) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return list(conn.execute(sql, tuple(params)).fetchall())

    def fetchone(
        self,
        sql: str,
        params: Iterable[Any] | tuple = (),
    ) -> Optional[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(sql, tuple(params)).fetchone()


# Singleton-style default instance (main.py may inject another path)
_default_db: Optional[Database] = None


def get_database(db_path: Optional[Path | str] = None) -> Database:
    global _default_db
    if _default_db is None or db_path is not None:
        _default_db = Database(db_path)
    return _default_db
