from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.model import MockModelAdapter
from app.core.runtime import AgentRuntime
from app.core.task_service import TaskService
from app.models.agent import ModelResponse, TokenUsage, ToolCall
from app.storage.database import Database
from app.storage.models import TaskStatus
from app.storage.repository import TaskRepository
from app.tools.base import BaseTool
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry


class EchoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str


class EchoTool(BaseTool):
    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Return the provided message."

    @property
    def arguments_model(self) -> type[BaseModel]:
        return EchoArguments

    def execute(self, **kwargs: Any) -> str:
        return kwargs["message"]


def build_service(
    database: Database,
    workspace: Path,
    responses: list[ModelResponse],
) -> tuple[TaskService, TaskRepository, MockModelAdapter]:
    registry = ToolRegistry()
    registry.register(EchoTool())
    model = MockModelAdapter(responses)
    runtime = AgentRuntime(
        model,
        registry,
        ToolExecutor(registry),
    )
    repository = TaskRepository(database)
    return TaskService(repository, runtime, workspace), repository, model


def test_task_service_persists_trace_and_final_result(
    empty_mysql_database: Database,
    tmp_path: Path,
) -> None:
    responses = [
        ModelResponse(
            tool_calls=[
                ToolCall(id="call-1", name="echo", arguments={"message": "hello"})
            ],
            usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=2,
                total_tokens=12,
            ),
        ),
        ModelResponse(
            content="Finished.",
            usage=TokenUsage(
                prompt_tokens=20,
                completion_tokens=3,
                total_tokens=23,
            ),
        ),
    ]
    service, repository, _ = build_service(
        empty_mysql_database,
        tmp_path,
        responses,
    )

    result = service.run("Call echo.", task_id="task-service-complete")
    task = repository.get_task("task-service-complete")
    events = repository.list_events("task-service-complete")
    tool_calls = repository.list_tool_calls("task-service-complete")

    assert result.task_id == "task-service-complete"
    assert result.status == "completed"
    assert task.status == TaskStatus.COMPLETED
    assert task.answer == "Finished."
    assert task.total_tokens == 35
    assert [event.event_type for event in events] == [
        "run_started",
        "model_response",
        "tool_call_started",
        "tool_call_completed",
        "model_response",
        "run_finished",
    ]
    assert tool_calls[0].tool_name == "echo"
    assert tool_calls[0].success is True


def test_task_service_persists_failed_run(
    empty_mysql_database: Database,
    tmp_path: Path,
) -> None:
    service, repository, _ = build_service(
        empty_mysql_database,
        tmp_path,
        [ModelResponse(content="")],
    )

    result = service.run("Return nothing.", task_id="task-service-failed")
    task = repository.get_task("task-service-failed")

    assert result.status == "failed"
    assert task.status == TaskStatus.FAILED
    assert task.stop_reason == "empty_model_response"
    assert task.error == "Model returned neither content nor tool calls"
