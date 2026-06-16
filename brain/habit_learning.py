"""
Tracks repeated normalized utterances and triggers shortcut creation after 3 hits.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from brain.shortcut_manager import ShortcutManager
from memory.habit_store import HabitStore

logger = logging.getLogger(__name__)

_THRESHOLD = 3


def _normalize_for_habit(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"^\s*jass\s+", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _suggest_shortcut_phrase(normalized: str) -> str:
    """Derive a short phrase from the first few content words."""
    stop = {"the", "a", "an", "to", "from", "and", "or", "please", "jass"}
    words = [w for w in re.findall(r"[a-zA-Z\u0900-\u097F\u3040-\u30ff]+", normalized) if w.lower() not in stop]
    if len(words) >= 2:
        return " ".join(words[:2])
    if words:
        return words[0]
    return normalized[:24] if normalized else "shortcut"


class HabitLearner:
    def __init__(
        self,
        habit_store: HabitStore,
        shortcut_manager: ShortcutManager,
        threshold: int = _THRESHOLD,
    ) -> None:
        self._store = habit_store
        self._shortcuts = shortcut_manager
        self._threshold = threshold

    def record_and_maybe_shortcut(self, utterance: str) -> Optional[str]:
        """
        Increment habit count; if threshold reached, register shortcut mapping
        short phrase -> full utterance. Returns new shortcut phrase if created.
        """
        pattern = _normalize_for_habit(utterance)
        if len(pattern) < 4:
            return None
        try:
            count = self._store.bump(pattern)
        except Exception as exc:
            logger.exception("habit bump failed: %s", exc)
            return None
        if count == self._threshold:
            phrase = _suggest_shortcut_phrase(pattern)
            try:
                self._shortcuts.register(phrase, utterance.strip())
                self._store.attach_shortcut(pattern, phrase)
                logger.info("Auto-shortcut after %s hits: %r -> %r", count, phrase, utterance)
                return phrase
            except Exception as exc:
                logger.exception("shortcut creation failed: %s", exc)
                return None
        return None
