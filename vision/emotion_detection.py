"""
Face + emotion + coarse activity from a single BGR frame.

Uses DeepFace when available; falls back to MediaPipe face detection only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    from deepface import DeepFace
except Exception:
    DeepFace = None  # type: ignore[misc, assignment]

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[misc, assignment]


@dataclass
class VisionInsight:
    face_present: bool
    emotion: Optional[str]
    activity_hint: str


class EmotionDetector:
    def __init__(self) -> None:
        self._mp = None
        try:
            import mediapipe as mp

            self._mp = mp.solutions.face_detection.FaceDetection(
                model_selection=0,
                min_detection_confidence=0.5,
            )
        except Exception as exc:
            logger.debug("MediaPipe face detection unavailable: %s", exc)
            self._mp = None

    def close(self) -> None:
        if self._mp is not None:
            try:
                self._mp.close()
            except Exception:
                pass
            self._mp = None

    def analyze_frame(self, frame_bgr: np.ndarray) -> VisionInsight:
        if frame_bgr is None or frame_bgr.size == 0:
            return VisionInsight(False, None, "none")

        face_present = False
        emotion: Optional[str] = None

        if DeepFace is not None:
            try:
                result = DeepFace.analyze(
                    frame_bgr,
                    actions=["emotion"],
                    enforce_detection=False,
                    silent=True,
                )
                if isinstance(result, list):
                    result = result[0]
                face_present = True
                emotion = (result.get("dominant_emotion") if isinstance(result, dict) else None)
            except Exception as exc:
                logger.debug("DeepFace: %s", exc)

        if not face_present and self._mp is not None and cv2 is not None:
            try:
                rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                res = self._mp.process(rgb)
                if res.detections:
                    face_present = True
            except Exception as exc:
                logger.debug("MediaPipe: %s", exc)

        activity_hint = self._activity_from_motion(frame_bgr)
        return VisionInsight(face_present, emotion, activity_hint)

    def _activity_from_motion(self, frame: np.ndarray) -> str:
        try:
            if cv2 is None:
                return "unknown"
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            v = float(gray.var())
            if v < 50:
                return "still"
            if v < 200:
                return "low"
            return "active"
        except Exception:
            return "unknown"
