import threading
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from app.core.model import MockModelAdapter
from app.core.runtime import AgentRuntime
from app.models.agent import ModelResponse, TokenUsage, ToolCall
from app.tools.base import BaseTool
from app.tools.executor import ToolExecutor
from app.tools.file_tools import ReadFileTool, SearchFilesTool, WriteFileTool
from app.tools.registry import ToolRegistry
from app.tools.test_tools import RunTestsTool


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


def tool_call(
    call_id: str,
    name: str,
    arguments: dict[str, Any],
) -> ModelResponse:
    return ModelResponse(
        tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)],
        finish_reason="tool_calls",
    )


def build_runtime(
    responses: list[ModelResponse],
    *,
    workspace: Path | None = None,
    max_iterations: int = 8,
    max_tool_calls: int = 20,
) -> tuple[AgentRuntime, MockModelAdapter]:
    registry = ToolRegistry()
    registry.register(EchoTool())
    if workspace is not None:
        registry.register(ReadFileTool(workspace))
    model = MockModelAdapter(responses)
    runtime = AgentRuntime(
        model,
        registry,
        ToolExecutor(registry),
        max_iterations=max_iterations,
        max_tool_calls=max_tool_calls,
    )
    return runtime, model


def test_runtime_completes_without_tool_calls() -> None:
    runtime, model = build_runtime([ModelResponse(content="Finished.")])

    result = runtime.run("Explain the task.")

    assert result.status == "completed"
    assert result.answer == "Finished."
    assert result.iterations == 1
    assert result.tool_call_count == 0
    assert [message.role for message in model.requests[0].messages] == [
        "system",
        "user",
    ]


def test_runtime_executes_tool_and_feeds_result_to_model() -> None:
    responses = [
        tool_call("call-1", "echo", {"message": "hello"}),
        ModelResponse(content="Tool completed."),
    ]
    runtime, model = build_runtime(responses)

    result = runtime.run("Call echo.")

    assert result.status == "completed"
    assert result.iterations == 2
    assert result.tool_call_count == 1
    assert result.tool_calls[0].result.success is True
    tool_message = model.requests[1].messages[-1]
    assert tool_message.role == "tool"
    assert tool_message.tool_call_id == "call-1"
    assert '"data":"hello"' in (tool_message.content or "")


