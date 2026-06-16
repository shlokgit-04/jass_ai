"""
Replays recorded JSON tasks using pyautogui.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TASKS_DIR = Path(__file__).resolve().parent.parent / "tasks"


class TaskReplay:
    def __init__(self, tasks_dir: Optional[Path] = None) -> None:
        self._dir = Path(tasks_dir or TASKS_DIR)

    def list_tasks(self) -> List[str]:
        if not self._dir.is_dir():
            return []
        return sorted(p.stem for p in self._dir.glob("*.json"))

    def replay_by_name(self, name: str) -> Tuple[bool, str]:
        path = self._dir / f"{name}.json"
        if not path.is_file():
            path = self._dir / name
            if not path.is_file():
                return False, f"Task not found: {name}"
        return self.replay_file(path)

    def replay_file(self, path: Path) -> Tuple[bool, str]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return False, f"Invalid JSON: {exc}"
        events: List[Dict[str, Any]] = data.get("events") or []
        if not events:
            return False, "No events in file."
        last_t = 0.0
        try:
            import pyautogui

            for ev in events:
                t = float(ev.get("t", 0))
                delay = max(0.0, t - last_t)
                if delay:
                    time.sleep(delay)
                last_t = t
                typ = ev.get("type")
                if typ == "move":
                    pyautogui.moveTo(int(ev["x"]), int(ev["y"]), duration=0.1)
                elif typ == "click":
                    pyautogui.moveTo(int(ev["x"]), int(ev["y"]), duration=0.1)
                    pyautogui.click()
                elif typ == "key":
                    ch = ev.get("char")
                    if ch:
                        pyautogui.typewrite(ch, interval=0.02)
            return True, f"Replayed {len(events)} events from {path.name}."
        except Exception as exc:
            logger.exception("replay failed: %s", exc)
            return False, str(exc)
