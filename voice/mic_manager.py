"""
Mic stream manager.

Keeps a single PyAudio instance and stream open so WakeListener and SpeechInput 
can share the microphone without constantly closing and reopening it (which causes issues).
"""

import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pyaudio
except ImportError:
    pyaudio = None

class SharedMic:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SharedMic, cls).__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self) -> None:
        self.pa = None
        self.stream = None
        self._read_lock = threading.Lock()
        
        if pyaudio is None:
            logger.error("pyaudio is not installed.")
            return
            
        self.pa = pyaudio.PyAudio()
        try:
            self.stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=4000,
            )
            logger.info("Shared microphone stream opened successfully.")
        except Exception as exc:
            logger.error("Failed to open shared microphone stream: %s", exc)
            self.stream = None

    def read(self, num_frames: int = 4000) -> Optional[bytes]:
        if not self.stream:
            return None
        with self._read_lock:
            try:
                # Discard stale data before returning the new chunk if needed
                # For simplicity, we just read
                return self.stream.read(num_frames, exception_on_overflow=False)
            except Exception as exc:
                logger.debug("SharedMic read error: %s", exc)
                return None

    def flush(self) -> None:
        if not self.stream:
            return
        with self._read_lock:
            try:
                available = self.stream.get_read_available()
                if available > 0:
                    self.stream.read(available, exception_on_overflow=False)
            except Exception:
                pass
