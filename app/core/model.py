from abc import ABC, abstractmethod
from collections.abc import Sequence
import json
from typing import Any

from app.models.agent import (
    ChatMessage,
    ModelRequest,
    ModelResponse,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)


class ModelAdapter(ABC):
    """屏蔽不同 LLM 接口差异的统一模型接口。"""

    @abstractmethod
    def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
    ) -> ModelResponse:
        """根据消息历史与可用工具返回下一轮模型响应。"""


class MockModelAdapter(ModelAdapter):
    """按预设顺序返回响应，用于确定性测试 Agent Loop。"""

    def __init__(self, responses: Sequence[ModelResponse]) -> None:
        self._responses = list(responses)
        self._next_response = 0
        self.requests: list[ModelRequest] = []

    @property
    def remaining_responses(self) -> int:
        return len(self._responses) - self._next_response

    def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
    ) -> ModelResponse:
        self.requests.append(
            ModelRequest(
                messages=[message.model_copy(deep=True) for message in messages],
                tools=[tool.model_copy(deep=True) for tool in tools],
            )
        )
        if self._next_response >= len(self._responses):
            raise RuntimeError("Mock model has no responses remaining")

        response = self._responses[self._next_response]
        self._next_response += 1
        return response.model_copy(deep=True)


class OpenAICompatibleModelAdapter(ModelAdapter):
    """通过 OpenAI Chat Completions 接口调用兼容模型。"""

    def __init__(
        self,
        model: str,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.0,
    ) -> None:
        if not model.strip():
            raise ValueError("model must be a non-empty string")
        if not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")

        self._model = model
        self._temperature = temperature
        if client is not None:
            self._client = client
            return

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is required when client is not provided"
            ) from exc

        client_options: dict[str, Any] = {}
        if api_key is not None:
            client_options["api_key"] = api_key
        if base_url is not None:
            client_options["base_url"] = base_url
        self._client = OpenAI(**client_options)

    def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
    ) -> ModelResponse:
        request: dict[str, Any] = {
            "model": self._model,
            "messages": [_to_openai_message(message) for message in messages],
            "temperature": self._temperature,
        }
        if tools:
            request["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]
            request["tool_choice"] = "auto"

        response = self._client.chat.completions.create(**request)
        if not response.choices:
            raise ValueError("Model response did not contain any choices")

        choice = response.choices[0]
        message = choice.message
        parsed_calls = [
            _parse_openai_tool_call(call)
            for call in (getattr(message, "tool_calls", None) or [])
        ]
        usage = _parse_usage(getattr(response, "usage", None))

        return ModelResponse(
            content=message.content,
            tool_calls=parsed_calls,
            finish_reason=getattr(choice, "finish_reason", None) or "stop",
            usage=usage,
        )


class OllamaModelAdapter(OpenAICompatibleModelAdapter):
    """通过 Ollama 的 OpenAI 兼容接口运行本地开源模型。"""

    def __init__(
        self,
        model: str = "qwen2.5-coder:3b",
        *,
        client: Any | None = None,
        base_url: str = "http://127.0.0.1:11434/v1",
        temperature: float = 0.0,
    ) -> None:
        super().__init__(
            model,
            client=client,
            api_key="ollama",
            base_url=base_url,
            temperature=temperature,
        )


def _to_openai_message(message: ChatMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": message.role,
        "content": message.content,
    }
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(
                        call.arguments,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            }
            for call in message.tool_calls
        ]
    if message.role == "tool":
        payload["tool_call_id"] = message.tool_call_id
        payload["content"] = message.content or ""
    return payload


def _parse_openai_tool_call(raw_call: Any) -> ToolCall:
    raw_arguments = raw_call.function.arguments
    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON arguments for tool {raw_call.function.name}"
            ) from exc
    else:
        arguments = raw_arguments
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object")

    return ToolCall(
        id=raw_call.id,
        name=raw_call.function.name,
        arguments=arguments,
    )


def _parse_usage(raw_usage: Any | None) -> TokenUsage | None:
    if raw_usage is None:
        return None
    return TokenUsage(
        prompt_tokens=raw_usage.prompt_tokens,
        completion_tokens=raw_usage.completion_tokens,
        total_tokens=raw_usage.total_tokens,
    )
