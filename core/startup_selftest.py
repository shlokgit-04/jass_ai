"""
Post-startup self-test: logs pass/fail and prints fix hints (non-fatal).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jass.selftest")


def run_selftest(
    *,
    project_root: Path,
    vosk_path: Optional[Path],
    speech_available: bool,
    wake_thread_alive: Optional[bool],
    orb_visible: bool,
    ollama_ok: bool,
    model_ok: bool,
    port_ok: bool,
) -> None:
    _ = project_root
    logger.info("======== JASS startup self-test ========")
    checks: list[tuple[str, bool, str]] = [
        ("Vosk model directory", vosk_path is not None and vosk_path.is_dir(), "Set JASS_VOSK_MODEL or add ./vosk-model"),
        ("Speech microphone module", speech_available, "Install PyAudio + portaudio dev; check mic permissions"),
        ("Wake listener thread", wake_thread_alive is True, "Fix Vosk model path and audio device"),
        ("Orb UI visible", orb_visible, "Ensure DISPLAY / Wayland session for GUI"),
        ("Ollama reachable", ollama_ok, "Run: ollama serve"),
        ("llama3 (or configured) model", model_ok, "Run: ollama pull llama3"),
        ("API port 8756 free / bound", port_ok, "Free port 8756 or set JASS_MOBILE_PORT"),
    ]
    for name, ok, fix in checks:
        status = "PASS" if ok else "FAIL"
        logger.info("[selftest] %s: %s", status, name)
        if not ok:
            logger.info("[selftest]   → %s", fix)
    logger.info("======== end self-test ========")
