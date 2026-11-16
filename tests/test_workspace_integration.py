from pathlib import Path

from app.tools.executor import ToolExecutor
from app.tools.file_tools import ReadFileTool, SearchFilesTool, WriteFileTool
from app.tools.registry import ToolRegistry
from app.tools.test_tools import RunTestsTool


def test_tools_complete_a_small_code_repair_workflow(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "src"
    source.mkdir(parents=True)
    (source / "calculator.py").write_text(
        "def add(left: int, right: int) -> int:\n"
        "    return left - right\n",
        encoding="utf-8",
    )

    registry = ToolRegistry()
    registry.register(ReadFileTool(workspace))
    registry.register(SearchFilesTool(workspace))
    registry.register(WriteFileTool(workspace))
    registry.register(RunTestsTool(workspace))
    executor = ToolExecutor(registry)

    search_result = executor.execute(
        "search_files",
        {"query": "def add", "file_pattern": "*.py"},
    )
    assert search_result.success is True
    assert search_result.data["matches"][0]["path"] == "src/calculator.py"

    read_result = executor.execute(
        "read_file",
        {"path": "src/calculator.py"},
    )
    assert "left - right" in read_result.data

    write_source_result = executor.execute(
        "write_file",
        {
            "path": "src/calculator.py",
            "content": (
                "def add(left: int, right: int) -> int:\n"
                "    return left + right\n"
            ),
        },
    )
    assert write_source_result.success is True

    write_test_result = executor.execute(
        "write_file",
        {
            "path": "tests/test_calculator.py",
            "content": (
                "from src.calculator import add\n\n\n"
                "def test_add():\n"
                "    assert add(2, 3) == 5\n"
            ),
            "create_parents": True,
        },
    )
    assert write_test_result.success is True

    test_result = executor.execute(
        "run_tests",
        {"test_path": "tests"},
    )
    assert test_result.success is True
    assert test_result.data["passed"] is True
