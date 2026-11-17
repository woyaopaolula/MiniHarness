from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.storage.database import Database
from app.storage.models import (
    TaskEventRow,
    TaskRow,
    TaskStatus,
    ToolCallRow,
    utc_now,
)
from app.storage.schemas import StoredTask, StoredTaskEvent, StoredToolCall


class TaskNotFoundError(LookupError):
    pass


class InvalidTaskTransition(ValueError):
    pass


_ALLOWED_TRANSITIONS = {
    (TaskStatus.PENDING, TaskStatus.RUNNING),
    (TaskStatus.RUNNING, TaskStatus.COMPLETED),
    (TaskStatus.RUNNING, TaskStatus.FAILED),
    (TaskStatus.RUNNING, TaskStatus.INTERRUPTED),
}


class TaskRepository:
    """使用短事务读写任务状态、事件和工具调用。"""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create_task(
        self,
        prompt: str,
        workspace: str,
        *,
        task_id: str | None = None,
    ) -> StoredTask:
        if not prompt.strip():
            raise ValueError("prompt must be non-empty")
        if not workspace.strip():
            raise ValueError("workspace must be non-empty")

        row = TaskRow(
            id=task_id or str(uuid4()),
            prompt=prompt,
            workspace=workspace,
            status=TaskStatus.PENDING,
        )
        with self._database.session() as session, session.begin():
            session.add(row)
            session.flush()
            return _task_to_schema(row)

    def get_task(self, task_id: str) -> StoredTask:
        with self._database.session() as session:
            row = session.get(TaskRow, task_id)
            if row is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")
            return _task_to_schema(row)

    def transition_task(
        self,
        task_id: str,
        target: TaskStatus,
        *,
        answer: str | None = None,
        error: str | None = None,
        stop_reason: str | None = None,
        iterations: int = 0,
        tool_call_count: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        elapsed_seconds: float | None = None,
    ) -> StoredTask:
        now = utc_now()
        with self._database.session() as session, session.begin():
            row = session.scalar(
                select(TaskRow)
                .where(TaskRow.id == task_id)
                .with_for_update()
            )
            if row is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            current = TaskStatus(row.status)
            if (current, target) not in _ALLOWED_TRANSITIONS:
                raise InvalidTaskTransition(
                    f"Cannot transition task from {current} to {target}"
                )

            row.status = target
            row.updated_at = now
            row.answer = answer
            row.error = error
            row.stop_reason = stop_reason
            row.iterations = iterations
            row.tool_call_count = tool_call_count
            row.prompt_tokens = prompt_tokens
            row.completion_tokens = completion_tokens
            row.total_tokens = total_tokens
            row.elapsed_seconds = elapsed_seconds
            if target == TaskStatus.RUNNING:
                row.started_at = now
            elif target in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.INTERRUPTED,
            }:
                row.finished_at = now

            session.flush()
            return _task_to_schema(row)

    def append_event(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        iteration: int | None = None,
    ) -> StoredTaskEvent:
        now = utc_now()
        with self._database.session() as session, session.begin():
            task = session.get(TaskRow, task_id)
            if task is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            row = TaskEventRow(
                task_id=task_id,
                iteration=iteration,
                event_type=event_type,
                payload=payload,
                created_at=now,
            )
            session.add(row)
            # append_event 同时更新心跳，供中断检测判断任务是否已经停滞。
            task.updated_at = now
            session.flush()
            return _event_to_schema(row)

    def list_events(self, task_id: str) -> list[StoredTaskEvent]:
        self.get_task(task_id)
        with self._database.session() as session:
            rows = session.scalars(
                select(TaskEventRow)
                .where(TaskEventRow.task_id == task_id)
                .order_by(TaskEventRow.id)
            ).all()
            return [_event_to_schema(row) for row in rows]

    def record_tool_call(
        self,
        task_id: str,
        *,
        call_id: str,
        iteration: int,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> StoredToolCall:
        with self._database.session() as session, session.begin():
            if session.get(TaskRow, task_id) is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            row = ToolCallRow(
                task_id=task_id,
                call_id=call_id,
                iteration=iteration,
                tool_name=tool_name,
                arguments=arguments,
                success=bool(result["success"]),
                result=result,
                error=result.get("error"),
                execution_time=float(result["execution_time"]),
            )
            session.add(row)
            session.flush()
            return _tool_call_to_schema(row)

    def list_tool_calls(self, task_id: str) -> list[StoredToolCall]:
        self.get_task(task_id)
        with self._database.session() as session:
            rows = session.scalars(
                select(ToolCallRow)
                .where(ToolCallRow.task_id == task_id)
                .order_by(ToolCallRow.id)
            ).all()
            return [_tool_call_to_schema(row) for row in rows]

    def list_tasks_by_status(self, status: TaskStatus) -> list[StoredTask]:
        with self._database.session() as session:
            rows = session.scalars(
                select(TaskRow)
                .where(TaskRow.status == status)
                .order_by(TaskRow.created_at)
            ).all()
            return [_task_to_schema(row) for row in rows]

    def recover_stale_running_tasks(self, cutoff: datetime) -> int:
        """将 cutoff 之前没有任何事件的 RUNNING 任务安全标记为中断。"""

        now = utc_now()
        with self._database.session() as session, session.begin():
            rows = session.scalars(
                select(TaskRow)
                .where(
                    TaskRow.status == TaskStatus.RUNNING,
                    TaskRow.updated_at < cutoff,
                )
                .with_for_update()
            ).all()
            for row in rows:
                row.status = TaskStatus.INTERRUPTED
                row.error = "Task interrupted before reaching a terminal state"
                row.stop_reason = "stale_running_task"
                row.updated_at = now
                row.finished_at = now
            return len(rows)


def _task_to_schema(row: TaskRow) -> StoredTask:
    return StoredTask(
        id=row.id,
        prompt=row.prompt,
        workspace=row.workspace,
        status=row.status,
        answer=row.answer,
        error=row.error,
        stop_reason=row.stop_reason,
        iterations=row.iterations,
        tool_call_count=row.tool_call_count,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        total_tokens=row.total_tokens,
        elapsed_seconds=row.elapsed_seconds,
        created_at=row.created_at,
        updated_at=row.updated_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _event_to_schema(row: TaskEventRow) -> StoredTaskEvent:
    return StoredTaskEvent(
        id=row.id,
        task_id=row.task_id,
        iteration=row.iteration,
        event_type=row.event_type,
        payload=row.payload,
        created_at=row.created_at,
    )


def _tool_call_to_schema(row: ToolCallRow) -> StoredToolCall:
    return StoredToolCall(
        id=row.id,
        task_id=row.task_id,
        call_id=row.call_id,
        iteration=row.iteration,
        tool_name=row.tool_name,
        arguments=row.arguments,
        success=row.success,
        result=row.result,
        error=row.error,
        execution_time=row.execution_time,
        created_at=row.created_at,
    )
