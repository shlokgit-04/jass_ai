"""
CPU, memory, and responsiveness metrics for dashboard and throttling.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import psutil

logger = logging.getLogger(__name__)


@dataclass
class SystemSnapshot:
    cpu_percent: float
    memory_percent: float
    timestamp: float


class PerformanceMonitor:
    """
    Background sampler that keeps recent CPU/memory readings without blocking callers.
    """

    def __init__(self, interval_sec: float = 2.0) -> None:
        self._interval = interval_sec
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: Optional[SystemSnapshot] = None
        self._callbacks: list[Callable[[SystemSnapshot], None]] = []

    def add_callback(self, cb: Callable[[SystemSnapshot], None]) -> None:
        with self._lock:
            self._callbacks.append(cb)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="JASS-PerfMon", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def snapshot(self) -> SystemSnapshot:
        with self._lock:
            if self._latest:
                return self._latest
        return self._capture()

    def _capture(self) -> SystemSnapshot:
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
        except Exception as exc:
            logger.warning("performance_monitor capture failed: %s", exc)
            cpu, mem = 0.0, 0.0
        return SystemSnapshot(cpu_percent=cpu, memory_percent=mem, timestamp=time.time())

    def _loop(self) -> None:
        while not self._stop.is_set():
            snap = self._capture()
            with self._lock:
                self._latest = snap
            for cb in list(self._callbacks):
                try:
                    cb(snap)
                except Exception as exc:
                    logger.debug("perf callback error: %s", exc)
            self._stop.wait(self._interval)
