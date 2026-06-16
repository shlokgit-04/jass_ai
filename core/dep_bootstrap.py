"""
Verify and install required Python packages at startup (best-effort).

Uses the same interpreter as the running process so venvs stay consistent.
"""

from __future__ import annotations

import importlib
import logging
import subprocess
import sys
from typing import Iterable, Tuple

logger = logging.getLogger(__name__)

# (import_name, pip_distribution_name)
REQUIRED_PACKAGES: Tuple[Tuple[str, str], ...] = (
    ("PyQt6", "PyQt6"),
    ("speech_recognition", "SpeechRecognition"),
    ("vosk", "vosk"),
    ("pyaudio", "PyAudio"),
    ("pyautogui", "pyautogui"),
    ("requests", "requests"),
    ("uvicorn", "uvicorn[standard]"),
    ("fastapi", "fastapi"),
    ("psutil", "psutil"),
    ("websockets", "websockets"),
    ("cv2", "opencv-python"),
    ("pynput", "pynput"),
    ("numpy", "numpy"),
    ("pyttsx3", "pyttsx3"),
)


def _try_import(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False


def ensure_dependencies(extra: Iterable[Tuple[str, str]] = ()) -> list[str]:
    """
    Import each required module; pip-install on failure.

    Returns a list of human-readable issues (empty if all satisfied after attempts).
    """
    issues: list[str] = []
    for mod, pip_name in (*REQUIRED_PACKAGES, *extra):
        if _try_import(mod):
            continue
        logger.warning("Missing dependency %s; installing %s …", mod, pip_name)
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", pip_name],
                check=True,
                timeout=600,
            )
        except Exception as exc:
            msg = f"Could not install {pip_name}: {exc}"
            logger.error(msg)
            issues.append(msg)
            continue
        if not _try_import(mod):
            issues.append(f"Installed {pip_name} but import {mod} still fails.")
    return issues
