import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.core.model import ModelAdapter
from app.core.runtime import AgentRuntime
from app.evaluation.models import (
    EvaluationCaseResult,
    EvaluationReport,
    EvaluationTaskSpec,
    ScriptedPlan,
)
from app.models.agent import ModelResponse, ToolCall
from app.tools.executor import ToolExecutor
from app.tools.file_tools import ReadFileTool, SearchFilesTool, WriteFileTool
from app.tools.registry import ToolRegistry
from app.tools.test_tools import RunTestsTool


@dataclass(frozen=True)
class EvaluationTask:
    root: Path
    spec: EvaluationTaskSpec

    @property
    def workspace(self) -> Path:
        return self.root / self.spec.workspace_dir

    @property
    def tests(self) -> Path:
        return self.root / self.spec.tests_dir

    @property
    def scripted_plan_path(self) -> Path:
        return self.root / "scripted_plan.json"

    def load_plan(self) -> ScriptedPlan:
        return ScriptedPlan.model_validate_json(
            self.scripted_plan_path.read_text(encoding="utf-8")
        )


def load_evaluation_tasks(root: str | Path) -> list[EvaluationTask]:
    suite_root = Path(root).resolve()
    tasks = []
    for manifest in sorted(suite_root.glob("*/task.json")):
        task_root = manifest.parent
        spec = EvaluationTaskSpec.model_validate_json(
            manifest.read_text(encoding="utf-8")
        )
        task = EvaluationTask(task_root, spec)
        for path in (task.workspace, task.tests):
            if not path.is_dir():
                raise ValueError(f"Evaluation directory does not exist: {path}")
            if not path.resolve().is_relative_to(task_root.resolve()):
                raise ValueError(f"Evaluation path escapes task root: {path}")
        tasks.append(task)
    if not tasks:
        raise ValueError(f"No evaluation tasks found under: {suite_root}")
    return tasks


def build_scripted_adapter(plan: ScriptedPlan) -> ModelAdapter:
    """把金标准动作转换成 Mock 模型响应，仅用于验证评测器自身。"""

    from app.core.model import MockModelAdapter

    responses = [
        ModelResponse(
            tool_calls=[
                ToolCall(
                    id=f"scripted-{index}",
                    name=action.tool_name,
                    arguments=action.arguments,
                )
            ],
            finish_reason="tool_calls",
        )
        for index, action in enumerate(plan.actions, start=1)
    ]
    responses.append(ModelResponse(content=plan.final_answer))
    return MockModelAdapter(responses)


class EvaluationRunner:
    """在隔离工作区中运行 Agent，并用隐藏测试独立评分。"""

    def run_task(
        self,
        task: EvaluationTask,
        model_factory: Any,
        *,
        trial: int = 1,
    ) -> EvaluationCaseResult:
        started_at = perf_counter()
        with tempfile.TemporaryDirectory(prefix=f"miniharness-{task.spec.id}-") as temp:
            workspace = Path(temp) / "workspace"
            shutil.copytree(task.workspace, workspace)
            registry = ToolRegistry()
            registry.register(ReadFileTool(workspace))
            registry.register(SearchFilesTool(workspace))
            registry.register(WriteFileTool(workspace))
            registry.register(RunTestsTool(workspace))
            model = model_factory(workspace)
            runtime = AgentRuntime(
                model,
                registry,
                ToolExecutor(registry),
                max_iterations=task.spec.max_iterations,
                max_tool_calls=task.spec.max_tool_calls,
            )

            agent_status = "exception"
            stop_reason = None
            answer = None
            agent_error = None
            iterations = 0
            tool_call_count = 0
            tool_names: list[str] = []
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            try:
                agent_result = runtime.run(task.spec.prompt)
                agent_status = agent_result.status
                stop_reason = agent_result.stop_reason
                answer = agent_result.answer
                agent_error = agent_result.error
                iterations = agent_result.iterations
                tool_call_count = agent_result.tool_call_count
                tool_names = [
                    record.tool_name for record in agent_result.tool_calls
                ]
                if agent_result.token_usage is not None:
                    prompt_tokens = agent_result.token_usage.prompt_tokens
                    completion_tokens = agent_result.token_usage.completion_tokens
                    total_tokens = agent_result.token_usage.total_tokens
            except Exception as exc:
                agent_error = str(exc) or exc.__class__.__name__

            evaluation_name = f"__evaluation_{uuid4().hex}"
            evaluation_path = workspace / evaluation_name
            shutil.copytree(task.tests, evaluation_path)
            try:
                test_result = RunTestsTool(workspace).execute(
                    test_path=evaluation_name
                )
                tests_passed = bool(test_result["passed"])
                test_exit_code = test_result["exit_code"]
                test_output = test_result["output"]
            except Exception as exc:
                tests_passed = False
                test_exit_code = None
                test_output = f"Evaluation failed: {exc}"

        elapsed = round(perf_counter() - started_at, 6)
        agent_completed = agent_status == "completed"
        failure_stage = _failure_stage(
            agent_completed=agent_completed,
            tests_passed=tests_passed,
            evaluation_failed=test_exit_code is None,
        )
        return EvaluationCaseResult(
            task_id=task.spec.id,
            trial=trial,
            # Only hidden tests determine task success.
            task_success=tests_passed,
            agent_completed=agent_completed,
            agent_status=agent_status,
            stop_reason=stop_reason,
            failure_stage=failure_stage,
            answer=answer,
            agent_error=agent_error,
            iterations=iterations,
            tool_call_count=tool_call_count,
            tool_names=tool_names,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            elapsed_seconds=elapsed,
            tests_passed=tests_passed,
            test_exit_code=test_exit_code,
            test_output=test_output,
        )


def summarize_report(
    cases: list[EvaluationCaseResult],
    *,
    suite: str,
    mode: str,
    model: str,
) -> EvaluationReport:
    if not cases:
        raise ValueError("At least one evaluation case is required")
    count = len(cases)
    passed = sum(case.task_success for case in cases)
    return EvaluationReport(
        suite=suite,
        mode=mode,
        model=model,
        generated_at=datetime.now(timezone.utc),
        task_count=count,
        passed_count=passed,
        task_success_rate=passed / count,
        mean_tool_calls=sum(case.tool_call_count for case in cases) / count,
        mean_elapsed_seconds=sum(case.elapsed_seconds for case in cases) / count,
        total_tokens=sum(case.total_tokens for case in cases),
        cases=cases,
    )


def _failure_stage(
    *,
    agent_completed: bool,
    tests_passed: bool,
    evaluation_failed: bool,
) -> str | None:
    if evaluation_failed:
        return "evaluation"
    if not tests_passed:
        return "agent" if not agent_completed else "tests"
    return None
