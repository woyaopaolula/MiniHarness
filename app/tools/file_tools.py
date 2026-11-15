import os
import tempfile
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.tools.base import BaseTool
from app.tools.workspace import Workspace


class ReadFileArguments(BaseModel):
    """ReadFileTool 的外部参数契约。"""

    model_config = ConfigDict(extra="forbid")

    path: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
    ] = Field(description="Workspace-relative path to a UTF-8 text file.")


class SearchFilesArguments(BaseModel):
    """SearchFilesTool 的外部参数契约。"""

    model_config = ConfigDict(extra="forbid")

    query: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    ] = Field(description="Literal text to find in workspace files.")
    path: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
    ] = Field(default=".", description="Workspace-relative directory to search.")
    file_pattern: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    ] = Field(default="*.py", description="Glob pattern such as '*.py'.")
    max_results: int = Field(default=50, ge=1, le=200)
    case_sensitive: bool = False


class WriteFileArguments(BaseModel):
    """WriteFileTool 的外部参数契约。"""

    model_config = ConfigDict(extra="forbid")

    path: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
    ] = Field(description="Workspace-relative path to write.")
    content: str = Field(
        default="",
        max_length=1_000_000,
        description="Complete UTF-8 file content.",
    )
    create_parents: bool = Field(
        default=False,
        description="Create missing parent directories when true.",
    )


class ReadFileTool(BaseTool):
    """从指定工作区的子路径读取 UTF-8 文本文件。"""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        max_chars: int = 200_000,
    ) -> None:
        if max_chars < 1:
            raise ValueError("max_chars must be greater than zero")
        self._workspace = Workspace(workspace_root)
        self._max_chars = max_chars

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read a UTF-8 text file from the configured workspace. "
            "The path must be relative and cannot escape the workspace."
        )

    @property
    def arguments_model(self) -> type[BaseModel]:
        return ReadFileArguments

    def execute(self, **kwargs: Any) -> str:
        unexpected_args = set(kwargs) - {"path"}
        if unexpected_args:
            names = ", ".join(sorted(unexpected_args))
            raise TypeError(f"Unexpected argument(s): {names}")

        path_value = kwargs.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError("path must be a non-empty string")

        target = self._workspace.resolve_path(path_value)
        if not target.exists():
            raise FileNotFoundError(f"File does not exist: {path_value}")
        if not target.is_file():
            raise IsADirectoryError(f"Path is not a file: {path_value}")

        content = target.read_text(encoding="utf-8")
        if len(content) <= self._max_chars:
            return content

        omitted = len(content) - self._max_chars
        marker = f"\n...[{omitted} characters truncated]..."
        return content[: self._max_chars] + marker


