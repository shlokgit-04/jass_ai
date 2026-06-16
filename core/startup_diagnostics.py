"""
Startup health checks: microphone, Vosk, Ollama, API port, optional UI.
"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticReport:
    microphone_ok: bool = False
    microphone_detail: str = ""
    vosk_ok: bool = False
    vosk_detail: str = ""
    ollama_running: bool = False
    ollama_detail: str = ""
    llama_model_ok: bool = False
    llama_model_detail: str = ""
    port_free: bool = False
    port_detail: str = ""
    ui_ok: bool = False
    ui_detail: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def log_summary(self) -> None:
        print("\n======== JASS SYSTEM DIAGNOSTICS ========")
        print(f"[*] Microphone       : {'OK' if self.microphone_ok else 'FAIL'} - {self.microphone_detail}")
        print(f"[*] Vosk STT Model   : {'OK' if self.vosk_ok else 'FAIL'} - {self.vosk_detail}")
        print(f"[*] Ollama Server    : {'OK' if self.ollama_running else 'FAIL'} - {self.ollama_detail}")
        print(f"[*] LLM Model        : {'OK' if self.llama_model_ok else 'FAIL'} - {self.llama_model_detail}")
        print(f"[*] API Port         : {'OK' if self.port_free else 'FAIL'} - {self.port_detail}")
        print("=========================================\n")

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "microphone": {"ok": self.microphone_ok, "detail": self.microphone_detail},
            "vosk": {"ok": self.vosk_ok, "detail": self.vosk_detail},
            "ollama": {"ok": self.ollama_running, "detail": self.ollama_detail},
            "llm_model": {"ok": self.llama_model_ok, "detail": self.llama_model_detail},
            "api_port": {"ok": self.port_free, "detail": self.port_detail},
            "ui": {"ok": self.ui_ok, "detail": self.ui_detail},
        }


def check_port_free(host: str, port: int) -> tuple[bool, str]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
        return True, f"Port {port} is available on {host}"
    except OSError as exc:
        return False, f"Port {port} not available: {exc}"
    finally:
        s.close()


def check_ollama(model_name: str, base: str = "http://127.0.0.1:11434") -> tuple[bool, bool, str, str]:
    try:
        r = requests.get(f"{base.rstrip('/')}/api/tags", timeout=2.0)
        r.raise_for_status()
        data = r.json()
        names: list[str] = []
        for m in data.get("models") or []:
            if isinstance(m, dict) and m.get("name"):
                names.append(m["name"].split(":")[0].lower())
        want = model_name.split(":")[0].lower()
        found = any(want == n or n.startswith(want) for n in names)
        ollama_detail = f"Ollama reachable at {base}"
        model_detail = (
            f"Model '{model_name}' present"
            if found
            else f"Model '{model_name}' not listed; try: ollama pull {model_name}"
        )
        if names:
            ollama_detail += f"; installed: {', '.join(names[:6])}{'…' if len(names) > 6 else ''}"
        return True, found, ollama_detail, model_detail
    except Exception as exc:
        return False, False, f"Ollama not reachable: {exc}", "Cannot verify model"


def check_microphone() -> tuple[bool, str]:
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        try:
            if pa.get_default_input_device_info():
                return True, "Default microphone available"
            return False, "No default microphone detected"
        finally:
            pa.terminate()
    except ImportError:
        return False, "PyAudio not installed"
    except Exception as exc:
        return False, f"Microphone check failed: {exc}"


def run_startup_diagnostics(
    *,
    project_root: Path,
    vosk_path: Optional[Path],
    ollama_model: str,
    api_port: int,
) -> DiagnosticReport:
    rep = DiagnosticReport()
    rep.microphone_ok, rep.microphone_detail = check_microphone()
    if vosk_path and vosk_path.is_dir():
        rep.vosk_ok = True
        rep.vosk_detail = str(vosk_path)
    else:
        rep.vosk_ok = False
        rep.vosk_detail = "No valid model directory"
    rep.ollama_running, rep.llama_model_ok, rep.ollama_detail, rep.llama_model_detail = check_ollama(
        ollama_model
    )
    rep.port_free, rep.port_detail = check_port_free("0.0.0.0", api_port)
    rep.raw = {
        "project_root": str(project_root),
        "ollama_model": ollama_model,
        "api_port": api_port,
    }
    return rep
