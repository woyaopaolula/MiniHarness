from types import SimpleNamespace
from typing import Any

import pytest

from app.core.model import OllamaModelAdapter, OpenAICompatibleModelAdapter
from app.models.agent import ChatMessage, ToolCall, ToolDefinition


class RecordingCompletions:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.request: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> Any:
        self.request = kwargs
        return self.response


def build_client(response: Any) -> tuple[Any, RecordingCompletions]:
    completions = RecordingCompletions(response)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
    )
    return client, completions


def test_openai_adapter_maps_request_and_tool_calls() -> None:
    raw_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="read_file",
            arguments='{"path":"src/app.py"}',
        ),
    )
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, tool_calls=[raw_call]),
                finish_reason="tool_calls",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    )
    client, completions = build_client(response)
    adapter = OpenAICompatibleModelAdapter(
        "test-model",
        client=client,
        temperature=0.2,
    )
    tools = [
        ToolDefinition(
            name="read_file",
            description="Read a file.",
            parameters={"type": "object", "properties": {}},
        )
    ]

    result = adapter.complete(
        [
            ChatMessage(role="system", content="You are an agent."),
            ChatMessage(role="user", content="Read the app."),
        ],
        tools,
    )

    assert completions.request is not None
    assert completions.request["model"] == "test-model"
    assert completions.request["tools"][0]["type"] == "function"
    assert completions.request["tool_choice"] == "auto"
    assert result.tool_calls == [
        ToolCall(id="call-1", name="read_file", arguments={"path": "src/app.py"})
    ]
    assert result.finish_reason == "tool_calls"
    assert result.usage is not None
    assert result.usage.total_tokens == 15


def test_openai_adapter_maps_assistant_and_tool_messages() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Finished.", tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=None,
    )
    client, completions = build_client(response)
    adapter = OpenAICompatibleModelAdapter("test-model", client=client)

    adapter.complete(
        [
            ChatMessage(
                role="assistant",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="read_file",
                        arguments={"path": "app.py"},
                    )
                ],
            ),
            ChatMessage(
                role="tool",
                content='{"success":true}',
                tool_call_id="call-1",
                tool_name="read_file",
            ),
        ],
        [],
    )

    assert completions.request is not None
    assistant_message, tool_message = completions.request["messages"]
    assert assistant_message["tool_calls"][0]["function"]["arguments"] == (
        '{"path":"app.py"}'
    )
    assert tool_message["tool_call_id"] == "call-1"
    assert "tools" not in completions.request


def test_openai_adapter_rejects_invalid_tool_argument_json() -> None:
    raw_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="read_file", arguments="{invalid"),
    )
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, tool_calls=[raw_call]),
                finish_reason="tool_calls",
            )
        ],
        usage=None,
    )
    client, _ = build_client(response)

    with pytest.raises(ValueError, match="Invalid JSON"):
        OpenAICompatibleModelAdapter("test-model", client=client).complete([], [])


def test_openai_adapter_rejects_non_object_tool_arguments() -> None:
    raw_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="read_file", arguments="[]"),
    )
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, tool_calls=[raw_call]),
                finish_reason="tool_calls",
            )
        ],
        usage=None,
    )
    client, _ = build_client(response)

    with pytest.raises(ValueError, match="JSON object"):
        OpenAICompatibleModelAdapter("test-model", client=client).complete([], [])


def test_openai_adapter_rejects_empty_choices() -> None:
    response = SimpleNamespace(choices=[], usage=None)
    client, _ = build_client(response)

    with pytest.raises(ValueError, match="choices"):
        OpenAICompatibleModelAdapter("test-model", client=client).complete([], [])


def test_openai_adapter_validates_configuration() -> None:
    with pytest.raises(ValueError, match="model"):
        OpenAICompatibleModelAdapter(" ")

    with pytest.raises(ValueError, match="temperature"):
        OpenAICompatibleModelAdapter("test-model", temperature=3)


def test_ollama_adapter_maps_local_model_response() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Local response.", tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=None,
    )
    client, completions = build_client(response)

    result = OllamaModelAdapter("qwen-test", client=client).complete([], [])

    assert result.content == "Local response."
    assert completions.request is not None
    assert completions.request["model"] == "qwen-test"
