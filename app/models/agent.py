from typing import Any, Literal

from pydantic import BaseModel, Field

from app.tools.executor import ToolExecutionResult

MessageRole = Literal["system", "user", "assistant", "tool"]
RunStatus = Literal[
    "completed",
    "failed",
    "iteration_limit",
    "tool_call_limit",
]


class ToolDefinition(BaseModel):
    """发送给模型的工具名称、用途和参数 JSON Schema。"""

    name: str
    description: str
    parameters: dict[str, Any]


class ToolCall(BaseModel):
    """模型提出的一次工具调用建议。"""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    """运行时内部与模型适配器之间传递的统一消息格式。"""

    role: MessageRole
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None


class ModelRequest(BaseModel):
    """一次模型调用的完整输入快照，便于 Mock 测试和后续观测。"""

    messages: list[ChatMessage]
    tools: list[ToolDefinition]


class TokenUsage(BaseModel):
    """模型供应商报告的 Token 使用量。"""

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class ModelResponse(BaseModel):
    """模型适配器归一化后的输出。"""

    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str = "stop"
    usage: TokenUsage | None = None


class ToolCallRecord(BaseModel):
    """Agent 执行轨迹中的一个工具调用结果。"""

    iteration: int = Field(ge=1)
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    result: ToolExecutionResult


class AgentRunResult(BaseModel):
    """Agent 单次运行的最终状态和可观测数据。"""

    status: RunStatus
    answer: str | None = None
    stop_reason: str
    error: str | None = None
    iterations: int = Field(ge=0)
    tool_call_count: int = Field(ge=0)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    token_usage: TokenUsage | None = None
    elapsed_seconds: float = Field(ge=0)
