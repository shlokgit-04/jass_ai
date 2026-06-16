"""
Futuristic floating assistant orb: glow, particles, state-based motion.

States: idle (breathing), listening (ripple), speaking (wave pulse), processing (rotating ring).
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional

from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QApplication, QWidget


class OrbState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    SPEAKING = "speaking"
    PROCESSING = "processing"
    ERROR = "error"


_ORB_DIAM = 70
_MARGIN = 28
_WIDGET = _ORB_DIAM + _MARGIN * 2

_STATE_CORE = {
    OrbState.IDLE: (QColor("#5B21B6"), QColor("#3B82F6"), QColor("#7C3AED")),
    OrbState.LISTENING: (QColor("#2563EB"), QColor("#60A5FA"), QColor("#818CF8")),
    OrbState.SPEAKING: (QColor("#6366F1"), QColor("#A78BFA"), QColor("#38BDF8")),
    OrbState.PROCESSING: (QColor("#6D28D9"), QColor("#8B5CF6"), QColor("#3B82F6")),
    OrbState.ERROR: (QColor("#991B1B"), QColor("#EF4444"), QColor("#DC2626")),
}


class AssistantOrb(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._state = OrbState.IDLE
        self._phase = 0.0
        self.setFixedSize(_WIDGET, _WIDGET)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._drag_pos: Optional[QPoint] = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(32)

    def _tick(self) -> None:
        self._phase += 0.12
        if self._phase > math.tau * 10:
            self._phase -= math.tau * 10
        self.update()

    def position_top_center(self, margin_top: int = 88) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.center().x() - self.width() // 2
        y = geo.y() + margin_top
        self.move(max(geo.x(), x), y)

    def set_orb_state(self, state: str) -> None:
        key = state.lower()
        if key == "thinking":
            key = "processing"
        try:
            self._state = OrbState(key)
        except ValueError:
            self._state = OrbState.IDLE
        self.update()

    def set_idle(self) -> None:
        self.set_orb_state("idle")

    def set_listening(self) -> None:
        self.set_orb_state("listening")

    def set_processing(self) -> None:
        self.set_orb_state("processing")

    def set_speaking(self) -> None:
        self.set_orb_state("speaking")

    def set_error(self) -> None:
        self.set_orb_state("error")

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        base_r = _ORB_DIAM / 2.0

        c0, c1, c2 = _STATE_CORE.get(self._state, _STATE_CORE[OrbState.IDLE])

        # Idle / global: breathing scale
        breath = 1.0
        if self._state == OrbState.IDLE:
            breath = 0.94 + 0.06 * (1.0 + math.sin(self._phase * 1.8)) * 0.5

        r_core = base_r * breath
        r_body = r_core
        if self._state == OrbState.SPEAKING:
            r_body += 3.0 * math.sin(self._phase * 5.0)

        # Outer glow layers
        for i in range(4):
            alpha = int(35 - i * 7 + 12 * math.sin(self._phase * 2 + i))
            alpha = max(8, min(55, alpha))
            rg = QRadialGradient(cx, cy, r_core + 8 + i * 10)
            rg.setColorAt(0, QColor(c1.red(), c1.green(), c1.blue(), alpha))
            rg.setColorAt(1, QColor(c0.red(), c0.green(), c0.blue(), 0))
            painter.setBrush(QBrush(rg))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(cx - r_core - 6 - i * 8, cy - r_core - 6 - i * 8, (r_core + 6 + i * 8) * 2, (r_core + 6 + i * 8) * 2))

        # Listening: expanding ripples
        if self._state == OrbState.LISTENING:
            for k in range(3):
                t = (self._phase * 1.6 + k * (math.tau / 3)) % math.tau
                expand = (1.0 - math.cos(t)) * 0.5
                rr = r_core + 6 + expand * 22
                pen = QPen(QColor(c2.red(), c2.green(), c2.blue(), int(90 * (1.0 - expand))))
                pen.setWidth(2)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QRectF(cx - rr, cy - rr, rr * 2, rr * 2))

        # Processing: rotating energy ring
        if self._state == OrbState.PROCESSING:
            painter.save()
            painter.translate(cx, cy)
            painter.rotate((self._phase * 50) % 360)
            painter.translate(-cx, -cy)
            pen = QPen(QColor(c2.red(), c2.green(), c2.blue(), 200))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(
                QRectF(cx - r_core - 5, cy - r_core - 5, (r_core + 5) * 2, (r_core + 5) * 2),
                int((self._phase * 80) % 5760),
                220 * 16,
            )
            painter.restore()

        # Particle specks
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(10):
            ang = self._phase * 1.2 + i * 0.62 * math.tau
            pr = r_core + 10 + 6 * math.sin(self._phase * 2 + i)
            px = cx + math.cos(ang) * pr
            py = cy + math.sin(ang) * pr
            pa = int(40 + 40 * math.sin(self._phase * 3 + i))
            painter.setBrush(QBrush(QColor(c2.red(), c2.green(), c2.blue(), pa)))
            painter.drawEllipse(QRectF(px - 2, py - 2, 4, 4))

        # Core orb body (uses r_body for speaking pulse)
        grad = QRadialGradient(cx - r_body * 0.35, cy - r_body * 0.35, r_body * 1.35)
        grad.setColorAt(0, c1.lighter(118))
        grad.setColorAt(0.45, c0)
        grad.setColorAt(1, c2.darker(115))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor(255, 255, 255, 55), 1))
        painter.drawEllipse(QRectF(cx - r_body, cy - r_body, r_body * 2, r_body * 2))

        # Speaking state audio waves
        if self._state == OrbState.SPEAKING:
            for k in range(2):
                t = (self._phase * 4.0 + k * math.pi) % (math.pi * 2)
                if t < math.pi:
                    sw = math.sin(t)
                    sr = r_body + 10 + sw * 25
                    spen = QPen(QColor(c1.red(), c1.green(), c1.blue(), int(150 * (1.0 - sw))))
                    spen.setWidth(3)
                    painter.setPen(spen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(QRectF(cx - sr, cy - sr, sr * 2, sr * 2))

        # Error state: red flashing ring
        if self._state == OrbState.ERROR:
            err_flash = abs(math.sin(self._phase * 8.0))
            err_r = r_body + 4 + err_flash * 6
            epen = QPen(QColor(239, 68, 68, int(200 * err_flash)), 5)
            painter.setPen(epen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(cx - err_r, cy - err_r, err_r * 2, err_r * 2))

        painter.end()


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    orb = AssistantOrb()
    orb.position_top_center()
    orb.show()

    test_states = ["idle", "listening", "processing", "speaking", "error"]
    idx = 0

    def cycle():
        global idx
        state = test_states[idx]
        orb.set_orb_state(state)
        print(f"Orb Test Mode -> Transition to: {state.upper()}")
        idx = (idx + 1) % len(test_states)

    t = QTimer()
    t.timeout.connect(cycle)
    t.start(2500)

    sys.exit(app.exec())
