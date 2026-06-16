"""
Local LLM integration via Ollama (default model: llama3).

Parses model output into structured actions: shell, manual_ui, background, say.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

OLLAMA_GENERATE_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_MODEL = "llama3"


class AIEngine:
    """
    Sends prompts to Ollama and normalizes responses into a small action dict.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = "http://127.0.0.1:11434",
        timeout_sec: float = 120.0,
    ) -> None:
        self.model = model
        self._generate_url = f"{base_url.rstrip('/')}/api/generate"
        self._timeout = timeout_sec

    def generate(self, prompt: str, system: Optional[str] = None, images: Optional[list[str]] = None) -> str:
        """Raw text completion from the local model."""
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system
        if images:
            payload["images"] = images
        try:
            resp = requests.post(
                self._generate_url,
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return (data.get("response") or "").strip()
        except Exception as exc:
            logger.exception("Ollama generate failed: %s", exc)
            raise

    def interpret_to_action(self, user_text: str, language: str = "en", history_context: str = "", images: Optional[list[str]] = None) -> dict[str, Any]:
        """
        Convert natural language into a single JSON action.

        Returns keys: kind (shell|manual_ui|background|say|python), payload (string).
        """
        system = self._system_prompt(language, history_context)
        prompt = f'User said: """{user_text}"""\nReply with ONE JSON object only, no markdown.'
        raw = self.generate(prompt, system=system, images=images)
        parsed = self._parse_json_loose(raw)
        if not parsed:
            # Fallback: treat whole line as shell if it looks like a command
            line = raw.strip().splitlines()[0] if raw.strip() else user_text
            if re.match(r"^[a-zA-Z0-9_./\-]+$", line.split()[0] if line.split() else ""):
                return {"kind": "shell", "payload": line}
            return {"kind": "say", "payload": raw or "I could not parse that request."}
        kind = str(parsed.get("kind", "say")).lower()
        payload = parsed.get("payload") or parsed.get("command") or ""
        if kind not in ("shell", "manual_ui", "background", "say", "python"):
            kind = "say"
        return {"kind": kind, "payload": str(payload).strip()}

    def _system_prompt(self, language: str, history_context: str = "") -> str:
        lang_note = {
            "en": "English",
            "hi": "Hindi",
            "mr": "Marathi",
            "ja": "Japanese",
        }.get(language, "English")
        
        hist_block = f"\nRecent Context:\n{history_context}\n" if history_context else ""
        
        return f"""You are JASS, a precise Linux assistant. User language preference: {lang_note}.{hist_block}
If the user's input contains obvious speech-to-text phonetic errors (like 'open termula', 'open youtub'), mentally correct them first ('open terminal', 'open youtube').
If the user references previous output, refer to Recent Context to fulfill the query.
You must output exactly one JSON object with keys:
  "kind": one of "shell", "manual_ui", "background", "say", "python"
  "payload": string

Rules:
- For opening apps or shell commands use kind "shell" and payload the full command line (e.g. "firefox").
- For opening websites, use "shell" and payload "xdg-open https://websitename.com".
- For automation (virtual mouse/keyboard/complex UI tasks) use "python" and write a robust Python script utilizing `pyautogui`, etc.
- For conversational answers use "say" and payload the spoken reply.
Examples:
User: open termula -> {{"kind":"shell","payload":"gnome-terminal"}}
User: generate python code to print hello -> {{"kind":"python","payload":"print('Hello')"}}
User: what is 2+2 -> {{"kind":"say","payload":"4"}}
Do not wrap JSON in code fences."""

    @staticmethod
    def _parse_json_loose(text: str) -> Optional[dict[str, Any]]:
        text = text.strip()
        if not text:
            return None
        # Strip markdown code fences if present
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                return None
        return None
