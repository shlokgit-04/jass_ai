"""
Screen capture utilities (OpenCV / pyautogui) for context-aware automation.

Provides a downscaled BGR frame of the primary monitor for optional vision pipelines.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[misc, assignment]

try:
    import pyautogui
except ImportError:
    pyautogui = None  # type: ignore[misc, assignment]


class ScreenReader:
    def grab_region_bgr(
        self,
        region: Optional[Tuple[int, int, int, int]] = None,
        max_width: int = 640,
    ) -> Optional[np.ndarray]:
        """
        Capture screen as BGR numpy array, optionally resized to ``max_width``.
        ``region`` is (left, top, width, height) in pyautogui coordinates.
        """
        if pyautogui is None:
            logger.error("pyautogui not available for screen capture")
            return None
        try:
            shot = pyautogui.screenshot(region=region)
            frame = np.array(shot)[:, :, ::-1].copy()
            if cv2 is not None and max_width > 0:
                h, w = frame.shape[:2]
                if w > max_width:
                    scale = max_width / float(w)
                    frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
            return frame
        except Exception as exc:
            logger.exception("screen grab failed: %s", exc)
            return None