class SearchFilesTool(BaseTool):
    """在 UTF-8 文本文件中搜索字面文本。"""

    _SKIPPED_DIRECTORIES = {
        ".git",
        ".pytest_cache",
        "__pycache__",
        "node_modules",
    }

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        max_file_bytes: int = 1_000_000,
        max_line_chars: int = 500,
    ) -> None:
        if max_file_bytes < 1:
            raise ValueError("max_file_bytes must be greater than zero")
        if max_line_chars < 1:
            raise ValueError("max_line_chars must be greater than zero")
        self._workspace = Workspace(workspace_root)
        self._max_file_bytes = max_file_bytes
        self._max_line_chars = max_line_chars

    @property
    def name(self) -> str:
        return "search_files"

    @property
    def description(self) -> str:
        return (
            "Search for literal text in UTF-8 files under a workspace-relative "
            "directory. Results include file paths, line numbers, and bounded "
            "line excerpts."
        )

    @property
    def arguments_model(self) -> type[BaseModel]:
        return SearchFilesArguments

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        query: str = kwargs["query"]
        search_root = self._workspace.resolve_path(kwargs["path"], allow_root=True)
        if not search_root.exists():
            raise FileNotFoundError(f"Search path does not exist: {kwargs['path']}")
        if not search_root.is_dir():
            raise NotADirectoryError(
                f"Search path is not a directory: {kwargs['path']}"
            )

        file_pattern: str = kwargs["file_pattern"]
        pattern_path = Path(file_pattern)
        if (
            pattern_path.is_absolute()
            or pattern_path.drive
            or pattern_path.root
            or ".." in pattern_path.parts
        ):
            raise ValueError("file_pattern must stay inside the search directory")

        max_results: int = kwargs["max_results"]
        case_sensitive: bool = kwargs["case_sensitive"]
        needle = query if case_sensitive else query.casefold()

        matches: list[dict[str, Any]] = []
        files_scanned = 0
        truncated = False

        candidates = sorted(
            search_root.rglob(file_pattern),
            key=lambda candidate: candidate.as_posix(),
        )
        for candidate in candidates:
            if not candidate.is_file() or candidate.is_symlink():
                continue

            relative_to_search = candidate.relative_to(search_root)
            if any(
                part in self._SKIPPED_DIRECTORIES
                for part in relative_to_search.parts
            ):
                continue

            resolved = candidate.resolve()
            if not resolved.is_relative_to(self._workspace.root):
                continue
            if resolved.stat().st_size > self._max_file_bytes:
                continue

            files_scanned += 1
            try:
                lines = resolved.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue

            for line_number, line in enumerate(lines, start=1):
                haystack = line if case_sensitive else line.casefold()
                if needle not in haystack:
                    continue
                if len(matches) >= max_results:
                    truncated = True
                    break
                matches.append(
                    {
                        "path": self._workspace.relative_path(resolved),
                        "line": line_number,
                        "text": line[: self._max_line_chars],
                    }
                )

            if truncated:
                break

        return {
            "matches": matches,
            "truncated": truncated,
            "files_scanned": files_scanned,
        }


class WriteFileTool(BaseTool):
    """以原子替换方式写入工作区内的 UTF-8 文本文件。"""

    _PROTECTED_DIRECTORIES = {".agents", ".codex", ".git"}
    _PROTECTED_FILES = {".env"}

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        max_content_chars: int = 1_000_000,
    ) -> None:
        if max_content_chars < 1:
            raise ValueError("max_content_chars must be greater than zero")
        self._workspace = Workspace(workspace_root)
        self._max_content_chars = max_content_chars

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Replace a UTF-8 text file inside the workspace using an atomic "
            "write. Git metadata, agent configuration, and .env are protected."
        )

    @property
    def arguments_model(self) -> type[BaseModel]:
        return WriteFileArguments

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        path_value: str = kwargs["path"]
        content: str = kwargs["content"]
        create_parents: bool = kwargs["create_parents"]

        if len(content) > self._max_content_chars:
            raise ValueError(
                f"content exceeds the {self._max_content_chars}-character limit"
            )

        target = self._workspace.resolve_path(path_value)
        relative_path = target.relative_to(self._workspace.root)
        lowered_parts = {part.casefold() for part in relative_path.parts}
        if lowered_parts & self._PROTECTED_DIRECTORIES:
            raise ValueError("path targets a protected directory")
        if relative_path.name.casefold() in self._PROTECTED_FILES:
            raise ValueError("path targets a protected file")

        if target.exists() and not target.is_file():
            raise IsADirectoryError(f"Path is not a file: {path_value}")

        parent = target.parent
        if not parent.exists():
            if not create_parents:
                raise FileNotFoundError(
                    f"Parent directory does not exist: {parent.name}"
                )
            parent.mkdir(parents=True, exist_ok=True)
        if not parent.is_dir():
            raise NotADirectoryError(f"Parent path is not a directory: {parent.name}")

        created = not target.exists()
        encoded_size = len(content.encode("utf-8"))
        descriptor, temporary_name = tempfile.mkstemp(
            dir=parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
            os.replace(temporary_path, target)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

        return {
            "path": self._workspace.relative_path(target),
            "bytes_written": encoded_size,
            "created": created,
        }
