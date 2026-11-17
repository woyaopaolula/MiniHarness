from pathlib import Path

from app.core.runtime import AgentEventListener, AgentRuntime, CancellationToken
from app.models.agent import AgentEvent, AgentRunResult
from app.storage.models import TaskStatus
from app.storage.repository import TaskRepository
from app.storage.schemas import StoredTask


class RepositoryEventSink(AgentEventListener):
    """把 Runtime 事件立即追加到指定任务的事件表。"""

    def __init__(self, repository: TaskRepository, task_id: str) -> None:
        self._repository = repository
        self._task_id = task_id

    def emit(self, event: AgentEvent) -> None:
        self._repository.append_event(
            self._task_id,
            event.event_type,
            event.payload,
            iteration=event.iteration,
        )


class TaskService:
    """组合 Runtime 与 Repository，执行一次可持久追踪的 Agent 任务。"""

    def __init__(
        self,
        repository: TaskRepository,
        runtime: AgentRuntime,
        workspace: str | Path,
    ) -> None:
        self._repository = repository
        self._runtime = runtime
        self._workspace = str(Path(workspace).resolve())

    def run(self, prompt: str, *, task_id: str | None = None) -> AgentRunResult:
        task = self.create_task(prompt, task_id=task_id)
        return self.run_existing(task.id)

    def create_task(
        self,
        prompt: str,
        *,
        task_id: str | None = None,
    ) -> StoredTask:
        return self._repository.create_task(
            prompt,
            self._workspace,
            task_id=task_id,
        )

    def run_existing(
        self,
        task_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> AgentRunResult:
        task = self._repository.get_task(task_id)
        if task.status != TaskStatus.PENDING:
            raise ValueError(f"Task is not pending: {task.status}")
        self._repository.transition_task(task.id, TaskStatus.RUNNING)

        try:
            result = self._runtime.run(
                task.prompt,
                task_id=task.id,
                event_listener=RepositoryEventSink(self._repository, task.id),
                cancellation_token=cancellation_token,
            )
        except Exception as exc:
            self._repository.transition_task(
                task.id,
                TaskStatus.FAILED,
                error=f"Runtime exception: {exc}",
                stop_reason="runtime_exception",
            )
            raise

        try:
            for record in result.tool_calls:
                self._repository.record_tool_call(
                    task.id,
                    call_id=record.call_id,
                    iteration=record.iteration,
                    tool_name=record.tool_name,
                    arguments=record.arguments,
                    result=record.result.model_dump(mode="json"),
                )

            final_status = (
                TaskStatus.COMPLETED
                if result.status == "completed"
                else (
                    TaskStatus.CANCELLED
                    if result.status == "cancelled"
                    else TaskStatus.FAILED
                )
            )
            usage = result.token_usage
            self._repository.transition_task(
                task.id,
                final_status,
                answer=result.answer,
                error=result.error,
                stop_reason=result.stop_reason,
                iterations=result.iterations,
                tool_call_count=result.tool_call_count,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                elapsed_seconds=result.elapsed_seconds,
            )
        except Exception as exc:
            try:
                self._repository.transition_task(
                    task.id,
                    TaskStatus.FAILED,
                    error=f"Persistence error: {exc}",
                    stop_reason="persistence_error",
                )
            except Exception:
                # Preserve the original persistence failure.
                pass
            raise

        return result
