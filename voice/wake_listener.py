"""
Wake word detection using Vosk with PyAudio capture (dedicated thread).

KEY DESIGN: It reads from the global `SharedMic`. When set_busy(True) is called, 
it stops reading to let SpeechInput read. When set_busy(False) is called, it resumes.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    import pyaudio
except ImportError:
    pyaudio = None  # type: ignore[misc, assignment]

try:
    from vosk import KaldiRecognizer, Model
except ImportError:
    Model = None  # type: ignore[misc, assignment]
    KaldiRecognizer = None  # type: ignore[misc, assignment]

WAKE_ALIASES = ("jass", "jazz", "jas", "jess")
CHUNK = 4000
DEFAULT_DEBOUNCE_SEC = 2.0
_MAX_BUSY_SEC = 45.0          # safety auto-release
_STREAM_RELEASE_SLEEP = 0.25  # wait after closing stream before signalling ready


class WakeListener:
    """
    Background thread that invokes ``on_wake`` when the wake word is detected.

    Mic lifecycle:
      * idle  → stream OPEN, reading audio, looking for wake word
      * busy  → stream CLOSED (mic device released for speech_input use)
      * after busy clears → stream RE-OPENED, back to listening
    """

    def __init__(
        self,
        on_wake: Callable[[], None],
        model_path: str,
        sample_rate: int = 16000,
        debounce_sec: float = DEFAULT_DEBOUNCE_SEC,
    ) -> None:
        self._on_wake = on_wake
        self._sample_rate = sample_rate
        self._model_path = (model_path or "").strip()
        self._debounce_sec = debounce_sec
        self._last_trigger = 0.0

        self._busy = False
        self._busy_since = 0.0
        self._busy_lock = threading.Lock()
        self._released = threading.Event()   # fires once stream is actually closed
        self._released.clear()

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------
    # Public control API
    # ------------------------------------------------------------------

    @staticmethod
    def is_valid_model_path(path: str) -> bool:
        p = Path(path).expanduser().resolve()
        return p.is_dir() and any(p.iterdir())

    def set_busy(self, busy: bool) -> None:
        """
        Call set_busy(True) BEFORE opening mic for command recognition.
        The method blocks until the wake-listener stream is confirmed closed
        (up to ~500 ms), so it's safe to open a new stream immediately after.
        Call set_busy(False) when command recognition is finished.
        """
        with self._busy_lock:
            self._busy = busy
            if busy:
                self._busy_since = time.monotonic()
                self._released.clear()
            else:
                self._busy_since = 0.0
                # reset debounce so partial words don't retrigger
                self._last_trigger = time.monotonic()

        if busy:
            # Wait up to 600 ms for the loop to close the stream
            self._released.wait(timeout=0.6)

    def _is_busy(self) -> bool:
        with self._busy_lock:
            if not self._busy:
                return False
            if time.monotonic() - self._busy_since > _MAX_BUSY_SEC:
                logger.warning("Wake listener busy timeout — auto-releasing")
                self._busy = False
                return False
            return True

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        if not self._model_path or not self.is_valid_model_path(self._model_path):
            logger.error(
                "Wake listener not started: invalid Vosk model path %r. "
                "Set JASS_VOSK_MODEL or place a model in ./vosk-model",
                self._model_path,
            )
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="JASS-Wake", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        if Model is None or KaldiRecognizer is None:
            logger.error("vosk Python package not installed")
            return
        if pyaudio is None:
            logger.error("pyaudio not installed")
            return

        from voice.mic_manager import SharedMic
        mic = SharedMic()

        try:
            model = Model(self._model_path)
        except Exception as exc:
            logger.exception("Vosk model load failed: %s", exc)
            return

        logger.info("Wake listener ready — say 'JASS' to activate.")

        try:
            while not self._stop.is_set():
                # ---- wait while session is active ----
                if self._is_busy():
                    self._released.set()   # signal: mic is free
                    while not self._stop.is_set() and self._is_busy():
                        time.sleep(0.05)
                    self._released.clear()
                    if self._stop.is_set():
                        break

                # Fresh recogniser for each listen window
                try:
                    rec = KaldiRecognizer(model, self._sample_rate)
                    rec.SetWords(True)
                except Exception as exc:
                    logger.exception("KaldiRecognizer init failed: %s", exc)
                    time.sleep(1.0)
                    continue

                mic.flush()

                # ---- read until stop or busy ----
                try:
                    while not self._stop.is_set() and not self._is_busy():
                        data = mic.read(CHUNK)
                        if data is None:
                            time.sleep(0.02)
                            continue
                        if rec.AcceptWaveform(data):
                            self._check_text(rec.Result())
                        else:
                            self._check_text(rec.PartialResult())
                finally:
                    # If we exited because busy, signal we stopped reading
                    if self._is_busy():
                        self._released.set()
        finally:
            pass

    def _check_text(self, res_json: str) -> None:
        try:
            obj = json.loads(res_json)
        except json.JSONDecodeError:
            return
        text = (obj.get("text") or obj.get("partial") or "").lower()
        if not text:
            return
        words = set(text.split())
        for alias in WAKE_ALIASES:
            if alias in words or text.startswith(alias):
                now = time.monotonic()
                if now - self._last_trigger < self._debounce_sec:
                    return
                self._last_trigger = now
                logger.info("Wake word detected in: %r", text)
                try:
                    self._on_wake()
                except Exception as exc:
                    logger.exception("on_wake error: %s", exc)
                return
