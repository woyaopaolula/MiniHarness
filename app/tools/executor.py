import logging
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

ToolErrorType = Literal[
    "invalid_tool_name",
    "tool_not_found",
    "invalid_arguments",
    "execution_error",
    "internal_error",
]


class ToolExecutionResult(BaseModel):
    """一次工具调用的统一结果。"""

    success: bool
    tool_name: str
    data: Any = None
    error: str | None = None
    error_type: ToolErrorType | None = None
    execution_time: float = Field(ge=0, description="Total elapsed seconds.")


class ToolExecutor:
    """查找、校验并执行工具，保证调用方总能获得统一结果。"""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        started_at = perf_counter()

        if not isinstance(tool_name, str) or not tool_name:
            return self._result(
                started_at,
                tool_name=repr(tool_name),
                success=False,
                error="tool_name must be a non-empty string",
                error_type="invalid_tool_name",
            )

        try:
            tool = self._registry.get(tool_name)
        except KeyError:
            return self._result(
                started_at,
                tool_name=tool_name,
                success=False,
                error=f"Tool not found: {tool_name}",
                error_type="tool_not_found",
            )

        raw_arguments = {} if arguments is None else arguments
        try:
            validated_arguments = tool.arguments_model.model_validate(raw_arguments)
        except ValidationError as exc:
            return self._result(
                started_at,
                tool_name=tool_name,
                success=False,
                error=_format_validation_error(exc),
                error_type="invalid_arguments",
            )

        try:
            data = tool.execute(**validated_arguments.model_dump())
        except (ValueError, OSError) as exc:
            logger.warning("Tool %s failed: %s", tool_name, exc)
            return self._result(
                started_at,
                tool_name=tool_name,
                success=False,
                error=str(exc) or exc.__class__.__name__,
                error_type="execution_error",
            )
        except Exception as exc:
            # Unexpected exceptions indicate a tool bug. Log the traceback for
            # developers while returning a stable result to the Agent loop.
            logger.exception("Unexpected error while executing tool %s", tool_name)
            return self._result(
                started_at,
                tool_name=tool_name,
                success=False,
                error=str(exc) or exc.__class__.__name__,
                error_type="internal_error",
            )

        return self._result(
            started_at,
            tool_name=tool_name,
            success=True,
            data=data,
        )

    @staticmethod
    def _result(
        started_at: float,
        *,
        tool_name: str,
        success: bool,
        data: Any = None,
        error: str | None = None,
        error_type: ToolErrorType | None = None,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            success=success,
            tool_name=tool_name,
            data=data,
            error=error,
            error_type=error_type,
            execution_time=round(perf_counter() - started_at, 6),
        )


def _format_validation_error(exc: ValidationError) -> str:
    messages = []
    for detail in exc.errors(include_url=False):
        location = ".".join(str(part) for part in detail["loc"]) or "arguments"
        messages.append(f"{location}: {detail['msg']}")
    return "; ".join(messages)




