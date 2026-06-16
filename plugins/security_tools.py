"""
Curated invocation of common security CLI tools (Kali-oriented).

Only allows a fixed set of prefixes for safety.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

_ALLOWED = (
    "nmap",
    "nikto",
    "sqlmap",
    "whois",
    "dig",
)


class SecurityToolsPlugin:
    def handles(self, text: str) -> bool:
        t = text.lower()
        return any(t.strip().startswith(p) or f" {p} " in f" {t} " for p in _ALLOWED)

    def run(self, text: str) -> str:
        line = text.strip()
        if not line:
            return "Empty command."
        first = line.split()[0].lower()
        if first not in _ALLOWED:
            return "Security plugin: command not in allow-list."
        binary = shutil.which(first)
        if not binary:
            return f"{first} not found in PATH."
        try:
            # Reject shell metacharacters
            if re.search(r"[;&|`$()<>]", line):
                return "Rejected: shell metacharacters are not allowed."
            proc = subprocess.run(
                line,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
                executable="/bin/sh",
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            return out[:4000] or f"exit {proc.returncode}"
        except Exception as exc:
            logger.exception("security tool: %s", exc)
            return str(exc)
