import threading
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from app.core.model import MockModelAdapter
from app.core.runtime import AgentRuntime
from app.core.task_service import TaskService
from app.main import create_app
from app.models.agent import ModelResponse, ToolCall
from app.storage.database import Database
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
    model: Any,
) -> tuple[TaskService, TaskRepository]:
    registry = ToolRegistry()
    registry.register(EchoTool())
    runtime = AgentRuntime(model, registry, ToolExecutor(registry))
    repository = TaskRepository(database)
    return TaskService(repository, runtime, workspace), repository


def wait_for_status(
    client: TestClient,
    task_id: str,
    expected: set[str],
    *,
    timeout: float = 5,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/tasks/{task_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in expected:
            return last
        time.sleep(0.05)
    raise AssertionError(f"Task did not reach {expected}; last={last}")


def test_health_and_create_query_task_flow(
    empty_mysql_database: Database,
    tmp_path: Path,
) -> None:
    responses = [
        ModelResponse(
            tool_calls=[
                ToolCall(id="call-1", name="echo", arguments={"message": "hello"})
            ]
        ),
        ModelResponse(content="Finished."),
    ]
    service, repository = build_service(
        empty_mysql_database,
        tmp_path,
        MockModelAdapter(responses),
    )
    app = create_app(
        task_service=service,
        repository=repository,
        database=empty_mysql_database,
        max_workers=1,
    )

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.json() == {"status": "ok", "database": "mysql"}

        created = client.post("/tasks", json={"prompt": "Call echo."})
        assert created.status_code == 202
        task_id = created.json()["id"]
        assert created.json()["status"] == "PENDING"

        task = wait_for_status(client, task_id, {"COMPLETED"})
        events = client.get(f"/tasks/{task_id}/events")
        tool_calls = client.get(f"/tasks/{task_id}/tool-calls")

    assert task["answer"] == "Finished."
    assert [event["event_type"] for event in events.json()][0] == "run_started"
    assert tool_calls.json()[0]["tool_name"] == "echo"
    assert tool_calls.json()[0]["success"] is True


def test_cancel_endpoint_cooperatively_stops_task(
    empty_mysql_database: Database,
    tmp_path: Path,
) -> None:
    class BlockingModel:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.release = threading.Event()

        def complete(self, messages: Any, tools: Any) -> ModelResponse:
            self.started.set()
            self.release.wait(timeout=5)
            return ModelResponse(content="Finished after cancellation.")

    model = BlockingModel()
    service, repository = build_service(empty_mysql_database, tmp_path, model)
    app = create_app(
        task_service=service,
        repository=repository,
        database=empty_mysql_database,
        max_workers=1,
    )

    with TestClient(app) as client:
        created = client.post("/tasks", json={"prompt": "Slow task."})
        task_id = created.json()["id"]
        assert model.started.wait(timeout=3)

        cancelled = client.post(f"/tasks/{task_id}/cancel")
        assert cancelled.status_code == 202
        assert cancelled.json()["cancellation_requested"] is True

        model.release.set()
        task = wait_for_status(client, task_id, {"CANCELLED"})

    assert task["stop_reason"] == "cancellation_requested"


def test_task_endpoints_return_404_and_validate_body(
    empty_mysql_database: Database,
    tmp_path: Path,
) -> None:
    service, repository = build_service(
        empty_mysql_database,
        tmp_path,
        MockModelAdapter([]),
    )
    app = create_app(
        task_service=service,
        repository=repository,
        database=empty_mysql_database,
        max_workers=1,
    )

    with TestClient(app) as client:
        assert client.get("/tasks/missing").status_code == 404
        assert client.get("/tasks/missing/events").status_code == 404
        assert client.get("/tasks/missing/tool-calls").status_code == 404
        assert client.post("/tasks", json={"prompt": ""}).status_code == 422
