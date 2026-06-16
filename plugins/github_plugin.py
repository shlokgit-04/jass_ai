"""
GitHub API helper: shallow read-only operations via HTTPS + token (optional).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class GitHubPlugin:
    def __init__(self, token: Optional[str] = None) -> None:
        self._token = token or os.environ.get("GITHUB_TOKEN", "")

    def handles(self, text: str) -> bool:
        t = text.lower()
        return "github" in t and any(k in t for k in ("repo", "issue", "pull", "star"))

    def handle(self, text: str) -> Optional[str]:
        if not self.handles(text):
            return None
        # Minimal demo: list authenticated user if token set
        if not self._token:
            return "Set GITHUB_TOKEN for GitHub integration."
        try:
            r = requests.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=20,
            )
            r.raise_for_status()
            data: dict[str, Any] = r.json()
            return f"GitHub user: {data.get('login')}"
        except Exception as exc:
            logger.exception("github: %s", exc)
            return f"GitHub error: {exc}"
