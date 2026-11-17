from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated


class CreateTaskRequest(BaseModel):
    prompt: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000),
    ] = Field(description="Coding task for the agent.")


class CancelTaskResponse(BaseModel):
    task_id: str
    cancellation_requested: bool
    message: str
