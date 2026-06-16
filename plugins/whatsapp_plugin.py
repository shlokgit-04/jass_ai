"""
WhatsApp Web helper: opens default browser to web.whatsapp.com (silent automation optional).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class WhatsAppPlugin:
    def handles(self, text: str) -> bool:
        t = text.lower()
        return "whatsapp" in t or "whats app" in t

    def open_web(self) -> str:
        url = "https://web.whatsapp.com"
        for bin_name in ("xdg-open", "firefox", "google-chrome", "chromium"):
            path = shutil.which(bin_name)
            if path:
                try:
                    subprocess.Popen([path, url], start_new_session=True)  # noqa: S603
                    return f"Opened {url} with {bin_name}"
                except Exception as exc:
                    logger.warning("%s", exc)
        return "Could not find a browser to open WhatsApp Web."

    def handle(self, text: str) -> Optional[str]:
        if not self.handles(text):
            return None
        return self.open_web()
