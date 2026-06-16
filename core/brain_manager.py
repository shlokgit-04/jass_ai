"""
Orchestrates wake flow: speech → intent → AI / shortcuts / automation / plugins.
"""

from __future__ import annotations

import logging
import re
import shlex
import subprocess
import threading
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from automation.background_engine import BackgroundEngine
    from automation.manual_engine import ManualEngine
    from automation.task_recorder import TaskRecorder
    from automation.task_replay import TaskReplay
    from brain.ai_engine import AIEngine
    from brain.habit_learning import HabitLearner
    from brain.shortcut_manager import ShortcutManager
    from memory.command_history import CommandHistoryStore
    from plugins.security_tools import SecurityToolsPlugin
    from voice.tts_output import TTSOutput

logger = logging.getLogger(__name__)


class BrainManager:
    """
    High-level coordinator invoked after wake word and STT produce user text.
    """

    def __init__(
        self,
        ai_engine: "AIEngine",
        shortcut_manager: "ShortcutManager",
        habit_learner: "HabitLearner",
        command_history: "CommandHistoryStore",
        manual_engine: "ManualEngine",
        background_engine: "BackgroundEngine",
        task_replay: "TaskReplay",
        task_recorder: Optional["TaskRecorder"] = None,
        tts: Optional["TTSOutput"] = None,
        security_plugin: Optional["SecurityToolsPlugin"] = None,
        phrase_plugins: Optional[list] = None,
        state_callback: Optional[Callable[[str], None]] = None,
        language: str = "en",
    ) -> None:
        self._ai = ai_engine
        self._shortcuts = shortcut_manager
        self._habits = habit_learner
        self._history = command_history
        self._manual = manual_engine
        self._bg = background_engine
        self._replay = task_replay
        self._recorder = task_recorder
        self._tts = tts
        self._security = security_plugin
        self._phrase_plugins = phrase_plugins or []
        self._state_cb = state_callback
        self._language = language
        self._learning_active = False
        self._lock = threading.Lock()
        self._llm_cache: dict[str, dict[str, Any]] = {}

    def set_language(self, code: str) -> None:
        self._language = code

    def set_state(self, name: str) -> None:
        if self._state_cb:
            try:
                self._state_cb(name)
            except Exception as exc:
                logger.debug("state callback: %s", exc)

    def is_learning(self) -> bool:
        with self._lock:
            return self._learning_active

    def set_learning(self, active: bool) -> None:
        with self._lock:
            self._learning_active = active

    def handle_utterance(self, text: str, source: str = "voice") -> str:
        """
        Main entry: normalize, apply shortcuts, handle learning commands,
        delegate to AI for command extraction, execute, log, learn habits.
        """
        self.set_state("processing")
        raw = (text or "").strip()
        if not raw:
            self.set_state("idle")
            return ""

        lowered = raw.lower()

        # Learning mode toggles
        if self._matches_learning_start(lowered):
            self.set_learning(True)
            if self._recorder:
                try:
                    self._recorder.start_session()
                except Exception as exc:
                    logger.warning("task_recorder start: %s", exc)
            msg = self._msg(
                "learning_started",
                "Learning mode started. I will record your mouse and keyboard.",
            )
            self._history.log(source, raw, "learning_start", "ok", None)
            self.set_state("idle")
            return msg

        if self._matches_learning_stop(lowered):
            self.set_learning(False)
            if self._recorder:
                try:
                    self._recorder.stop_session()
                except Exception as exc:
                    logger.warning("task_recorder stop: %s", exc)
            msg = self._msg(
                "learning_stopped",
                "Learning mode stopped.",
            )
            self._history.log(source, raw, "learning_stop", "ok", None)
            self.set_state("idle")
            return msg

        # Replay request
        replay_match = re.match(
            r"^\s*(?:jass\s+)?(?:replay|run task|play task)\s+(.+)$",
            lowered,
        )
        if replay_match:
            name = replay_match.group(1).strip()
            ok, detail = self._replay.replay_by_name(name)
            self._history.log(source, raw, f"replay:{name}", "ok" if ok else "error", detail)
            self.set_state("idle")
            return detail

        # Expand habitual shortcuts
        expanded = self._shortcuts.expand(raw)
        effective = expanded if expanded != raw else raw

        for plug in self._phrase_plugins:
            try:
                if getattr(plug, "handles", lambda _t: False)(effective):
                    result = getattr(plug, "handle", lambda _t: None)(effective)
                    if result is not None:
                        self._history.log(source, raw, effective, "ok", str(result)[:500])
                        self._habits.record_and_maybe_shortcut(effective)
                        self.set_state("idle")
                        return str(result)
            except Exception as exc:
                logger.warning("phrase plugin error: %s", exc)

        # Security plugin passthrough (explicit phrases)
        if self._security and self._security.handles(effective):
            result = self._security.run(effective)
            self._history.log(source, raw, effective, "ok", result[:500])
            self._habits.record_and_maybe_shortcut(effective)
            self.set_state("idle")
            return result

        # Fast Rule Based Command Router
        rule_action = self._route_fast_command(effective)
        if rule_action:
            action = rule_action
        else:
            # Check cache
            if effective in self._llm_cache:
                action = self._llm_cache[effective]
            else:
                # Build RAG Context
                recent_stmts = self._history.recent(5)
                history_arr = [f"User: {r['raw_text']} -> {r['result_status']}" for r in recent_stmts if r.get('raw_text')]
                history_arr.reverse()
                history_str = "\n".join(history_arr)

                # Check for Vision request natively
                images = None
                lowered_eff = effective.lower()
                if "screen" in lowered_eff or "see" in lowered_eff or "vision" in lowered_eff:
                    try:
                        import mss
                        import base64
                        with mss.mss() as sct:
                            monitor = sct.monitors[1]
                            sct_img = sct.grab(monitor)
                            img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
                            images = [base64.b64encode(img_bytes).decode('utf-8')]
                    except Exception as e:
                        logger.warning("Vision grab failed: %s", e)

                # Ask LLM for structured action
                try:
                    action = self._ai.interpret_to_action(effective, language=self._language, history_context=history_str, images=images)
                    self._llm_cache[effective] = action
                except Exception as exc:
                    logger.exception("AI interpret failed: %s", exc)
                    self._history.log(source, raw, None, "error", str(exc))
                    self.set_state("idle")
                    return self._msg("ai_error", "I could not reach the language model. Is Ollama running?")

        kind = (action.get("kind") or "shell").lower()
        payload = action.get("payload") or ""

        reply = ""
        status = "ok"
        details: Optional[str] = None

        try:
            if kind == "shell":
                reply, details = self._run_shell(payload)
            elif kind == "manual_ui":
                reply = self._manual.run_sequence(payload)
                details = reply
            elif kind == "background":
                reply = self._bg.run_action(payload)
                details = reply
            elif kind == "say":
                reply = str(payload)
            elif kind == "python":
                import io
                import sys
                old_stdout = sys.stdout
                redirected_output = sys.stdout = io.StringIO()
                try:
                    exec(payload)
                    sys.stdout = old_stdout
                    out = redirected_output.getvalue()
                    reply = self._msg("cmd_ok", f"Executed Python snippet. {out[:200]}")
                    details = out
                except Exception as ex:
                    sys.stdout = old_stdout
                    reply = self._msg("exec_error", f"Python error: {ex}")
                    details = str(ex)
            else:
                reply = str(payload or action.get("message") or "Done.")
        except Exception as exc:
            status = "error"
            details = str(exc)
            reply = self._msg("exec_error", f"Execution failed: {exc}")
            logger.exception("handle_utterance exec: %s", exc)

        self._history.log(source, raw, f"{kind}:{payload}", status, details)
        self._habits.record_and_maybe_shortcut(effective)
        self.set_state("idle")
        return reply

    def _route_fast_command(self, text: str) -> Optional[dict[str, Any]]:
        lowered = text.lower().strip()
        
        # Smart Morning Routine
        if lowered == "good morning":
            import requests
            try:
                weather = requests.get("https://wttr.in/?format=3", timeout=3).text.strip()
                return {"kind": "say", "payload": f"Good morning! {weather}"}
            except Exception:
                return {"kind": "say", "payload": "Good morning!"}

        # Focus Mode
        if lowered == "activate focus mode":
            return {"kind": "shell", "payload": "bash -c \"notify-send 'Focus Mode Activated'; killall discord slack telegram-desktop spotify || true\""}

        # System control
        if lowered in ("shutdown", "shutdown system", "poweroff"):
            return {"kind": "shell", "payload": "sudo systemctl poweroff"}
        if lowered in ("restart", "restart system", "reboot"):
            return {"kind": "shell", "payload": "sudo systemctl reboot"}
            
        # Hardware diagnostics
        if "check cpu" in lowered:
            import psutil
            return {"kind": "say", "payload": f"CPU usage is at {psutil.cpu_percent()} percent."}
        if "check memory" in lowered or "check ram" in lowered:
            import psutil
            mem = psutil.virtual_memory().percent
            return {"kind": "say", "payload": f"Memory usage is at {mem} percent."}
            
        # Fast terminal execution rules
        import re
        term_match = re.match(r"^(run|execute|install|update)\s+(.+)$", lowered)
        if term_match:
            verb = term_match.group(1)
            cmd = term_match.group(2).strip()
            if cmd.startswith("apt ") and verb in ("run", "install", "update"):
                cmd = f"sudo {cmd}"
            return {"kind": "shell", "payload": cmd}
            
        # Fast UI open rules
        app_match = re.match(r"^open\s+(.+)$", lowered)
        if app_match:
            app_name = app_match.group(1).strip()
            if app_name in ("youtube", "youtube.com", "you tube"):
                return {"kind": "shell", "payload": "xdg-open https://youtube.com"}
            if app_name == "terminal":
                app_name = "gnome-terminal"
            return {"kind": "shell", "payload": app_name}
            
        return None

    def _matches_learning_start(self, lowered: str) -> bool:
        return bool(
            re.search(
                r"(?:^|\b)(?:jass\s+)?start\s+learning\b",
                lowered,
            )
        )

    def _matches_learning_stop(self, lowered: str) -> bool:
        return bool(
            re.search(
                r"(?:^|\b)(?:jass\s+)?stop\s+learning\b",
                lowered,
            )
        )

    def _run_shell(self, command_line: str) -> tuple[str, str]:
        command_line = command_line.strip()
        if not command_line:
            return self._msg("empty", "No command to run."), ""
        try:
            args = shlex.split(command_line)
        except ValueError as exc:
            return self._msg("parse_error", str(exc)), str(exc)
            
        gui_apps = {"firefox", "brave", "chrome", "chromium", "nautilus", "gnome-terminal", "xterm", "gedit", "thunar", "dolphin", "code", "vlc", "spotify", "discord", "slack", "konsole", "terminator", "wezterm", "gnome-calculator", "xdg-open"}
        cmd_base = args[0].lower()
        if any(app in cmd_base for app in gui_apps):
            try:
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                if cmd_base == "xdg-open":
                    return self._msg("cmd_ok", "Opening requested link, sir."), f"Launched {args[0]} in background."
                return self._msg("cmd_ok", f"Opening {cmd_base}, sir."), f"Launched {args[0]} in background."
            except Exception as exc:
                return self._msg("cmd_failed", f"Failed to open {args[0]}"), str(exc)

        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            return (
                self._msg("cmd_failed", f"Exit {proc.returncode}: {out[:400]}"),
                out[:2000],
            )
        return (
            self._msg("cmd_ok", out[:400] if out else "Command completed."),
            out[:2000],
        )

    def _msg(self, key: str, default_en: str) -> str:
        # Minimal i18n map; voice/emotion_voice can hold fuller sets
        messages = {
            "en": {
                "learning_started": "Learning mode started. I will record your actions.",
                "learning_stopped": "Learning mode stopped.",
                "ai_error": "I could not reach the language model. Is Ollama running with llama3?",
                "exec_error": default_en,
                "empty": "No command to run.",
                "parse_error": default_en,
                "cmd_failed": default_en,
                "cmd_ok": default_en,
            },
            "hi": {
                "learning_started": "लर्निंग मोड शुरू। मैं आपकी क्रियाएँ रिकॉर्ड करूँगी।",
                "learning_stopped": "लर्निंग मोड बंद।",
                "ai_error": "भाषा मॉडल तक नहीं पहुँच पाई। क्या Ollama चल रहा है?",
                "exec_error": default_en,
                "empty": "चलाने के लिए कोई कमांड नहीं।",
                "parse_error": default_en,
                "cmd_failed": default_en,
                "cmd_ok": default_en,
            },
            "mr": {
                "learning_started": "शिकण मोड सुरू. मी तुमच्या क्रिया नोंदवेन.",
                "learning_stopped": "शिकण मोड थांबवला.",
                "ai_error": "भाषा मॉडेलपर्यंत पोहोचू शकत नाही. Ollama चालू आहे का?",
                "exec_error": default_en,
                "empty": "चालवण्यासाठी आदेश नाही.",
                "parse_error": default_en,
                "cmd_failed": default_en,
                "cmd_ok": default_en,
            },
            "ja": {
                "learning_started": "学習モードを開始しました。操作を記録します。",
                "learning_stopped": "学習モードを停止しました。",
                "ai_error": "言語モデルに接続できません。Ollamaは起動していますか？",
                "exec_error": default_en,
                "empty": "実行するコマンドがありません。",
                "parse_error": default_en,
                "cmd_failed": default_en,
                "cmd_ok": default_en,
            },
        }
        lang = self._language if self._language in messages else "en"
        return messages[lang].get(key, default_en)
