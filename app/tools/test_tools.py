import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from app.tools.base import BaseTool
from app.tools.workspace import Workspace


class RunTestsArguments(BaseModel):
    """RunTestsTool 的外部参数契约。"""

    model_config = ConfigDict(extra="forbid")

    test_path: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
    ] = Field(
        default="tests",
        description="Workspace-relative test file or directory for pytest.",
    )

    @field_validator("test_path")
    @classmethod
    def reject_pytest_options(cls, value: str) -> str:
        if value.startswith("-"):
            raise ValueError("test_path cannot start with '-'")
        return value


class RunTestsTool(BaseTool):
    """在受控工作区内运行固定形式的 pytest 命令。"""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        timeout_seconds: float = 30.0,
        max_output_chars: int = 20_000,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if max_output_chars < 256:
            raise ValueError("max_output_chars must be at least 256")
        self._workspace = Workspace(workspace_root)
        self._timeout_seconds = timeout_seconds
        self._max_output_chars = max_output_chars

    @property
    def name(self) -> str:
        return "run_tests"

    @property
    def description(self) -> str:
        return (
            "Run pytest against a workspace-relative test file or directory. "
            "The command is fixed; test_path cannot inject command options."
        )

    @property
    def arguments_model(self) -> type[BaseModel]:
        return RunTestsArguments

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        test_path: str = kwargs["test_path"]
        target = self._workspace.resolve_path(test_path, allow_root=True)
        if not target.exists():
            raise FileNotFoundError(f"Test path does not exist: {test_path}")
        if not target.is_file() and not target.is_dir():
            raise ValueError(f"Test path is not a file or directory: {test_path}")

        relative_target = self._workspace.relative_path(target) or "."
        command = [
            sys.executable,
            "-m",
            "pytest",
            relative_target,
        ]
        environment = os.environ.copy()
        environment.pop("PYTEST_ADDOPTS", None)
        environment["PYTHONIOENCODING"] = "utf-8"

        process_options: dict[str, Any] = {}
        if os.name == "nt":
            process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            process_options["start_new_session"] = True

        started_at = perf_counter()
        process = subprocess.Popen(
            command,
            cwd=self._workspace.root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=environment,
            **process_options,
        )

        timed_out = False
        try:
            output, _ = process.communicate(timeout=self._timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_tree(process)
            output, _ = process.communicate()

        duration = round(perf_counter() - started_at, 6)
        bounded_output, output_truncated = _truncate_middle(
            output or "",
            self._max_output_chars,
        )

        return {
            "test_path": relative_target,
            "passed": not timed_out and process.returncode == 0,
            "exit_code": process.returncode,
            "timed_out": timed_out,
            "duration": duration,
            "output": bounded_output,
            "output_truncated": output_truncated,
        }


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """尽力终止 pytest 及其子进程，然后清理直接子进程。"""

    if process.poll() is not None:
        return

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(process.pid, 9)
        except OSError:
            pass

    if process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _truncate_middle(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False

    marker = f"\n...[{len(text) - max_chars} characters truncated]...\n"
    remaining = max(max_chars - len(marker), 0)
    head_length = remaining * 3 // 4
    tail_length = remaining - head_length
    tail = text[-tail_length:] if tail_length else ""
    return text[:head_length] + marker + tail, True
