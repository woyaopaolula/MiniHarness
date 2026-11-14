from pathlib import Path

import pytest

from app.tools.file_tools import ReadFileTool


def test_read_file_returns_utf8_content(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("hello 世界", encoding="utf-8")

    tool = ReadFileTool(workspace)

    assert tool.execute(path="notes.txt") == "hello 世界"


def test_read_file_supports_nested_relative_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    nested = workspace / "src" / "package"
    nested.mkdir(parents=True)
    (nested / "module.py").write_text("value = 1\n", encoding="utf-8")

    content = ReadFileTool(workspace).execute(path="src/package/module.py")

    assert content == "value = 1\n"


def test_read_file_rejects_missing_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(FileNotFoundError, match="does not exist"):
        ReadFileTool(workspace).execute(path="missing.txt")


def test_read_file_rejects_parent_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="escapes"):
        ReadFileTool(workspace).execute(path="../secret.txt")


def test_read_file_rejects_absolute_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = tmp_path / "secret.txt"
    target.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="must be relative"):
        ReadFileTool(workspace).execute(path=str(target))


def test_read_file_rejects_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)

    with pytest.raises(IsADirectoryError, match="not a file"):
        ReadFileTool(workspace).execute(path="src")


@pytest.mark.parametrize("path", [None, "", "   ", 123])
def test_read_file_rejects_invalid_path(tmp_path: Path, path: object) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError, match="non-empty string"):
        ReadFileTool(workspace).execute(path=path)


def test_read_file_rejects_unknown_argument(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("hello", encoding="utf-8")

    with pytest.raises(TypeError, match="Unexpected argument"):
        ReadFileTool(workspace).execute(path="notes.txt", encoding="utf-8")


def test_read_file_requires_existing_workspace(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Workspace does not exist"):
        ReadFileTool(tmp_path / "missing")
