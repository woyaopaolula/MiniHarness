from pathlib import Path

import pytest

from app.core.model import MockModelAdapter
from app.evaluation.runner import (
    EvaluationRunner,
    build_scripted_adapter,
    load_evaluation_tasks,
    summarize_report,
)
from app.models.agent import ModelResponse

TASK_ROOT = Path("data/evaluation/tasks").resolve()


@pytest.fixture(scope="module")
def evaluation_tasks():
    return load_evaluation_tasks(TASK_ROOT)


def test_evaluation_suite_loads_three_valid_tasks(evaluation_tasks) -> None:
    assert [task.spec.id for task in evaluation_tasks] == [
        "calculator_add",
        "normalize_tags",
        "parse_port",
    ]
    assert all(task.workspace.is_dir() for task in evaluation_tasks)
    assert all(task.tests.is_dir() for task in evaluation_tasks)


def test_golden_scripted_traces_pass_hidden_tests(evaluation_tasks) -> None:
    runner = EvaluationRunner()
    cases = []
    for task in evaluation_tasks:
        adapter = build_scripted_adapter(task.load_plan())
        factory = lambda workspace, adapter=adapter: adapter
        cases.append(runner.run_task(task, factory))

    report = summarize_report(
        cases,
        suite="tasks",
        mode="mock",
        model="scripted-golden",
    )

    assert report.task_count == 3
    assert report.passed_count == 3
    assert report.task_success_rate == 1.0
    assert all(case.tests_passed for case in cases)
    assert all(case.agent_completed for case in cases)


def test_agent_self_claim_without_code_change_is_not_success(
    evaluation_tasks,
) -> None:
    task = evaluation_tasks[0]
    runner = EvaluationRunner()
    adapter = MockModelAdapter([ModelResponse(content="I fixed everything.")])

    result = runner.run_task(task, lambda workspace: adapter)

    assert result.agent_completed is True
    assert result.answer == "I fixed everything."
    assert result.tests_passed is False
    assert result.task_success is False
    assert result.failure_stage == "tests"
