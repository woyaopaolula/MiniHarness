import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Event, Lock

from app.core.task_service import TaskService

logger = logging.getLogger(__name__)


@dataclass
class _RunningTask:
    cancellation: Event = field(default_factory=Event)
    future: Future | None = None


class TaskManager:
    """在进程内线程池中执行任务，并支持协作取消。"""

    def __init__(self, service: TaskService, *, max_workers: int = 2) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self._service = service
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="miniharness-task",
        )
        self._runs: dict[str, _RunningTask] = {}
        self._lock = Lock()

    def submit(self, task_id: str) -> None:
        with self._lock:
            existing = self._runs.get(task_id)
            if existing is not None and existing.future and not existing.future.done():
                raise ValueError(f"Task is already running: {task_id}")
            run = _RunningTask()
            run.future = self._executor.submit(self._execute, task_id, run)
            self._runs[task_id] = run

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            run = self._runs.get(task_id)
            if run is None:
                return False
            if run.future is not None and run.future.done():
                return False
            run.cancellation.set()
            return True

    def is_active(self, task_id: str) -> bool:
        with self._lock:
            run = self._runs.get(task_id)
            return bool(
                run is not None
                and run.future is not None
                and not run.future.done()
            )

    def shutdown(self) -> None:
        with self._lock:
            for run in self._runs.values():
                run.cancellation.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _execute(self, task_id: str, run: _RunningTask) -> None:
        try:
            self._service.run_existing(
                task_id,
                cancellation_token=run.cancellation,
            )
        except Exception:
            # TaskService normally records failures. This catches failures that
            # happen before that persistence boundary is available.
            logger.exception("Unhandled background task error: %s", task_id)
