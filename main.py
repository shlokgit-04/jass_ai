#!/usr/bin/env python3
"""
JASS — local AI assistant entrypoint.

Run::

    python main.py

See README for environment variables.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# --- bootstrap (minimal imports) ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from core.dep_bootstrap import ensure_dependencies  # noqa: E402

_dep_issues = ensure_dependencies()
for _msg in _dep_issues:
    logging.getLogger("jass.bootstrap").error("%s", _msg)

from core.stderr_filter import install_stderr_filter  # noqa: E402

install_stderr_filter()

from core.startup_diagnostics import DiagnosticReport, run_startup_diagnostics  # noqa: E402
from core.startup_selftest import run_selftest  # noqa: E402
from core.vosk_paths import resolve_vosk_model, vosk_resolution_message  # noqa: E402

from PyQt6.QtCore import QObject, QTimer, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from automation.background_engine import BackgroundEngine  # noqa: E402
from automation.manual_engine import ManualEngine  # noqa: E402
from automation.task_recorder import TaskRecorder  # noqa: E402
from automation.task_replay import TaskReplay  # noqa: E402
from brain.ai_engine import AIEngine  # noqa: E402
from brain.habit_learning import HabitLearner  # noqa: E402
from brain.shortcut_manager import ShortcutManager  # noqa: E402
from core.brain_manager import BrainManager  # noqa: E402
from core.performance_monitor import PerformanceMonitor  # noqa: E402
from core.task_scheduler import TaskPriority, TaskScheduler  # noqa: E402
from memory.command_history import CommandHistoryStore  # noqa: E402
from memory.database import get_database  # noqa: E402
from memory.habit_store import HabitStore  # noqa: E402
from mobile_sync.device_sync import DeviceSync  # noqa: E402
from mobile_sync.mobile_server import create_mobile_app, run_uvicorn_thread  # noqa: E402
from plugins.github_plugin import GitHubPlugin  # noqa: E402
from plugins.security_tools import SecurityToolsPlugin  # noqa: E402
from plugins.spotify_plugin import SpotifyPlugin  # noqa: E402
from plugins.whatsapp_plugin import WhatsAppPlugin  # noqa: E402
from ui.dashboard import DashboardWindow  # noqa: E402
from ui.orb import AssistantOrb  # noqa: E402
from ui.tray_icon import TrayIcon  # noqa: E402
from voice.emotion_voice import speak_empathetic  # noqa: E402
from voice.speech_input import SpeechInput  # noqa: E402
from voice.tts_output import TTSOutput  # noqa: E402
from voice.wake_listener import WakeListener  # noqa: E402


def _setup_file_logging() -> Path:
    log_dir = Path.home() / ".jass" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "jass.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(fh)
    return log_file


class JassSignals(QObject):
    orb_state = pyqtSignal(str)
    tray_message = pyqtSignal(str, str)
    hotkey_listen = pyqtSignal()
    assistant_reply_logged = pyqtSignal(str)


class JassApplication:
    def __init__(self) -> None:
        self.log_file = _setup_file_logging()
        self.logger = logging.getLogger("jass.main")

        self.lang = os.environ.get("JASS_LANG", "en").lower()
        self.mobile_port = int(os.environ.get("JASS_MOBILE_PORT", "8756"))
        self.ollama_model = os.environ.get("JASS_OLLAMA_MODEL", "llama3")
        self.upload_dir = str(Path.home() / ".jass" / "ned_uploads")

        self._vosk_path = resolve_vosk_model(_ROOT)
        self._vosk_model_str = str(self._vosk_path) if self._vosk_path else ""

        get_database()
        self.command_history = CommandHistoryStore()
        self.habit_store = HabitStore()
        self.shortcuts = ShortcutManager()
        self.habit_learner = HabitLearner(self.habit_store, self.shortcuts)

        self.ai_engine = AIEngine(model=self.ollama_model)
        self.manual = ManualEngine()
        self.background = BackgroundEngine()
        self.task_replay = TaskReplay()
        self.task_recorder = TaskRecorder()

        self.tts = TTSOutput()
        self.speech: SpeechInput | None = None

        self.spotify = SpotifyPlugin()
        self.whatsapp = WhatsAppPlugin()
        self.github = GitHubPlugin()
        self.security = SecurityToolsPlugin()

        self.signals = JassSignals()
        self.orb: AssistantOrb | None = None
        self.dashboard: DashboardWindow | None = None
        self._app: QApplication | None = None

        self.perf = PerformanceMonitor(interval_sec=2.0)
        self.scheduler = TaskScheduler(num_workers=4)

        self.device_sync = DeviceSync()

        def state_cb(name: str) -> None:
            self.signals.orb_state.emit(name)

        self.brain = BrainManager(
            ai_engine=self.ai_engine,
            shortcut_manager=self.shortcuts,
            habit_learner=self.habit_learner,
            command_history=self.command_history,
            manual_engine=self.manual,
            background_engine=self.background,
            task_replay=self.task_replay,
            task_recorder=self.task_recorder,
            tts=self.tts,
            security_plugin=self.security,
            phrase_plugins=[self.spotify, self.whatsapp, self.github],
            state_callback=state_cb,
            language=self.lang,
        )

        self.emotion_detector = None
        self.camera = None
        self._last_empathy = 0.0
        self._wake_listener: WakeListener | None = None
        self._tray: TrayIcon | None = None
        self._diagnostics: DiagnosticReport | None = None
        self._hotkey_thread: threading.Thread | None = None

        self._install_global_hooks()
        self.signals.hotkey_listen.connect(self._on_hotkey_listen)

    def _install_global_hooks(self) -> None:
        def excepthook(exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            logging.error("Unhandled exception (main thread):\n%s", "".join(traceback.format_tb(tb)))
            logging.error("%s: %s", exc_type.__name__, exc)

        sys.excepthook = excepthook

        if hasattr(threading, "excepthook"):
            def thread_excepthook(args: threading.ExceptHookArgs) -> None:  # type: ignore[name-defined]
                logging.error(
                    "Thread %s failed:\n%s",
                    args.thread.name,
                    "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
                )

            threading.excepthook = thread_excepthook  # type: ignore[attr-defined]

    def _health_payload(self) -> dict:
        if self._diagnostics is None:
            return {}
        d = self._diagnostics.to_api_dict()
        d["wake_listener_alive"] = (
            self._wake_listener.is_alive() if self._wake_listener else False
        )
        d["speech_available"] = self.speech.available if self.speech else False
        return d

    def _on_vision_frame(self, frame) -> None:
        import time

        if self.emotion_detector is None:
            return
        try:
            insight = self.emotion_detector.analyze_frame(frame)
        except Exception as exc:
            logging.debug("vision: %s", exc)
            return
        em = (insight.emotion or "").lower()
        sad_like = em in ("sad", "fear", "angry") or ("sad" in em)
        if sad_like and insight.face_present:
            now = time.monotonic()
            if now - self._last_empathy > 120.0:
                self._last_empathy = now
                speak_empathetic(self.tts, self.lang)
                self.signals.tray_message.emit("JASS", "Empathic check-in")

    def _handle_command(self, text: str, source: str) -> str:
        try:
            reply = self.brain.handle_utterance(text, source=source)
        except Exception as exc:
            self.logger.exception("Command pipeline error: %s", exc)
            reply = f"I hit an error handling that: {exc}"
        if reply:
            self.logger.info("Assistant reply: %s", reply)
            try:
                self.signals.assistant_reply_logged.emit(reply.strip())
            except Exception:
                pass
            try:
                snippet = reply if len(reply) <= 240 else reply[:237] + "…"
                self.signals.tray_message.emit("JASS", snippet)
            except Exception:
                pass
            self.signals.orb_state.emit("speaking")
            if not os.environ.get("JASS_NO_TTS"):
                try:
                    self.tts.speak(reply, block=False)
                except Exception as exc:
                    self.logger.warning("TTS: %s", exc)
        return reply or ""

    def _wake_callback(self) -> None:
        self.logger.info("Wake word detected")
        self.scheduler.submit(
            "voice_session",
            self._voice_session_worker,
            priority=TaskPriority.HIGH,
        )

    def _voice_session_worker(self) -> None:
        import time

        # Step 1: signal busy so wake_listener closes its stream (releases mic)
        if self._wake_listener:
            self._wake_listener.set_busy(True)
            # set_busy blocks ~600ms until stream is confirmed closed
            # add tiny extra buffer for ALSA device to settle
            time.sleep(0.15)

        try:
            self.signals.orb_state.emit("listening")
            self.logger.info("Voice session started — listening for command…")

            if self.speech is None:
                self.logger.error("Speech input not initialized")
                self.signals.orb_state.emit("idle")
                return

            # Play a short audio cue so user knows we're listening
            if not os.environ.get("JASS_NO_TTS"):
                try:
                    self.tts.speak("Yes?", block=True)
                except Exception:
                    pass

            # Step 2: listen for the actual command (mic is free now)
            try:
                text = self.speech.listen_once(language=self.lang)
            except Exception as exc:
                self.logger.exception("Listen error: %s", exc)
                text = None

            if not text:
                self.logger.info("No speech recognized (timeout or unclear).")
                self.signals.orb_state.emit("idle")
                return

            self.logger.info("Recognized command: %r", text)
            self.signals.orb_state.emit("processing")
            self._handle_command(text, source="voice")
            time.sleep(0.4)
            self.signals.orb_state.emit("idle")

        finally:
            # Step 3: release mic back to wake listener
            if self._wake_listener:
                self._wake_listener.set_busy(False)

    def _listen_once_clicked(self) -> None:
        self.scheduler.submit("manual_listen", self._voice_session_worker, priority=TaskPriority.HIGH)

    def _queue_text_command(self, text: str) -> None:
        """Dashboard / typed input — same pipeline as voice, no STT."""

        def worker() -> None:
            self.signals.orb_state.emit("processing")
            self.logger.info("Text command: %s", text)
            try:
                self._handle_command(text, source="text_ui")
            finally:
                import time

                time.sleep(0.15)
                self.signals.orb_state.emit("idle")

        self.scheduler.submit("text_ui", worker, priority=TaskPriority.HIGH)

    def process_text_cli(self, text: str) -> str:
        """Headless one-shot (used with ``python main.py --text``)."""
        t = (text or "").strip()
        if not t:
            return ""
        self.logger.info("[CLI] %s", t)
        self.signals.orb_state.emit("processing")
        try:
            return self._handle_command(t, source="cli")
        finally:
            self.signals.orb_state.emit("idle")

    def _on_hotkey_listen(self) -> None:
        self.logger.info("Hotkey activated (Ctrl+Space) — starting listen session")
        self._listen_once_clicked()

    def _start_global_hotkey(self) -> None:
        try:
            from pynput import keyboard
        except ImportError:
            self.logger.warning("pynput missing; Ctrl+Space hotkey disabled")
            return

        def on_hotkey() -> None:
            try:
                self.signals.hotkey_listen.emit()
            except Exception as exc:
                logging.debug("hotkey emit: %s", exc)

        def runner() -> None:
            try:
                with keyboard.GlobalHotKeys({"<ctrl>+<space>": on_hotkey}) as h:
                    h.join()
            except Exception as exc:
                logging.warning("Global hotkey listener stopped: %s", exc)

        self._hotkey_thread = threading.Thread(target=runner, name="JASS-Hotkey", daemon=True)
        self._hotkey_thread.start()

    def _deferred_heavy_start(self) -> None:
        try:
            from vision.camera_monitor import CameraMonitor
            from vision.emotion_detection import EmotionDetector
            
            if os.environ.get("JASS_VISION") == "1":
                self.emotion_detector = EmotionDetector()
                self.camera = CameraMonitor(device_index=0, fps_limit=3.0)
                self.camera.set_callback(self._on_vision_frame)
                self.camera.start()
            else:
                self.logger.info("Vision subsystem skipped. Set JASS_VISION=1 to enable.")
        except Exception as exc:
            self.logger.warning("Vision subsystem disabled: %s", exc)

    def _trigger_restart(self) -> None:
        self.logger.info("Restart triggered from dashboard.")
        import sys, os, time, threading
        def do_restart():
            try:
                if self._app:
                    self._app.quit()
            except Exception:
                pass
            time.sleep(1)
            os.execv(sys.executable, [sys.executable, "main.py"] + sys.argv[1:])
        threading.Thread(target=do_restart, daemon=True).start()

    def run(self) -> int:
        self.perf.start()
        self.scheduler.start()

        self._diagnostics = run_startup_diagnostics(
            project_root=_ROOT,
            vosk_path=self._vosk_path,
            ollama_model=self.ollama_model,
            api_port=self.mobile_port,
        )
        self._diagnostics.log_summary()

        self.speech = SpeechInput(vosk_model=self._vosk_path)

        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        if not self._vosk_path:
            msg = vosk_resolution_message(_ROOT, self._vosk_path)
            self.logger.error(msg.replace("\n", " | "))
            QMessageBox.critical(
                None,
                "JASS — Vosk model required",
                msg + "\n\nWake-word listening cannot start until a model is configured.\n"
                "You can still use Ctrl+Space or the tray Listen button.",
            )
        else:
            self.logger.info("%s", vosk_resolution_message(_ROOT, self._vosk_path))

        self.orb = AssistantOrb()
        self.orb.position_top_center(margin_top=24)
        self.orb.show()
        self._diagnostics.ui_ok = True
        self._diagnostics.ui_detail = "Floating orb shown"

        mobile_app = create_mobile_app(
            on_command=self._handle_command,
            list_tasks=self.task_replay.list_tasks,
            upload_dir=self.upload_dir,
            get_health=self._health_payload,
            on_mic_toggle=lambda enabled: self._wake_listener.set_busy(not enabled) if self._wake_listener else None,
            on_restart=lambda: self._trigger_restart()
        )
        try:
            uvicorn_server, uvicorn_thread = run_uvicorn_thread(mobile_app, host="0.0.0.0", port=self.mobile_port)
        except Exception as exc:
            self.logger.error("Mobile API failed to start: %s", exc)

        if self._vosk_path:
            self._wake_listener = WakeListener(
                on_wake=self._wake_callback,
                model_path=self._vosk_model_str,
            )
            started = self._wake_listener.start()
            if not started:
                self.logger.error("Wake listener failed to start — check logs above")
        else:
            self._wake_listener = None

        self._start_global_hotkey()

        self.dashboard = DashboardWindow(
            perf=self.perf,
            history=self.command_history,
            task_replay=self.task_replay,
            device_sync=self.device_sync,
            spotify=self.spotify,
            whatsapp=self.whatsapp,
            github=self.github,
            on_listen_click=self._listen_once_clicked,
            on_text_command=self._queue_text_command,
        )
        self.dashboard.refresh_all()

        self.signals.assistant_reply_logged.connect(self.dashboard.append_assistant_reply)
        self.signals.orb_state.connect(lambda s: self.orb.set_orb_state(s) if self.orb else None)

        self._tray = TrayIcon(
            self.dashboard,
            on_show_dashboard=lambda: (
                self.dashboard.show(),
                self.dashboard.raise_(),
                self.dashboard.refresh_all(),
            ),
            on_quit=self._app.quit,
            on_listen=self._listen_once_clicked,
        )
        self.signals.tray_message.connect(lambda t, m: self._tray.show_message(t, m))

        QTimer.singleShot(60, self._deferred_heavy_start)

        self.logger.info("JASS initialized. Listening for wake word.")
        QTimer.singleShot(
            400,
            lambda: self._tray.show_message(
                "JASS",
                "Type commands in the Dashboard, or Say JASS / Ctrl+Space / Listen.",
            ),
        )

        def _watch_wake() -> None:
            if self._vosk_path and self._wake_listener and not self._wake_listener.is_alive():
                self.logger.warning("Wake listener thread stopped; restarting.")
                try:
                    self._wake_listener = WakeListener(
                        on_wake=self._wake_callback,
                        model_path=self._vosk_model_str,
                    )
                    self._wake_listener.start()
                except Exception as exc:
                    self.logger.error("Wake listener restart failed: %s", exc)

        self._wake_watch = QTimer()
        self._wake_watch.timeout.connect(_watch_wake)
        self._wake_watch.start(30_000)

        def _selftest() -> None:
            run_selftest(
                project_root=_ROOT,
                vosk_path=self._vosk_path,
                speech_available=bool(self.speech and self.speech.available),
                wake_thread_alive=self._wake_listener.is_alive() if self._wake_listener else False,
                orb_visible=bool(self.orb and self.orb.isVisible()),
                ollama_ok=bool(self._diagnostics and self._diagnostics.ollama_running),
                model_ok=bool(self._diagnostics and self._diagnostics.llama_model_ok),
                port_ok=bool(self._diagnostics and self._diagnostics.port_free),
            )

        QTimer.singleShot(900, _selftest)

        return self._app.exec()

    def shutdown(self) -> None:
        w = getattr(self, "_wake_watch", None)
        if w is not None:
            w.stop()
        self.scheduler.stop()
        self.perf.stop()
        try:
            if self.camera is not None:
                self.camera.stop()
        except Exception:
            pass
        try:
            if self._wake_listener is not None:
                self._wake_listener.stop()
        except Exception:
            pass
        try:
            if self.emotion_detector is not None:
                self.emotion_detector.close()
        except Exception:
            pass


def _cli_text_mode(command: str) -> int:
    """Run one command and print the assistant reply (no GUI window)."""
    from PyQt6.QtCore import QCoreApplication

    _ = QCoreApplication([sys.argv[0], "jass-cli"])
    app = JassApplication()
    try:
        out = app.process_text_cli(command)
        print(out or "", flush=True)
        return 0 if out else 1
    finally:
        app.shutdown()


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) >= 1 and argv[0] == "--text":
        rest = argv[1:]
        cmd = " ".join(rest).strip()
        if not cmd:
            print('Usage: python main.py --text "your command here"', file=sys.stderr)
            return 2
        return _cli_text_mode(cmd)

    app = JassApplication()
    code = 0
    try:
        code = app.run()
    finally:
        app.shutdown()
    return int(code or 0)

if __name__ == "__main__":
    raise SystemExit(main())
