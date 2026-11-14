from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """所有 Agent 工具的基础接口。

    每个具体工具都需要实现：
    1. name：工具名称
    2. description：工具描述
    3. execute()：工具执行逻辑
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """返回模型的工具调用中使用的唯一名称。"""

    @property
    @abstractmethod
    def description(self) -> str:
        """返回供模型理解工具用途的描述。"""

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """执行工具。

        具体参数由各工具定义。参数 Schema 和统一异常转换将在
        ToolExecutor 阶段实现。
        """
