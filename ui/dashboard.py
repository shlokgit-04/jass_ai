"""
Main dashboard: typed commands (no voice), last replies, status, logs, tasks.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable, Optional

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from automation.task_replay import TaskReplay
    from core.performance_monitor import PerformanceMonitor
    from memory.command_history import CommandHistoryStore
    from mobile_sync.device_sync import DeviceSync
    from plugins.github_plugin import GitHubPlugin
    from plugins.spotify_plugin import SpotifyPlugin
    from plugins.whatsapp_plugin import WhatsAppPlugin


class DashboardWindow(QWidget):
    def __init__(
        self,
        perf: "PerformanceMonitor",
        history: "CommandHistoryStore",
        task_replay: "TaskReplay",
        device_sync: "DeviceSync",
        spotify: Optional["SpotifyPlugin"] = None,
        whatsapp: Optional["WhatsAppPlugin"] = None,
        github: Optional["GitHubPlugin"] = None,
        on_listen_click: Optional[Callable[[], None]] = None,
        on_text_command: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("JASS Dashboard")
        self.resize(920, 620)
        self._perf = perf
        self._history = history
        self._task_replay = task_replay
        self._device_sync = device_sync
        self._spotify = spotify
        self._whatsapp = whatsapp
        self._github = github
        self._on_listen = on_listen_click
        self._on_text_command = on_text_command

        self._status_text: Optional[QTextEdit] = None
        self._memory_list: Optional[QListWidget] = None
        self._task_list: Optional[QListWidget] = None
        self._plugin_text: Optional[QTextEdit] = None
        self._device_text: Optional[QTextEdit] = None
        self._cmd_line: Optional[QLineEdit] = None
        self._reply_log: Optional[QTextEdit] = None

        self.setStyleSheet("""
            QWidget {
                background-color: #121212;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLineEdit, QTextEdit, QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 4px;
            }
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QTabWidget::pane {
                border: 1px solid #333;
                background-color: #1a1a1a;
            }
            QTabBar::tab {
                background-color: #222;
                padding: 8px 16px;
                border: 1px solid #333;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #1a1a1a;
                border: 1px solid #555;
                border-bottom: 1px solid #1a1a1a;
            }
        """)

        layout = QVBoxLayout(self)

        # --- Always-visible text command (works without microphone) ---
        layout.addWidget(QLabel("<b>Command</b> — type and press Enter or Send (same AI as voice):"))
        cmd_row = QHBoxLayout()
        self._cmd_line = QLineEdit()
        self._cmd_line.setPlaceholderText('Examples: "what is 2+2"  ·  open firefox  ·  JASS start learning')
        self._cmd_line.returnPressed.connect(self._submit_text_command)
        cmd_row.addWidget(self._cmd_line, stretch=1)
        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._submit_text_command)
        cmd_row.addWidget(send_btn)
        layout.addLayout(cmd_row)

        layout.addWidget(QLabel("<b>Assistant replies</b> (latest at bottom):"))
        self._reply_log = QTextEdit()
        self._reply_log.setReadOnly(True)
        self._reply_log.setMaximumHeight(140)
        self._reply_log.setPlaceholderText("Replies from typed or voice commands appear here.")
        layout.addWidget(self._reply_log)

        clr = QPushButton("Clear reply log")
        clr.clicked.connect(lambda: self._reply_log.clear() if self._reply_log else None)
        layout.addWidget(clr)

        tabs = QTabWidget()
        layout.addWidget(tabs, stretch=1)

        tabs.addTab(self._build_status(), "Status")
        tabs.addTab(self._build_memory(), "Memory logs")
        tabs.addTab(self._build_tasks(), "Tasks")
        tabs.addTab(self._build_plugins(), "Plugins")
        tabs.addTab(self._build_devices(), "Devices")

        btn_row = QHBoxLayout()
        refresh = QPushButton("Refresh all")
        refresh.clicked.connect(self.refresh_all)
        btn_row.addWidget(refresh)
        if self._on_listen:
            listen_btn = QPushButton("Listen (one shot)")
            listen_btn.clicked.connect(self._on_listen)
            btn_row.addWidget(listen_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _submit_text_command(self) -> None:
        if not self._cmd_line or not self._on_text_command:
            return
        text = self._cmd_line.text().strip()
        if not text:
            return
        self._cmd_line.clear()
        self._on_text_command(text)

    def append_assistant_reply(self, text: str) -> None:
        """Slot: safe from any thread (use QueuedConnection from worker)."""
        if not self._reply_log:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        self._reply_log.append(f"[{ts}] {text}")
        sb = self._reply_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _build_status(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self._status_text = QTextEdit()
        self._status_text.setReadOnly(True)
        v.addWidget(self._status_text)
        return w

    def _build_memory(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self._memory_list = QListWidget()
        v.addWidget(self._memory_list)
        return w

    def _build_tasks(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self._task_list = QListWidget()
        v.addWidget(self._task_list)
        return w

    def _build_plugins(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self._plugin_text = QTextEdit()
        self._plugin_text.setReadOnly(True)
        v.addWidget(self._plugin_text)
        return w

    def _build_devices(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        hint = QLabel("NED companion devices registered via /v1 APIs appear here.")
        hint.setWordWrap(True)
        v.addWidget(hint)
        self._device_text = QTextEdit()
        self._device_text.setReadOnly(True)
        v.addWidget(self._device_text)
        return w

    def refresh_all(self) -> None:
        snap = self._perf.snapshot()
        if self._status_text:
            self._status_text.setPlainText(
                f"CPU: {snap.cpu_percent:.1f}%\nMemory: {snap.memory_percent:.1f}%\n"
                f"Timestamp: {snap.timestamp:.0f}"
            )
        if self._memory_list:
            self._memory_list.clear()
            for row in self._history.recent(80):
                self._memory_list.addItem(
                    f"{row.get('created_at')} | {row.get('source')} | {row.get('raw_text')!r}"
                )
        if self._task_list:
            self._task_list.clear()
            for name in self._task_replay.list_tasks():
                self._task_list.addItem(name)
        if self._plugin_text:
            lines = []
            if self._spotify:
                lines.append(f"Spotify (playerctl): {'yes' if self._spotify.available() else 'no'}")
            if self._whatsapp:
                lines.append("WhatsApp Web: use voice/GUI to open")
            if self._github:
                lines.append("GitHub: token from GITHUB_TOKEN env")
            self._plugin_text.setPlainText("\n".join(lines) or "No plugin metadata.")
        if self._device_text:
            devs = self._device_sync.list_devices()
            self._device_text.setPlainText(
                "\n".join(str(d) for d in devs) or "No devices registered yet."
            )
