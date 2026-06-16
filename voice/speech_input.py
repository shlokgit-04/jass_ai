"""
Speech-to-text after the wake word.

Default engine: **vosk** (offline, uses same model as wake listener).
Can be overridden with JASS_STT_ENGINE=google for Google Web API (needs internet).

Model caching: The Vosk Model object is cached globally per path so it loads
only once (shared with wake_listener which loads its own instance — both are
lightweight to keep open at the same model path).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import speech_recognition as sr
except ImportError:
    sr = None  # type: ignore[misc, assignment]

LOCALE_MAP = {
    "en": "en-US",
    "hi": "hi-IN",
    "mr": "mr-IN",
    "ja": "ja-JP",
}

# Global model cache: path → vosk.Model instance
_VOSK_MODEL_CACHE: dict[str, object] = {}
_VOSK_CACHE_LOCK = threading.Lock()


def _get_vosk_model(path: str):
    """Return cached Vosk Model, loading once on first call."""
    with _VOSK_CACHE_LOCK:
        if path not in _VOSK_MODEL_CACHE:
            from vosk import Model
            logger.info("Loading Vosk STT model from %s (first time)…", path)
            _VOSK_MODEL_CACHE[path] = Model(path)
        return _VOSK_MODEL_CACHE[path]


class SpeechInput:
    """
    Captures audio from the default microphone and returns transcribed text.

    Default engine: vosk (offline). Set JASS_STT_ENGINE=google for online Google STT.
    """

    def __init__(
        self,
        energy_threshold: int = 300,
        pause_threshold: float = 0.5,
        vosk_model: Optional[Path] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._recognizer: Optional["sr.Recognizer"] = None
        self._mic: Optional["sr.Microphone"] = None
        self._calibrated = False
        self._last_error: Optional[str] = None
        self._vosk_model = Path(vosk_model).resolve() if vosk_model else None

        # Default to vosk (offline) if model is available, otherwise google
        env_engine = os.environ.get("JASS_STT_ENGINE", "").strip().lower()
        if env_engine:
            self._stt_engine = env_engine
        elif self._vosk_model and self._vosk_model.is_dir():
            self._stt_engine = "vosk"
            logger.info("STT engine: vosk (offline, model found at %s)", self._vosk_model)
        else:
            self._stt_engine = "google"
            logger.info("STT engine: google (no vosk model found)")

        if sr is None:
            self._last_error = "speech_recognition not installed"
            return
        try:
            self._recognizer = sr.Recognizer()
            self._recognizer.energy_threshold = energy_threshold
            self._recognizer.pause_threshold = pause_threshold
            self._mic = sr.Microphone()
        except Exception as exc:
            logger.exception("SpeechInput init failed: %s", exc)
            self._last_error = str(exc)
            self._recognizer = None
            self._mic = None

    @property
    def available(self) -> bool:
        if self._stt_engine == "vosk" and self._vosk_model and self._vosk_model.is_dir():
            try:
                import pyaudio  # noqa: F401
                return True
            except ImportError:
                return False
        return self._recognizer is not None and self._mic is not None

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def engine_label(self) -> str:
        return self._stt_engine

    def _listen_vosk_phrase(self, timeout: float, phrase_time_limit: float) -> Optional[str]:
        """Record from mic with SharedMic + Vosk until silence or time limit."""
        try:
            import pyaudio
            from vosk import KaldiRecognizer
        except ImportError as exc:
            self._last_error = str(exc)
            logger.error("Vosk STT missing dependency: %s", exc)
            return None

        if not self._vosk_model or not self._vosk_model.is_dir():
            logger.error("Vosk STT: no model directory at %s", self._vosk_model)
            return None

        CHUNK = 4000
        sample_rate = 16000

        try:
            model = _get_vosk_model(str(self._vosk_model))
            rec = KaldiRecognizer(model, sample_rate)
        except Exception as exc:
            logger.exception("Vosk STT: recognizer init failed: %s", exc)
            return None
            
        from voice.mic_manager import SharedMic
        mic = SharedMic()
        mic.flush()

        logger.info("Vosk STT: listening (timeout=%.1fs, limit=%.1fs)…", timeout, phrase_time_limit)
        t_start = time.monotonic()
        t_speech_start: Optional[float] = None
        last_partial = ""
        deadline = t_start + timeout + phrase_time_limit

        try:
            while time.monotonic() < deadline:
                data = mic.read(CHUNK)
                if data is None:
                    time.sleep(0.02)
                    continue

                if rec.AcceptWaveform(data):
                    result_text = json.loads(rec.Result()).get("text", "").strip()
                    if result_text:
                        logger.info("Vosk STT result: %r", result_text)
                        return result_text
                else:
                    partial = json.loads(rec.PartialResult()).get("partial", "").strip()
                    if partial and partial != last_partial:
                        last_partial = partial
                        if t_speech_start is None:
                            t_speech_start = time.monotonic()
                        # If we have partial text and hit phrase_time_limit, stop
                        if time.monotonic() - t_speech_start >= phrase_time_limit:
                            break

            # Flush final result
            final = json.loads(rec.FinalResult()).get("text", "").strip()
            out = (final or last_partial).strip()
            if out:
                logger.info("Vosk STT final: %r", out)
            else:
                logger.info("Vosk STT: no speech detected in window")
            return out or None
        finally:
            pass

    def listen_once(
        self,
        language: str = "en",
        timeout: float = 8.0,
        phrase_time_limit: float = 15.0,
    ) -> Optional[str]:
        """Block until a phrase is recognized, return text or None."""
        if self._stt_engine == "vosk":
            with self._lock:
                return self._listen_vosk_phrase(
                    timeout=timeout, phrase_time_limit=phrase_time_limit
                )

        # Google / fallback
        if not self._recognizer or not self._mic or sr is None:
            logger.error("Speech recognizer not initialized (engine=%s)", self._stt_engine)
            return None
        locale = LOCALE_MAP.get(language, LOCALE_MAP["en"])

        with self._lock:
            with self._mic as source:
                if not self._calibrated:
                    try:
                        self._recognizer.adjust_for_ambient_noise(source, duration=0.4)
                    except Exception as exc:
                        logger.warning("Ambient calibration skipped: %s", exc)
                    self._calibrated = True
                try:
                    audio = self._recognizer.listen(
                        source,
                        timeout=timeout,
                        phrase_time_limit=phrase_time_limit,
                    )
                except sr.WaitTimeoutError:
                    logger.info("STT: no speech heard before timeout")
                    return None
                except Exception as exc:
                    self._last_error = str(exc)
                    logger.exception("listen failed: %s", exc)
                    return None

            try:
                text = self._recognizer.recognize_google(audio, language=locale)
                out = text.strip()
                logger.info("Google STT (%s): %r", locale, out)
                return out
            except sr.UnknownValueError:
                logger.info("STT: could not understand audio")
                return None
            except sr.RequestError as exc:
                self._last_error = str(exc)
                logger.warning(
                    "Google STT network error: %s — set JASS_STT_ENGINE=vosk for offline", exc
                )
                return None
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("recognize_google failed: %s", exc)
                return None
