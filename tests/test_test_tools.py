from pathlib import Path

import pytest

from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry
from app.tools.test_tools import RunTestsTool


def build_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    tests = workspace / "tests"
    tests.mkdir(parents=True)
    return workspace


def test_run_tests_reports_passing_suite(tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path)
    (workspace / "tests/test_pass.py").write_text(
        "def test_addition():\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )

    result = RunTestsTool(workspace).execute(test_path="tests")

    assert result["passed"] is True
    assert result["timed_out"] is False
    assert result["exit_code"] == 0
    assert result["test_path"] == "tests"


def test_run_tests_reports_failing_suite(tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path)
    (workspace / "tests/test_fail.py").write_text(
        "def test_addition():\n    assert 1 + 1 == 3\n",
        encoding="utf-8",
    )

    result = RunTestsTool(workspace).execute(test_path="tests")

    assert result["passed"] is False
    assert result["timed_out"] is False
    assert result["exit_code"] != 0
    assert "1 failed" in result["output"]


def test_run_tests_returns_structured_tool_result(tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path)
    (workspace / "tests/test_pass.py").write_text(
        "def test_truth():\n    assert True\n",
        encoding="utf-8",
    )
    registry = ToolRegistry()
    registry.register(RunTestsTool(workspace))

    result = ToolExecutor(registry).execute(
        "run_tests",
        {"test_path": "tests/test_pass.py"},
    )

    assert result.success is True
    assert result.data["passed"] is True


def test_run_tests_stops_after_timeout(tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path)
    (workspace / "tests/test_slow.py").write_text(
        "import time\n\n\ndef test_slow():\n    time.sleep(5)\n",
        encoding="utf-8",
    )

    result = RunTestsTool(workspace, timeout_seconds=0.5).execute(test_path="tests")

    assert result["passed"] is False
    assert result["timed_out"] is True
    assert result["duration"] < 5


def test_run_tests_truncates_large_output(tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path)
    (workspace / "tests/test_output.py").write_text(
        "def test_output():\n"
        "    print('x' * 5000)\n"
        "    assert True\n",
        encoding="utf-8",
    )

    result = RunTestsTool(workspace, max_output_chars=256).execute(
        test_path="tests"
    )

    assert result["passed"] is True
    assert result["output_truncated"] is True
    assert "characters truncated" in result["output"]
    assert len(result["output"]) <= 256


def test_run_tests_rejects_parent_traversal(tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path)

    with pytest.raises(ValueError, match="escapes"):
        RunTestsTool(workspace).execute(test_path="../outside")


def test_run_tests_rejects_pytest_options_through_executor(tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path)
    registry = ToolRegistry()
    registry.register(RunTestsTool(workspace))

    result = ToolExecutor(registry).execute(
        "run_tests",
        {"test_path": "--version"},
    )

    assert result.success is False
    assert result.error_type == "invalid_arguments"


def test_run_tests_rejects_missing_path(tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path)

    with pytest.raises(FileNotFoundError, match="does not exist"):
        RunTestsTool(workspace).execute(test_path="missing")
