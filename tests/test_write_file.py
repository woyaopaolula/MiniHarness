from pathlib import Path

import pytest

from app.tools.executor import ToolExecutor
from app.tools.file_tools import WriteFileTool
from app.tools.registry import ToolRegistry


def run_write(
    workspace: Path,
    *,
    path: str,
    content: str = "",
    create_parents: bool = False,
) -> dict:
    return WriteFileTool(workspace).execute(
        path=path,
        content=content,
        create_parents=create_parents,
    )


def test_write_file_creates_utf8_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_write(workspace, path="notes.txt", content="你好\nworld\n")

    assert result == {
        "path": "notes.txt",
        "bytes_written": len("你好\nworld\n".encode("utf-8")),
        "created": True,
    }
    assert (workspace / "notes.txt").read_text(encoding="utf-8") == "你好\nworld\n"


def test_write_file_overwrites_existing_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "notes.txt"
    target.write_text("old", encoding="utf-8")

    result = run_write(workspace, path="notes.txt", content="new")

    assert result["created"] is False
    assert target.read_text(encoding="utf-8") == "new"


def test_write_file_can_create_parent_directories(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    run_write(
        workspace,
        path="src/package/module.py",
        content="value = 1\n",
        create_parents=True,
    )

    assert (workspace / "src/package/module.py").read_text(encoding="utf-8") == (
        "value = 1\n"
    )


def test_write_file_rejects_missing_parent_by_default(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(FileNotFoundError, match="Parent directory"):
        run_write(workspace, path="src/module.py", content="value = 1\n")


def test_write_file_rejects_parent_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError, match="escapes"):
        run_write(workspace, path="../outside.txt", content="unsafe")


def test_write_file_rejects_absolute_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError, match="must be relative"):
        run_write(workspace, path=str(tmp_path / "outside.txt"), content="unsafe")


@pytest.mark.parametrize("path", [".git/config", ".codex/config.toml", ".agents/a"])
def test_write_file_rejects_protected_directories(
    tmp_path: Path,
    path: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError, match="protected"):
        run_write(workspace, path=path, content="unsafe", create_parents=True)


def test_write_file_rejects_dotenv(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError, match="protected"):
        run_write(workspace, path=".env", content="SECRET=value")


def test_write_file_rejects_directory_target(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)

    with pytest.raises(IsADirectoryError, match="not a file"):
        run_write(workspace, path="src", content="unsafe")


def test_write_file_works_through_executor(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = ToolRegistry()
    registry.register(WriteFileTool(workspace))

    result = ToolExecutor(registry).execute(
        "write_file",
        {"path": "example.py", "content": "value = 1\n"},
    )

    assert result.success is True
    assert result.data["created"] is True
    assert (workspace / "example.py").read_text(encoding="utf-8") == "value = 1\n"


def test_write_file_rejects_content_over_schema_limit(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = ToolRegistry()
    registry.register(WriteFileTool(workspace))

    result = ToolExecutor(registry).execute(
        "write_file",
        {"path": "large.txt", "content": "x" * 1_000_001},
    )

    assert result.success is False
    assert result.error_type == "invalid_arguments"
