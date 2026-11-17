import json
from time import perf_counter
from typing import Any, Protocol

from app.core.model import ModelAdapter
from app.models.agent import (
    AgentEvent,
    AgentEventType,
    AgentRunResult,
    ChatMessage,
    RunStatus,
    TokenUsage,
    ToolCallRecord,
    ToolDefinition,
)
from app.tools.executor import ToolExecutionResult, ToolExecutor
from app.tools.registry import ToolRegistry

DEFAULT_SYSTEM_PROMPT = (
    "You are a coding agent. Use the available tools to inspect and modify "
    "the workspace. Do not claim that code works unless a tool result "
    "provides evidence. Use search_files to find tests instead of guessing "
    "paths. Re-read modified code, check every boundary condition in the "
    "request, and run relevant tests before returning a concise final answer."
)

VERIFICATION_PROMPT = (
    "Verification checkpoint: re-read every modified file and compare it "
    "against each requirement in the user's task. Check error paths, boundary "
    "conditions, and relevant tests. Use tools to fix anything that is still "
    "wrong. Otherwise return a final answer only after verification."
)


class AgentEventListener(Protocol):
    def emit(self, event: AgentEvent) -> None:
        """接收 Runtime 发出的实时执行事件。"""
        ...


class CancellationToken(Protocol):
    def is_set(self) -> bool:
        """返回是否已经请求取消。"""
        ...


