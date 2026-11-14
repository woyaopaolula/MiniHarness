from pathlib import Path
from typing import Any

from app.tools.base import BaseTool


class ReadFileTool(BaseTool):
    """从指定工作区的子路径读取 UTF-8 文本文件。"""

    def __init__(self, workspace_root: str | Path) -> None:
        root = Path(workspace_root).expanduser()
        if not root.exists():
            raise FileNotFoundError(f"Workspace does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Workspace is not a directory: {root}")
        self._workspace_root = root.resolve()

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read a UTF-8 text file from the configured workspace. "
            "The path must be relative and cannot escape the workspace."
        )

    def execute(self, **kwargs: Any) -> str:
        unexpected_args = set(kwargs) - {"path"}
        if unexpected_args:
            names = ", ".join(sorted(unexpected_args))
            raise TypeError(f"Unexpected argument(s): {names}")

        path_value = kwargs.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError("path must be a non-empty string")

        relative_path = Path(path_value)
        if relative_path.is_absolute():
            raise ValueError("path must be relative to the workspace")

        # resolve() also normalizes symlinks, preventing a link in the
        # workspace from silently exposing a file outside its boundary.
        target = (self._workspace_root / relative_path).resolve()
        if not target.is_relative_to(self._workspace_root):
            raise ValueError("path escapes the configured workspace")
        if not target.exists():
            raise FileNotFoundError(f"File does not exist: {path_value}")
        if not target.is_file():
            raise IsADirectoryError(f"Path is not a file: {path_value}")

        return target.read_text(encoding="utf-8")
