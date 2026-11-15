from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class BaseTool(ABC):
    """所有 Agent 工具的基础接口。

    每个具体工具都需要实现：
    1. name：工具名称
    2. description：工具描述
    3. arguments_model：工具参数 Schema
    4. execute()：工具执行逻辑
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """返回模型的工具调用中使用的唯一名称。"""

    @property
    @abstractmethod
    def description(self) -> str:
        """返回供模型理解工具用途的描述。"""

    @property
    @abstractmethod
    def arguments_model(self) -> type[BaseModel]:
        """返回用于校验模型生成参数值的 Pydantic 模型。"""

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """使用已经校验的参数执行工具。"""
