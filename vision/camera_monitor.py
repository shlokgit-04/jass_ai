"""
Webcam capture loop on a worker thread; delivers BGR frames to a callback.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[misc, assignment]

FrameCallback = Callable[[np.ndarray], None]


class CameraMonitor:
    def __init__(self, device_index: int = 0, fps_limit: float = 5.0) -> None:
        self._device = device_index
        self._fps_limit = fps_limit
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._callback: Optional[FrameCallback] = None

    def set_callback(self, cb: Optional[FrameCallback]) -> None:
        self._callback = cb

    def start(self) -> None:
        if cv2 is None:
            logger.error("opencv-python not installed")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="JASS-Camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def _loop(self) -> None:
        cap = cv2.VideoCapture(self._device)
        if not cap.isOpened():
            logger.error("Cannot open camera index %s", self._device)
            return
        import time

        min_interval = 1.0 / max(self._fps_limit, 0.1)
        last = 0.0
        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    time.sleep(0.05)
                    continue
                now = time.monotonic()
                if now - last < min_interval:
                    continue
                last = now
                if self._callback is not None:
                    try:
                        self._callback(frame)
                    except Exception as exc:
                        logger.debug("frame callback: %s", exc)
        finally:
            cap.release()
