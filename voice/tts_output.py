"""
Text-to-speech: pyttsx3 when it works; on Linux falls back to ``espeak-ng`` /
``espeak`` / ``spd-say`` so audio works without ``aplay`` (common pyttsx3 failure).

Install examples (Debian/Kali)::

    sudo apt install espeak-ng alsa-utils
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[misc, assignment]

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None  # type: ignore[misc, assignment]

try:
    from gtts import gTTS
except ImportError:
    gTTS = None  # type: ignore[misc, assignment]


def _shell_safe_text(text: str, max_len: int = 4000) -> str:
    t = text.strip()
    if len(t) > max_len:
        t = t[:max_len] + "…"
    return t


def _linux_aplay_missing() -> bool:
    return sys.platform.startswith("linux") and shutil.which("aplay") is None


class TTSOutput:
    """
    Thread-safe TTS. Prefers ``JASS_TTS_BACKEND=pyttsx3|espeak|auto`` (default auto).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._init_error: Optional[str] = None
        self._engine = None
        self._pyttsx3_ok = False
        self._espeak_bin: Optional[str] = None
        self._spd_say_bin: Optional[str] = None

        want = os.environ.get("JASS_TTS_BACKEND", "auto").strip().lower()

        for name in ("espeak-ng", "espeak"):
            p = shutil.which(name)
            if p:
                self._espeak_bin = p
                break
        self._spd_say_bin = shutil.which("spd-say")

        if (
            want == "auto"
            and _linux_aplay_missing()
            and not self._espeak_bin
            and not self._spd_say_bin
        ):
            logger.warning(
                "TTS: no `aplay` and no espeak-ng — install: sudo apt install espeak-ng "
                "(or alsa-utils for aplay)"
            )

        # pyttsx3's espeak driver shells out to `aplay`; if it's missing you get
        # "sh: 1: aplay: not found" and no audio. Skip pyttsx3 playback when we can use espeak directly.
        self._skip_pyttsx3_playback = False
        if want == "auto" and _linux_aplay_missing() and self._espeak_bin:
            self._skip_pyttsx3_playback = True
            logger.info(
                "TTS: `aplay` not found — using %s directly (no pyttsx3 shell). "
                "For pyttsx3 instead: sudo apt install alsa-utils",
                self._espeak_bin,
            )

        if pyttsx3 is None:
            self._init_error = "pyttsx3 not installed"
        elif want == "espeak":
            self._init_error = "JASS_TTS_BACKEND=espeak (using espeak, not pyttsx3)"
        elif self._skip_pyttsx3_playback:
            self._init_error = "pyttsx3 skipped (no aplay); using espeak-ng"
        else:
            try:
                self._engine = pyttsx3.init()
                self._prefer_female_voice()
                self._pyttsx3_ok = True
            except Exception as exc:
                logger.warning("pyttsx3 init failed (will try espeak): %s", exc)
                self._init_error = str(exc)
                self._engine = None

        if want == "espeak" or self._skip_pyttsx3_playback or (not self._pyttsx3_ok and self._espeak_bin):
            logger.info("TTS: primary speech via %s", self._espeak_bin or self._spd_say_bin or "spd-say")

    def _prefer_female_voice(self) -> None:
        if not self._engine:
            return
        try:
            voices = self._engine.getProperty("voices") or []
            chosen = None
            for v in voices:
                name = (v.name or "") + " " + (getattr(v, "id", "") or "")
                name_low = name.lower()
                if any(
                    k in name_low
                    for k in ("female", "zira", "samantha", "karen", "veena", "hiroko", "kyoko")
                ):
                    chosen = v
                    break
            if chosen is None and voices:
                chosen = voices[1] if len(voices) > 1 else voices[0]
            if chosen:
                self._engine.setProperty("voice", chosen.id)
            self._engine.setProperty("rate", 175)
        except Exception as exc:
            logger.debug("voice select: %s", exc)

    def _speak_espeak(self, text: str) -> bool:
        if not self._espeak_bin:
            return False
        voice = os.environ.get("JASS_ESPEAK_VOICE", "en+f3").strip() or "en+f3"
        safe = _shell_safe_text(text)
        try:
            subprocess.run(
                [self._espeak_bin, "-s", "160", "-v", voice, safe],
                check=False,
                timeout=120,
                capture_output=True,
                text=True,
            )
            return True
        except Exception as exc:
            logger.warning("espeak failed: %s", exc)
            return False

    def _speak_spd(self, text: str) -> bool:
        if not self._spd_say_bin:
            return False
        safe = _shell_safe_text(text)
        try:
            subprocess.run(
                [self._spd_say_bin, "-w", safe],
                check=False,
                timeout=120,
                capture_output=True,
                text=True,
            )
            return True
        except Exception as exc:
            logger.warning("spd-say failed: %s", exc)
            return False

    def _speak_gtts(self, text: str) -> bool:
        if gTTS is None or _linux_aplay_missing():
            # Or if mpg123 is missing, but maybe we have it. Let's rely on simple play/aplay/mpg123
            return False
        mpg = shutil.which("mpg123") or shutil.which("aplay")
        if not mpg:
            return False
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".mp3" if "mpg123" in mpg else ".wav", delete=False) as f:
                tmp = f.name
            tts = gTTS(text, lang='en')
            tts.save(tmp)
            subprocess.run([mpg, tmp], check=False, timeout=120, capture_output=True)
            os.unlink(tmp)
            return True
        except Exception as exc:
            logger.warning("gTTS failed: %s", exc)
            return False

    def _speak_edge_tts(self, text: str) -> bool:
        safe = _shell_safe_text(text)
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp = f.name
            
            # Find edge-tts in venv or path
            import sys
            venv_bin = os.path.dirname(sys.executable)
            edge_tts_bin = os.path.join(venv_bin, "edge-tts")
            if not os.path.exists(edge_tts_bin):
                edge_tts_bin = shutil.which("edge-tts")
            
            if not edge_tts_bin or pygame is None:
                return False

            cmd = [edge_tts_bin, "--voice", "en-US-AriaNeural", "--text", safe, "--write-media", tmp]
            subprocess.run(cmd, check=True, timeout=30, capture_output=True)
            
            pygame.mixer.init()
            pygame.mixer.music.load(tmp)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            pygame.mixer.music.unload()
            
            os.unlink(tmp)
            return True
        except Exception as exc:
            logger.warning("edge-tts failed: %s", exc)
            try:
                if 'tmp' in locals():
                    os.unlink(tmp)
            except Exception:
                pass
            return False

    def _speak_pyttsx3(self, text: str) -> bool:
        if not self._engine:
            return False
        try:
            self._engine.say(text)
            self._engine.runAndWait()
            return True
        except Exception as exc:
            logger.warning("pyttsx3 speak failed: %s", exc)
            return False

    def speak(self, text: str, block: bool = False) -> None:
        if not text.strip():
            return

        want = os.environ.get("JASS_TTS_BACKEND", "auto").strip().lower()

        def _run() -> None:
            with self._lock:
                ok = False
                if want == "espeak" or self._skip_pyttsx3_playback:
                    ok = self._speak_espeak(text) or self._speak_spd(text)
                elif want == "pyttsx3" and self._pyttsx3_ok:
                    ok = self._speak_pyttsx3(text)
                else:
                    if not ok:
                        ok = self._speak_edge_tts(text)
                    if self._pyttsx3_ok and not self._skip_pyttsx3_playback and not ok:
                        ok = self._speak_pyttsx3(text)
                    if not ok:
                        ok = self._speak_espeak(text)
                    if not ok:
                        ok = self._speak_spd(text)
                    if not ok:
                        ok = self._speak_gtts(text)
                if not ok:
                    logger.error(
                        "TTS: no working backend. Run: sudo apt install espeak-ng "
                        "(and alsa-utils if you want pyttsx3)."
                    )

        if block:
            _run()
        else:
            threading.Thread(target=_run, name="JASS-TTS", daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            if self._engine:
                try:
                    self._engine.stop()
                except Exception:
                    pass
