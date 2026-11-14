from typing import Any

import pytest

from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry


class EchoTool(BaseTool):
    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Return the provided message."

    def execute(self, **kwargs: Any) -> str:
        return str(kwargs.get("message", ""))


class InvalidNameTool(EchoTool):
    @property
    def name(self) -> str:
        return " "


class EmptyDescriptionTool(EchoTool):
    @property
    def description(self) -> str:
        return ""


def test_base_tool_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        BaseTool()


def test_register_get_list_and_execute_tool() -> None:
    registry = ToolRegistry()
    tool = EchoTool()

    registry.register(tool)

    assert len(registry) == 1
    assert registry.get("echo") is tool
    assert registry.list_tools() == [
        {"name": "echo", "description": "Return the provided message."}
    ]
    assert registry.get("echo").execute(message="hello") == "hello"


def test_register_rejects_non_tool() -> None:
    registry = ToolRegistry()

    with pytest.raises(TypeError, match="inherit from BaseTool"):
        registry.register("echo")


def test_register_rejects_duplicate_name() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(EchoTool())


@pytest.mark.parametrize("tool", [InvalidNameTool(), EmptyDescriptionTool()])
def test_register_rejects_invalid_metadata(tool: BaseTool) -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError):
        registry.register(tool)


def test_get_rejects_unknown_tool() -> None:
    registry = ToolRegistry()

    with pytest.raises(KeyError, match="not found"):
        registry.get("missing")
