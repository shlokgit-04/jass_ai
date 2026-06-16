"""
Central task queue with worker threads — keeps UI and voice paths responsive.
"""

from __future__ import annotations

import logging
import queue
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3


@dataclass(order=True)
class ScheduledTask:
    priority: TaskPriority
    created_seq: int = field(compare=False)
    task_id: str = field(compare=False)
    name: str = field(compare=False)
    fn: Callable[[], Any] = field(compare=False)
    on_done: Optional[Callable[[Any, Optional[BaseException]], None]] = field(
        default=None, compare=False
    )


class TaskScheduler:
    """
    Priority queue of callables executed by a pool of daemon workers.
    """

    def __init__(self, num_workers: int = 4) -> None:
        self._q: queue.PriorityQueue[tuple[int, int, Optional[ScheduledTask]]] = (
            queue.PriorityQueue()
        )
        self._workers: list[threading.Thread] = []
        self._stop = threading.Event()
        self._seq = 0
        self._seq_lock = threading.Lock()
        self._num_workers = max(1, num_workers)

    def start(self) -> None:
        self._stop.clear()
        for i in range(self._num_workers):
            t = threading.Thread(target=self._worker_loop, name=f"JASS-Worker-{i}", daemon=True)
            t.start()
            self._workers.append(t)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        for _ in self._workers:
            try:
                self._q.put_nowait((0, 0, None))
            except queue.Full:
                pass
        for t in self._workers:
            t.join(timeout=timeout)
        self._workers.clear()

    def submit(
        self,
        name: str,
        fn: Callable[[], Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        on_done: Optional[Callable[[Any, Optional[BaseException]], None]] = None,
    ) -> str:
        tid = str(uuid.uuid4())
        with self._seq_lock:
            self._seq += 1
            seq = self._seq
        task = ScheduledTask(
            priority=priority,
            created_seq=seq,
            task_id=tid,
            name=name,
            fn=fn,
            on_done=on_done,
        )
        # Lower tuple sorts first in PriorityQueue — invert priority value
        pri_val = -task.priority.value
        self._q.put((pri_val, seq, task))
        return tid

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                _, _, item = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                break
            result: Any = None
            err: Optional[BaseException] = None
            try:
                result = item.fn()
            except BaseException as exc:
                err = exc
                logger.error(
                    "Task %s (%s) failed: %s\n%s",
                    item.task_id,
                    item.name,
                    exc,
                    traceback.format_exc(),
                )
            finally:
                if item.on_done:
                    try:
                        item.on_done(result, err)
                    except Exception as cb_exc:
                        logger.debug("on_done error: %s", cb_exc)
                self._q.task_done()
