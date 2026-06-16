"""
Visible desktop automation using pyautogui (mouse moves on screen).

``pyautogui`` is imported lazily so headless ``python main.py --text`` does not
require an X display at import time.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    import pyautogui as pyautogui_mod

logger = logging.getLogger(__name__)

_pyg = None


def _pyautogui():
    global _pyg
    if _pyg is None:
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        _pyg = pyautogui
    return _pyg


class ManualEngine:
    def run_sequence(self, payload: str) -> str:
        steps = [s.strip() for s in payload.split(";") if s.strip()]
        if not steps:
            return "No manual steps provided."
        errors: List[str] = []
        for i, step in enumerate(steps):
            try:
                self._run_step(step)
            except Exception as exc:
                logger.exception("manual step %s failed: %s", step, exc)
                errors.append(f"step {i+1} ({step}): {exc}")
        if errors:
            return "Some steps failed: " + "; ".join(errors)
        return "Manual sequence completed."

    def _run_step(self, step: str) -> None:
        pyautogui = _pyautogui()
        lower = step.lower()
        if lower.startswith("move:"):
            rest = step.split(":", 1)[1]
            x_str, y_str = rest.split(",", 1)
            x, y = int(float(x_str.strip())), int(float(y_str.strip()))
            pyautogui.moveTo(x, y, duration=0.35)
        elif lower == "click":
            pyautogui.click()
        elif lower == "rightclick":
            pyautogui.rightClick()
        elif lower.startswith("type:"):
            text = step.split(":", 1)[1]
            pyautogui.typewrite(text, interval=0.02)
        elif lower.startswith("key:"):
            key = step.split(":", 1)[1].strip()
            pyautogui.press(key)
        elif lower.startswith("sleep:"):
            time.sleep(float(step.split(":", 1)[1].strip()))
        else:
            raise ValueError(f"Unknown manual step: {step}")
