import re
from app.tools.base import BaseTool

_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


class ToolRegistry:
    """Agent 工具注册表。

    负责：
    1. 注册工具
    2. 根据名称查找工具
    3. 获取当前所有工具
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册一个工具。"""

        if not isinstance(tool, BaseTool):
            raise TypeError("Registered tool must inherit from BaseTool")

        name = tool.name
        if not isinstance(name, str) or not name:
            raise ValueError("Tool name must be a non-empty string")
        if _TOOL_NAME_PATTERN.fullmatch(name) is None:
            raise ValueError(
                "Tool name must start with a letter and contain only "
                "letters, numbers, underscores, or hyphens (max 64 characters)"
            )

        description = tool.description
        if not isinstance(description, str) or not description.strip():
            raise ValueError("Tool description must be a non-empty string")

        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")

        self._tools[name] = tool

    def get(self, name: str) -> BaseTool:
        """根据名称获取工具。"""

        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")

        return self._tools[name]

    def list_tools(self) -> list[dict[str, str]]:
        """返回所有已注册工具的基本信息。"""

        return [
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in self._tools.values()
        ]

    def __len__(self) -> int:
        return len(self._tools)