def test_runtime_feeds_tool_failure_back_to_model(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    responses = [
        tool_call("read-1", "read_file", {"path": "missing.py"}),
        ModelResponse(content="The file does not exist."),
    ]
    runtime, model = build_runtime(responses, workspace=workspace)

    result = runtime.run("Read the missing file.")

    assert result.status == "completed"
    assert result.tool_calls[0].result.success is False
    assert result.tool_calls[0].result.error_type == "execution_error"
    tool_message = model.requests[1].messages[-1]
    assert "does not exist" in (tool_message.content or "")


def test_runtime_executes_multiple_calls_from_one_response() -> None:
    responses = [
        ModelResponse(
            tool_calls=[
                ToolCall(id="call-1", name="echo", arguments={"message": "one"}),
                ToolCall(id="call-2", name="echo", arguments={"message": "two"}),
            ],
            finish_reason="tool_calls",
        ),
        ModelResponse(content="Both completed."),
    ]
    runtime, _ = build_runtime(responses)

    result = runtime.run("Call echo twice.")

    assert result.status == "completed"
    assert result.tool_call_count == 2
    assert [record.result.data for record in result.tool_calls] == ["one", "two"]


def test_runtime_stops_at_tool_call_budget() -> None:
    responses = [
        ModelResponse(
            tool_calls=[
                ToolCall(id="call-1", name="echo", arguments={"message": "one"}),
                ToolCall(id="call-2", name="echo", arguments={"message": "two"}),
            ]
        ),
        ModelResponse(content="Unused."),
    ]
    runtime, model = build_runtime(responses, max_tool_calls=1)

    result = runtime.run("Call echo twice.")

    assert result.status == "tool_call_limit"
    assert result.tool_call_count == 1
    assert model.remaining_responses == 1


def test_runtime_stops_at_iteration_limit() -> None:
    responses = [
        tool_call("call-1", "echo", {"message": "one"}),
        tool_call("call-2", "echo", {"message": "two"}),
        ModelResponse(content="Unused."),
    ]
    runtime, model = build_runtime(responses, max_iterations=2)

    result = runtime.run("Keep calling echo.")

    assert result.status == "iteration_limit"
    assert result.iterations == 2
    assert result.tool_call_count == 2
    assert model.remaining_responses == 1


def test_runtime_contains_model_error() -> None:
    runtime, _ = build_runtime([])

    result = runtime.run("Will fail.")

    assert result.status == "failed"
    assert result.stop_reason == "model_error"
    assert "no responses remaining" in (result.error or "")


def test_runtime_aggregates_token_usage() -> None:
    responses = [
        ModelResponse(
            tool_calls=[
                ToolCall(id="call-1", name="echo", arguments={"message": "one"})
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
                prompt_tokens=15,
                completion_tokens=3,
                total_tokens=18,
            ),
        ),
    ]
    runtime, _ = build_runtime(responses)

    result = runtime.run("Call echo.")

    assert result.token_usage == TokenUsage(
        prompt_tokens=25,
        completion_tokens=5,
        total_tokens=30,
    )


def test_runtime_rejects_empty_model_response() -> None:
    runtime, _ = build_runtime([ModelResponse(content="")])

    result = runtime.run("Will return nothing.")

    assert result.status == "failed"
    assert result.stop_reason == "empty_model_response"


def test_runtime_stops_when_cancellation_is_already_requested() -> None:
    token = threading.Event()
    token.set()
    runtime, model = build_runtime([ModelResponse(content="Unused.")])

    result = runtime.run("Cancel immediately.", cancellation_token=token)

    assert result.status == "cancelled"
    assert result.stop_reason == "cancellation_requested"
    assert result.iterations == 0
    assert model.remaining_responses == 1


def test_runtime_stops_after_model_notices_cancellation() -> None:
    token = threading.Event()
    runtime, _ = build_runtime([ModelResponse(content="Finished first.")])

    class CancellingListener:
        def emit(self, event: Any) -> None:
            if event.event_type == "run_started":
                token.set()

    result = runtime.run(
        "Cancel before the model call.",
        event_listener=CancellingListener(),
        cancellation_token=token,
    )

    assert result.status == "cancelled"
    assert result.iterations == 0


def test_runtime_requests_verification_after_workspace_write(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = ToolRegistry()
    registry.register(WriteFileTool(workspace))
    responses = [
        tool_call(
            "write-1",
            "write_file",
            {"path": "example.py", "content": "value = 1\n"},
        ),
        ModelResponse(content="First candidate answer."),
        ModelResponse(content="Verified final answer."),
    ]
    model = MockModelAdapter(responses)
    runtime = AgentRuntime(
        model,
        registry,
        ToolExecutor(registry),
        verification_rounds=1,
    )

    result = runtime.run("Write the file.")

    assert result.status == "completed"
    assert result.answer == "Verified final answer."
    assert result.iterations == 3
    assert model.requests[2].messages[-1].content.startswith(
        "Verification checkpoint:"
    )


def test_runtime_rejects_invalid_limits() -> None:
    registry = ToolRegistry()
    executor = ToolExecutor(registry)

    with pytest.raises(ValueError, match="max_iterations"):
        AgentRuntime(
            MockModelAdapter([]),
            registry,
            executor,
            max_iterations=0,
        )

    with pytest.raises(ValueError, match="max_tool_calls"):
        AgentRuntime(
            MockModelAdapter([]),
            registry,
            executor,
            max_tool_calls=-1,
        )


def test_mock_driven_runtime_repairs_code_and_runs_tests(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "src"
    source.mkdir(parents=True)
    (source / "calculator.py").write_text(
        "def add(left: int, right: int) -> int:\n"
        "    return left - right\n",
        encoding="utf-8",
    )

    fixed_source = (
        "def add(left: int, right: int) -> int:\n"
        "    return left + right\n"
    )
    responses = [
        tool_call(
            "search-1",
            "search_files",
            {"query": "def add", "file_pattern": "*.py"},
        ),
        tool_call("read-1", "read_file", {"path": "src/calculator.py"}),
        tool_call(
            "write-1",
            "write_file",
            {"path": "src/calculator.py", "content": fixed_source},
        ),
        tool_call(
            "write-2",
            "write_file",
            {
                "path": "tests/test_calculator.py",
                "content": (
                    "from src.calculator import add\n\n\n"
                    "def test_add():\n"
                    "    assert add(2, 3) == 5\n"
                ),
                "create_parents": True,
            },
        ),
        tool_call("test-1", "run_tests", {"test_path": "tests"}),
        ModelResponse(content="Fixed add() and verified the tests."),
    ]

    registry = ToolRegistry()
    registry.register(SearchFilesTool(workspace))
    registry.register(ReadFileTool(workspace))
    registry.register(WriteFileTool(workspace))
    registry.register(RunTestsTool(workspace))
    model = MockModelAdapter(responses)
    runtime = AgentRuntime(model, registry, ToolExecutor(registry))

    result = runtime.run("Fix add() and verify it with tests.")

    assert result.status == "completed"
    assert result.tool_call_count == 5
    assert result.tool_calls[-1].result.data["passed"] is True
    assert result.answer == "Fixed add() and verified the tests."
