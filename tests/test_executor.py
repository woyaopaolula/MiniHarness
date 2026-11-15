from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.tools.base import BaseTool
from app.tools.executor import ToolExecutor
from app.tools.file_tools import ReadFileTool
from app.tools.registry import ToolRegistry


class EmptyArguments(BaseModel):
    pass


class ValueErrorTool(BaseTool):
    @property
    def name(self) -> str:
        return "value_error"

    @property
    def description(self) -> str:
        return "Raise an expected tool error."

    @property
    def arguments_model(self) -> type[BaseModel]:
        return EmptyArguments

    def execute(self, **kwargs: Any) -> None:
        raise ValueError("business rule rejected the operation")


class RuntimeErrorTool(ValueErrorTool):
    @property
    def name(self) -> str:
        return "runtime_error"

    @property
    def description(self) -> str:
        return "Raise an unexpected implementation error."

    def execute(self, **kwargs: Any) -> None:
        raise RuntimeError("implementation bug")


def build_executor(tmp_path: Path, *extra_tools: BaseTool) -> ToolExecutor:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("hello", encoding="utf-8")

    registry = ToolRegistry()
    registry.register(ReadFileTool(workspace))
    for tool in extra_tools:
        registry.register(tool)
    return ToolExecutor(registry)


def test_execute_returns_success_result(tmp_path: Path) -> None:
    result = build_executor(tmp_path).execute(
        "read_file",
        {"path": "hello.txt"},
    )

    assert result.success is True
    assert result.tool_name == "read_file"
    assert result.data == "hello"
    assert result.error is None
    assert result.error_type is None
    assert result.execution_time >= 0


def test_execute_returns_tool_not_found(tmp_path: Path) -> None:
    result = build_executor(tmp_path).execute("missing", {})

    assert result.success is False
    assert result.error_type == "tool_not_found"
    assert "missing" in (result.error or "")


def test_execute_rejects_invalid_tool_name(tmp_path: Path) -> None:
    result = build_executor(tmp_path).execute(None, {})  # type: ignore[arg-type]

    assert result.success is False
    assert result.error_type == "invalid_tool_name"
    assert result.tool_name == "None"


def test_execute_rejects_missing_arguments(tmp_path: Path) -> None:
    result = build_executor(tmp_path).execute("read_file", {})

    assert result.success is False
    assert result.error_type == "invalid_arguments"
    assert "path" in (result.error or "")


def test_execute_rejects_wrong_argument_type(tmp_path: Path) -> None:
    result = build_executor(tmp_path).execute("read_file", {"path": 123})

    assert result.success is False
    assert result.error_type == "invalid_arguments"
    assert "string" in (result.error or "")


def test_execute_rejects_extra_arguments(tmp_path: Path) -> None:
    result = build_executor(tmp_path).execute(
        "read_file",
        {"path": "hello.txt", "unexpected": True},
    )

    assert result.success is False
    assert result.error_type == "invalid_arguments"
    assert "unexpected" in (result.error or "")


def test_execute_rejects_non_object_arguments(tmp_path: Path) -> None:
    result = build_executor(tmp_path).execute(
        "read_file",
        ["hello.txt"],  # type: ignore[arg-type]
    )

    assert result.success is False
    assert result.error_type == "invalid_arguments"


def test_execute_converts_tool_value_error(tmp_path: Path) -> None:
    executor = build_executor(tmp_path, ValueErrorTool())

    result = executor.execute("value_error")

    assert result.success is False
    assert result.error == "business rule rejected the operation"
    assert result.error_type == "execution_error"


def test_execute_contains_unexpected_tool_exception(tmp_path: Path) -> None:
    executor = build_executor(tmp_path, RuntimeErrorTool())

    result = executor.execute("runtime_error")

    assert result.success is False
    assert result.error == "implementation bug"
    assert result.error_type == "internal_error"
