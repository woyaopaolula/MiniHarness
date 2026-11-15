from pathlib import Path


class Workspace:
    """为所有文件工具提供统一的工作区路径边界。"""

    def __init__(self, root: str | Path) -> None:
        workspace_root = Path(root).expanduser()
        if not workspace_root.exists():
            raise FileNotFoundError(
                f"Workspace does not exist: {workspace_root}"
            )
        if not workspace_root.is_dir():
            raise NotADirectoryError(
                f"Workspace is not a directory: {workspace_root}"
            )
        self._root = workspace_root.resolve()

    @property
    def root(self) -> Path:
        return self._root

    def resolve_path(self, path_value: str, *, allow_root: bool = False) -> Path:
        """把相对路径解析为工作区内的绝对路径。"""

        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError("path must be a non-empty string")

        relative_path = Path(path_value)
        if relative_path.is_absolute() or relative_path.drive or relative_path.root:
            raise ValueError("path must be relative to the workspace")

        target = (self._root / relative_path).resolve()
        if not target.is_relative_to(self._root):
            raise ValueError("path escapes the configured workspace")
        if target == self._root and not allow_root:
            raise ValueError("path must point inside the workspace")
        return target

    def relative_path(self, target: Path) -> str:
        """返回稳定的 POSIX 风格工作区相对路径。"""

        return target.relative_to(self._root).as_posix()
