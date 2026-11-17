from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StoredTask(BaseModel):
    id: str
    prompt: str
    workspace: str
    status: str
    answer: str | None
    error: str | None
    stop_reason: str | None
    iterations: int
    tool_call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    elapsed_seconds: float | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class StoredTaskEvent(BaseModel):
    id: int
    task_id: str
    iteration: int | None
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class StoredToolCall(BaseModel):
    id: int
    task_id: str
    call_id: str
    iteration: int
    tool_name: str
    arguments: dict[str, Any]
    success: bool
    result: dict[str, Any]
    error: str | None
    execution_time: float = Field(ge=0)
    created_at: datetime
