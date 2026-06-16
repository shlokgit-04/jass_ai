"""
System tray entry for JASS: show dashboard, quit, quick listen.
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget


class TrayIcon:
    def __init__(
        self,
        parent: QWidget,
        on_show_dashboard: Callable[[], None],
        on_quit: Callable[[], None],
        on_listen: Optional[Callable[[], None]] = None,
    ) -> None:
        self._icon = QSystemTrayIcon(parent)
        self._icon.setToolTip("JASS")
        
        # Default icon may be empty on some themes; still functional
        icon = QIcon.fromTheme("audio-input-microphone")
        if icon.isNull():
            from PyQt6.QtGui import QPixmap, QPainter, QColor
            from PyQt6.QtCore import Qt
            pix = QPixmap(32, 32)
            pix.fill(Qt.GlobalColor.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QColor("#7C3AED"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(4, 4, 24, 24)
            p.end()
            icon = QIcon(pix)
            
        self._icon.setIcon(icon)
        menu = QMenu()
        dash = QAction("Dashboard", parent)
        dash.triggered.connect(lambda: on_show_dashboard())
        menu.addAction(dash)
        if on_listen:
            lst = QAction("Listen once", parent)
            lst.triggered.connect(lambda: on_listen())
            menu.addAction(lst)
        menu.addSeparator()
        quit_a = QAction("Quit", parent)
        quit_a.triggered.connect(lambda: on_quit())
        menu.addAction(quit_a)
        self._icon.setContextMenu(menu)
        self._icon.show()

    def show_message(self, title: str, msg: str) -> None:
        self._icon.showMessage(title, msg, QSystemTrayIcon.MessageIcon.Information, 3000)
