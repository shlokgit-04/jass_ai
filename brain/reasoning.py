"""
Higher-level reasoning helpers (chain-of-thought style) built on AIEngine.
"""

from __future__ import annotations

import logging
from typing import Optional

from brain.ai_engine import AIEngine

logger = logging.getLogger(__name__)


class ReasoningEngine:
    """
    Optional multi-step reasoning before action selection.
    """

    def __init__(self, ai: AIEngine) -> None:
        self._ai = ai

    def deliberate(self, question: str, context: Optional[str] = None) -> str:
        """
        Ask the model to think step-by-step, then summarize the conclusion.
        """
        parts = [
            "Think through the problem briefly, then give a clear final answer.",
            f"Question: {question}",
        ]
        if context:
            parts.append(f"Context:\n{context}")
        prompt = "\n".join(parts)
        try:
            return self._ai.generate(prompt)
        except Exception as exc:
            logger.exception("deliberate failed: %s", exc)
            return f"Reasoning unavailable: {exc}"