class AgentRuntime:
    """执行“模型决策 → 工具调用 → 结果反馈”的多轮循环。"""

    def __init__(
        self,
        model: ModelAdapter,
        registry: ToolRegistry,
        executor: ToolExecutor,
        *,
        max_iterations: int = 8,
        max_tool_calls: int = 20,
        verification_rounds: int = 0,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        if max_tool_calls < 0:
            raise ValueError("max_tool_calls cannot be negative")
        if verification_rounds < 0:
            raise ValueError("verification_rounds cannot be negative")
        if not system_prompt.strip():
            raise ValueError("system_prompt must be non-empty")

        self._model = model
        self._registry = registry
        self._executor = executor
        self._max_iterations = max_iterations
        self._max_tool_calls = max_tool_calls
        self._verification_rounds = verification_rounds
        self._system_prompt = system_prompt

    def run(
        self,
        task: str,
        *,
        task_id: str | None = None,
        event_listener: AgentEventListener | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> AgentRunResult:
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")

        started_at = perf_counter()
        messages = [
            ChatMessage(role="system", content=self._system_prompt),
            ChatMessage(role="user", content=task),
        ]
        tools = [
            ToolDefinition.model_validate(definition)
            for definition in self._registry.list_tool_definitions()
        ]
        _emit(
            event_listener,
            "run_started",
            None,
            {
                "task": task,
                "task_id": task_id,
                "available_tools": [tool.name for tool in tools],
                "max_iterations": self._max_iterations,
                "max_tool_calls": self._max_tool_calls,
            },
        )
        records: list[ToolCallRecord] = []
        iterations = 0
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        has_usage = False
        workspace_mutated = False
        remaining_verifications = self._verification_rounds

        while iterations < self._max_iterations:
            if _is_cancelled(cancellation_token):
                return self._cancelled_result(
                    started_at,
                    task_id,
                    iterations,
                    records,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    has_usage,
                    event_listener,
                )
            iterations += 1
            try:
                response = self._model.complete(messages, tools)
            except Exception as exc:
                return self._result(
                    started_at,
                    task_id=task_id,
                    status="failed",
                    stop_reason="model_error",
                    error=str(exc) or exc.__class__.__name__,
                    iterations=iterations,
                    records=records,
                    token_usage=_token_usage(
                        has_usage,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
                    ),
                    event_listener=event_listener,
                )

            _emit(
                event_listener,
                "model_response",
                iterations,
                response.model_dump(mode="json"),
            )
            if response.usage is not None:
                has_usage = True
                prompt_tokens += response.usage.prompt_tokens
                completion_tokens += response.usage.completion_tokens
                total_tokens += response.usage.total_tokens

            if _is_cancelled(cancellation_token):
                return self._cancelled_result(
                    started_at,
                    task_id,
                    iterations,
                    records,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    has_usage,
                    event_listener,
                )

            if response.tool_calls:
                messages.append(
                    ChatMessage(
                        role="assistant",
                        content=response.content,
                        tool_calls=response.tool_calls,
                    )
                )
                for call in response.tool_calls:
                    if _is_cancelled(cancellation_token):
                        return self._cancelled_result(
                            started_at,
                            task_id,
                            iterations,
                            records,
                            prompt_tokens,
                            completion_tokens,
                            total_tokens,
                            has_usage,
                            event_listener,
                        )
                    if len(records) >= self._max_tool_calls:
                        return self._result(
                            started_at,
                            task_id=task_id,
                            status="tool_call_limit",
                            stop_reason="tool_call_limit",
                            error=(
                                f"Maximum tool calls reached: "
                                f"{self._max_tool_calls}"
                            ),
                            iterations=iterations,
                            records=records,
                            token_usage=_token_usage(
                                has_usage,
                                prompt_tokens,
                                completion_tokens,
                                total_tokens,
                            ),
                            event_listener=event_listener,
                        )

                    _emit(
                        event_listener,
                        "tool_call_started",
                        iterations,
                        {
                            "call_id": call.id,
                            "tool_name": call.name,
                            "arguments": call.arguments,
                        },
                    )
                    tool_result = self._executor.execute(
                        call.name,
                        call.arguments,
                    )
                    record = ToolCallRecord(
                        iteration=iterations,
                        call_id=call.id,
                        tool_name=call.name,
                        arguments=call.arguments,
                        result=tool_result,
                    )
                    records.append(record)
                    if call.name == "write_file" and tool_result.success:
                        workspace_mutated = True
                    _emit(
                        event_listener,
                        "tool_call_completed",
                        iterations,
                        {"record": record.model_dump(mode="json")},
                    )
                    messages.append(
                        ChatMessage(
                            role="tool",
                            content=_serialize_tool_result(tool_result),
                            tool_call_id=call.id,
                            tool_name=call.name,
                        )
                    )
                continue

            if response.content and response.content.strip():
                if workspace_mutated and remaining_verifications > 0:
                    remaining_verifications -= 1
                    messages.append(
                        ChatMessage(role="assistant", content=response.content)
                    )
                    messages.append(
                        ChatMessage(role="user", content=VERIFICATION_PROMPT)
                    )
                    _emit(
                        event_listener,
                        "verification_requested",
                        iterations,
                        {
                            "remaining_verification_rounds": (
                                remaining_verifications
                            ),
                            "candidate_answer": response.content,
                        },
                    )
                    continue
                return self._result(
                    started_at,
                    task_id=task_id,
                    status="completed",
                    stop_reason="final_answer",
                    answer=response.content,
                    iterations=iterations,
                    records=records,
                    token_usage=_token_usage(
                        has_usage,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
                    ),
                    event_listener=event_listener,
                )

            return self._result(
                started_at,
                task_id=task_id,
                status="failed",
                stop_reason="empty_model_response",
                error="Model returned neither content nor tool calls",
                iterations=iterations,
                records=records,
                token_usage=_token_usage(
                    has_usage,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                ),
                event_listener=event_listener,
            )

        return self._result(
            started_at,
            task_id=task_id,
            status="iteration_limit",
            stop_reason="iteration_limit",
            error=f"Maximum iterations reached: {self._max_iterations}",
            iterations=iterations,
            records=records,
            token_usage=_token_usage(
                has_usage,
                prompt_tokens,
                completion_tokens,
                total_tokens,
            ),
            event_listener=event_listener,
        )

    def _cancelled_result(
        self,
        started_at: float,
        task_id: str | None,
        iterations: int,
        records: list[ToolCallRecord],
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        has_usage: bool,
        event_listener: AgentEventListener | None,
    ) -> AgentRunResult:
        return self._result(
            started_at,
            task_id=task_id,
            status="cancelled",
            stop_reason="cancellation_requested",
            error="Task cancellation was requested",
            iterations=iterations,
            records=records,
            token_usage=_token_usage(
                has_usage,
                prompt_tokens,
                completion_tokens,
                total_tokens,
            ),
            event_listener=event_listener,
        )

    def _result(
        self,
        started_at: float,
        *,
        task_id: str | None,
        status: RunStatus,
        stop_reason: str,
        iterations: int,
        records: list[ToolCallRecord],
        answer: str | None = None,
        error: str | None = None,
        token_usage: TokenUsage | None = None,
        event_listener: AgentEventListener | None,
    ) -> AgentRunResult:
        result = AgentRunResult(
            task_id=task_id,
            status=status,
            answer=answer,
            stop_reason=stop_reason,
            error=error,
            iterations=iterations,
            tool_call_count=len(records),
            tool_calls=records,
            token_usage=token_usage,
            elapsed_seconds=round(perf_counter() - started_at, 6),
        )
        _emit(
            event_listener,
            "run_finished",
            iterations,
            result.model_dump(mode="json", exclude={"tool_calls"}),
        )
        return result


def _serialize_tool_result(result: ToolExecutionResult) -> str:
    return json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _token_usage(
    has_usage: bool,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> TokenUsage | None:
    if not has_usage:
        return None
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def _emit(
    listener: AgentEventListener | None,
    event_type: AgentEventType,
    iteration: int | None,
    payload: dict[str, Any],
) -> None:
    if listener is None:
        return
    listener.emit(
        AgentEvent(
            event_type=event_type,
            iteration=iteration,
            payload=payload,
        )
    )


def _is_cancelled(token: CancellationToken | None) -> bool:
    return token is not None and token.is_set()
