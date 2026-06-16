"""
Resolve Vosk model directory: env ``JASS_VOSK_MODEL`` then ``<project>/vosk-model``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def resolve_vosk_model(project_root: Path) -> Optional[Path]:
    env = os.environ.get("JASS_VOSK_MODEL", "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser().resolve())
    candidates.append((project_root / "vosk-model").resolve())

    for p in candidates:
        if p.is_dir() and any(p.iterdir()):
            return p
    return None


def vosk_resolution_message(project_root: Path, resolved: Optional[Path]) -> str:
    if resolved:
        return f"Vosk model OK: {resolved}"
    return (
        "Vosk model NOT FOUND.\n"
        "  • Set JASS_VOSK_MODEL to an unpacked model directory, or\n"
        f"  • Place an unpacked model at: {project_root / 'vosk-model'}\n"
        "  Download: https://alphacephei.com/vosk/models"
    )
