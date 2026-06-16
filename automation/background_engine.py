"""
Silent automation: headless browser tasks via Playwright and simple HTTP GET.

Runs without visible browser window where possible.
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_sync_playwright = None
try:
    from playwright.sync_api import sync_playwright as _sync_playwright
except ImportError:
    pass


class BackgroundEngine:
    """
    Parses ``payload``:

    - ``http://`` or ``https://`` — fetch URL (requests); optional prefix ``play:`` for Playwright.
    - ``play:https://example.com`` — headless Chromium navigate + title
    """

    def run_action(self, payload: str) -> str:
        payload = payload.strip()
        if not payload:
            return "No background action."
        use_playwright = False
        target = payload
        if payload.lower().startswith("play:"):
            use_playwright = True
            target = payload.split(":", 1)[1].strip()

        parsed = urlparse(target)
        if parsed.scheme not in ("http", "https"):
            return "Background mode expects a URL or play:URL."

        if use_playwright:
            return self._playwright_fetch(target)
        return self._http_fetch(target)

    def _http_fetch(self, url: str) -> str:
        try:
            r = requests.get(url, timeout=30)
            return f"GET {url} -> {r.status_code}, {len(r.content)} bytes"
        except Exception as exc:
            logger.exception("http fetch: %s", exc)
            return f"HTTP error: {exc}"

    def _playwright_fetch(self, url: str) -> str:
        if _sync_playwright is None:
            return "Playwright not installed. Run: playwright install chromium"
        try:
            with _sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    title: Optional[str] = page.title()
                    return f"Playwright: title={title!r}"
                finally:
                    browser.close()
        except Exception as exc:
            logger.exception("playwright: %s", exc)
            return f"Playwright error: {exc}"
