from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class EvaluationTaskSpec(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    prompt: str = Field(min_length=1)
    workspace_dir: str = "workspace"
    tests_dir: str = "evaluation_tests"
    max_iterations: int = Field(default=8, ge=1)
    max_tool_calls: int = Field(default=20, ge=0)


class ScriptedAction(BaseModel):
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ScriptedPlan(BaseModel):
    actions: list[ScriptedAction] = Field(default_factory=list)
    final_answer: str = "Completed."


class EvaluationCaseResult(BaseModel):
    task_id: str
    trial: int = Field(default=1, ge=1)
    task_success: bool
    agent_completed: bool
    agent_status: str
    stop_reason: str | None = None
    failure_stage: Literal["agent", "tests", "evaluation"] | None = None
    answer: str | None = None
    agent_error: str | None = None
    iterations: int = 0
    tool_call_count: int = 0
    tool_names: list[str] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    elapsed_seconds: float = Field(ge=0)
    tests_passed: bool = False
    test_exit_code: int | None = None
    test_output: str = ""


class EvaluationReport(BaseModel):
    suite: str
    mode: str
    model: str
    generated_at: datetime
    task_count: int
    passed_count: int
    task_success_rate: float = Field(ge=0, le=1)
    mean_tool_calls: float = Field(ge=0)
    mean_elapsed_seconds: float = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cases: list[EvaluationCaseResult]
