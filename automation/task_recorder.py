"""
Records mouse and keyboard events while learning mode is active.

Output: JSON files under ``tasks/`` with event timelines for replay.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pynput import keyboard, mouse

logger = logging.getLogger(__name__)

TASKS_DIR = Path(__file__).resolve().parent.parent / "tasks"


class TaskRecorder:
    def __init__(self, tasks_dir: Optional[Path] = None) -> None:
        self._dir = Path(tasks_dir or TASKS_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._events: List[Dict[str, Any]] = []
        self._start_ts: float = 0.0
        self._session_name: str = ""
        self._mouse_listener: Optional[mouse.Listener] = None
        self._key_listener: Optional[keyboard.Listener] = None
        self._lock = threading.Lock()
        self._active = False

    def start_session(self, name: Optional[str] = None) -> None:
        with self._lock:
            if self._active:
                return
            self._events = []
            self._start_ts = time.monotonic()
            self._session_name = name or datetime.now(timezone.utc).strftime("learned_%Y%m%d_%H%M%S")
            self._active = True

        def rel_ts() -> float:
            return round(time.monotonic() - self._start_ts, 4)

        def on_move(x, y) -> None:  # type: ignore[no-untyped-def]
            self._append({"t": rel_ts(), "type": "move", "x": int(x), "y": int(y)})

        def on_click(x, y, button, pressed) -> None:  # type: ignore[no-untyped-def]
            if pressed:
                self._append(
                    {
                        "t": rel_ts(),
                        "type": "click",
                        "x": int(x),
                        "y": int(y),
                        "button": str(button),
                    }
                )

        def on_press(key) -> None:  # type: ignore[no-untyped-def]
            try:
                ch = key.char  # type: ignore[attr-defined]
            except AttributeError:
                ch = None
            self._append(
                {
                    "t": rel_ts(),
                    "type": "key",
                    "key": str(key),
                    "char": ch,
                }
            )

        try:
            self._mouse_listener = mouse.Listener(on_move=on_move, on_click=on_click)
            self._key_listener = keyboard.Listener(on_press=on_press)
            self._mouse_listener.start()
            self._key_listener.start()
        except Exception as exc:
            logger.exception("recorder start: %s", exc)
            self._active = False

    def _append(self, ev: Dict[str, Any]) -> None:
        with self._lock:
            if self._active:
                self._events.append(ev)

    def stop_session(self) -> Optional[Path]:
        with self._lock:
            if not self._active:
                return None
            self._active = False
            name = self._session_name
            events = list(self._events)

        try:
            if self._mouse_listener:
                self._mouse_listener.stop()
            if self._key_listener:
                self._key_listener.stop()
        except Exception as exc:
            logger.debug("listener stop: %s", exc)
        finally:
            self._mouse_listener = None
            self._key_listener = None

        path = self._dir / f"{name}.json"
        try:
            path.write_text(json.dumps({"name": name, "events": events}, indent=2), encoding="utf-8")
            logger.info("Saved task recording: %s", path)
            return path
        except Exception as exc:
            logger.exception("save recording: %s", exc)
            return None
