#!/usr/bin/env python3
"""
Quick verification: syntax compile + one headless ``--text`` command (needs Ollama).

Run from repo root::

    python tools/verify_jass.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    print("[verify] compileall …")
    r = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(ROOT)],
        cwd=str(ROOT),
    )
    if r.returncode != 0:
        return r.returncode
    print("[verify] main.py --text …")
    r2 = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--text", "Reply with exactly one word: pong"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = (r2.stdout or "").strip()
    print("[verify] exit code:", r2.returncode)
    if out:
        print("[verify] reply snippet:", out[:300] + ("…" if len(out) > 300 else ""))
    if r2.stderr:
        print("[verify] stderr:", r2.stderr[-400:], file=sys.stderr)
    return 0 if r2.returncode == 0 and out else 1


if __name__ == "__main__":
    raise SystemExit(main())
