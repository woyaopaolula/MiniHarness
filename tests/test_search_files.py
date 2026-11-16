from pathlib import Path

import pytest

from app.tools.executor import ToolExecutor
from app.tools.file_tools import SearchFilesTool
from app.tools.registry import ToolRegistry


def test_search_files_finds_case_insensitive_matches(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "src"
    source.mkdir(parents=True)
    (source / "app.py").write_text(
        "def calculate_total():\n    return NEEDLE + 1\n",
        encoding="utf-8",
    )

    result = SearchFilesTool(workspace).execute(
        query="needle",
        path=".",
        file_pattern="*.py",
        max_results=20,
        case_sensitive=False,
    )

    assert result["truncated"] is False
    assert result["matches"] == [
        {
            "path": "src/app.py",
            "line": 2,
            "text": "    return NEEDLE + 1",
        }
    ]


def test_search_files_respects_case_sensitivity(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "example.py").write_text("Needle\nneedle\n", encoding="utf-8")

    matches = SearchFilesTool(workspace).execute(
        query="Needle",
        path=".",
        file_pattern="*.py",
        max_results=20,
        case_sensitive=True,
    )["matches"]

    assert [match["line"] for match in matches] == [1]


def test_search_files_treats_regex_characters_as_literal_text(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "example.py").write_text(
        "values = array[0]\nother = array0\n",
        encoding="utf-8",
    )

    matches = SearchFilesTool(workspace).execute(
        query="[",
        path=".",
        file_pattern="*.py",
        max_results=20,
        case_sensitive=False,
    )["matches"]

    assert [match["line"] for match in matches] == [1]


def test_search_files_respects_file_pattern(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("needle", encoding="utf-8")
    (workspace / "code.py").write_text("needle", encoding="utf-8")

    matches = SearchFilesTool(workspace).execute(
        query="needle",
        path=".",
        file_pattern="*.md",
        max_results=20,
        case_sensitive=False,
    )["matches"]

    assert [match["path"] for match in matches] == ["notes.md"]


def test_search_files_skips_generated_directories(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    generated = workspace / "__pycache__"
    generated.mkdir(parents=True)
    (generated / "cached.py").write_text("needle", encoding="utf-8")
    (workspace / "source.py").write_text("needle", encoding="utf-8")

    matches = SearchFilesTool(workspace).execute(
        query="needle",
        path=".",
        file_pattern="*.py",
        max_results=20,
        case_sensitive=False,
    )["matches"]

    assert [match["path"] for match in matches] == ["source.py"]


def test_search_files_marks_results_as_truncated(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "many.py").write_text("needle\nneedle\nneedle\n", encoding="utf-8")

    result = SearchFilesTool(workspace).execute(
        query="needle",
        path=".",
        file_pattern="*.py",
        max_results=2,
        case_sensitive=False,
    )

    assert len(result["matches"]) == 2
    assert result["truncated"] is True


def test_search_files_skips_binary_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "binary.py").write_bytes(b"\xff\xfe\x00needle")
    (workspace / "text.py").write_text("needle", encoding="utf-8")

    matches = SearchFilesTool(workspace).execute(
        query="needle",
        path=".",
        file_pattern="*.py",
        max_results=20,
        case_sensitive=False,
    )["matches"]

    assert [match["path"] for match in matches] == ["text.py"]


def test_search_files_rejects_parent_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError, match="escapes"):
        SearchFilesTool(workspace).execute(
            query="needle",
            path="../outside",
            file_pattern="*.py",
            max_results=20,
            case_sensitive=False,
        )


def test_search_files_works_through_executor(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "example.py").write_text("needle", encoding="utf-8")
    registry = ToolRegistry()
    registry.register(SearchFilesTool(workspace))

    result = ToolExecutor(registry).execute(
        "search_files",
        {"query": "needle", "file_pattern": "*.py"},
    )

    assert result.success is True
    assert result.data["matches"][0]["path"] == "example.py"
