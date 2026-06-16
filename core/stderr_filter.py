"""
Filter noisy ALSA/JACK messages on Linux stderr without hiding real errors.

This includes both Python-level stderr filtering and C-level handlers.
"""

from __future__ import annotations

import os
import sys
import ctypes
from typing import IO, Optional, TextIO

# Prevent JACK from complaining when it isn't running
os.environ["JACK_NO_START_SERVER"] = "1"

# Global reference to prevent garbage collection of the mapped C-callback
_alsa_error_handler = None

def _silence_alsa_c_level() -> None:
    global _alsa_error_handler
    try:
        ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
            None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
        )
        def py_error_handler(filename, line, function, err, fmt):
            pass
        _alsa_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
        asound = ctypes.cdll.LoadLibrary('libasound.so.2')
        asound.snd_lib_error_set_handler(_alsa_error_handler)
    except Exception:
        pass


_NOISE_SUBSTRINGS = (
    "JACK server",
    "Cannot connect to server socket",
    "JackShmReadWritePtr",
    "jack server",
    "ALSA lib",
    "Unknown PCM",
    "underrun",
    "overrun",
    "snd_pcm",
    "Cannot lock memory",
)


class FilteredStderr:
    def __init__(self, real: TextIO) -> None:
        self._real = real

    def write(self, s: str) -> int:
        if s and not s.isspace():
            for frag in _NOISE_SUBSTRINGS:
                if frag in s:
                    return len(s)
        self._real.write(s)
        return len(s)

    def flush(self) -> None:
        self._real.flush()

    def __getattr__(self, name: str):
        return getattr(self._real, name)


def install_stderr_filter() -> Optional[TextIO]:
    """Wrap sys.stderr; returns previous stderr for restoration."""
    _silence_alsa_c_level()
    prev = sys.stderr
    if isinstance(prev, FilteredStderr):
        return None
    sys.stderr = FilteredStderr(prev)  # type: ignore[assignment]
    return prev
