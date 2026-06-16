"""
Spotify control on Linux via ``playerctl`` when available (DBus MPRIS).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class SpotifyPlugin:
    def __init__(self) -> None:
        self._playerctl = shutil.which("playerctl")

    def available(self) -> bool:
        return self._playerctl is not None

    def play_pause(self) -> str:
        return self._run(["play-pause"])

    def next_track(self) -> str:
        return self._run(["next"])

    def previous_track(self) -> str:
        return self._run(["previous"])

    def play_uri(self, uri: str) -> str:
        return self._run(["open", uri])

    def _run(self, args: list[str]) -> str:
        if not self._playerctl:
            return "Install playerctl and run Spotify for MPRIS control."
        try:
            cmd = [self._playerctl, "-p", "spotify", *args]
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=15)
            return "OK"
        except subprocess.CalledProcessError as exc:
            logger.warning("playerctl: %s", exc)
            return (exc.stderr or exc.stdout or str(exc))[:500]
        except Exception as exc:
            return str(exc)

    def handles_phrase(self, text: str) -> bool:
        t = text.lower()
        return "spotify" in t and any(
            k in t for k in ("play", "pause", "next", "previous", "track", "music")
        )

    def handle(self, text: str) -> Optional[str]:
        if not self.handles_phrase(text):
            return None
        tl = text.lower()
        if "pause" in tl or "stop" in tl:
            return self.play_pause()
        if "next" in tl:
            return self.next_track()
        if "previous" in tl or "back" in tl:
            return self.previous_track()
        if "play" in tl:
            return self.play_pause()
        return self.play_pause()
