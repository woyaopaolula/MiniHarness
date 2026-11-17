import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.core.model import (
    ModelAdapter,
    OllamaModelAdapter,
    OpenAICompatibleModelAdapter,
)
from app.core.runtime import AgentRuntime
from app.core.task_service import TaskService
from app.storage.database import Database
from app.storage.repository import TaskRepository
from app.tools.executor import ToolExecutor
from app.tools.file_tools import ReadFileTool, SearchFilesTool, WriteFileTool
from app.tools.registry import ToolRegistry
from app.tools.test_tools import RunTestsTool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class ApplicationComponents:
    database: Database
    repository: TaskRepository
    task_service: TaskService
    model: ModelAdapter
    workspace: Path

    def close(self) -> None:
        self.database.dispose()


def build_application_components(
    *,
    workspace_root: str | Path | None = None,
) -> ApplicationComponents:
    workspace = Path(
        workspace_root
        or os.getenv("MINIHARNESS_WORKSPACE_ROOT", str(PROJECT_ROOT))
    ).resolve()
    if not workspace.is_dir():
        raise RuntimeError(f"Workspace root does not exist: {workspace}")

    database = Database()
    database.create_schema()
    repository = TaskRepository(database)
    registry = ToolRegistry()
    registry.register(ReadFileTool(workspace))
    registry.register(SearchFilesTool(workspace))
    registry.register(WriteFileTool(workspace))
    registry.register(RunTestsTool(workspace))
    model = build_model_adapter()
    runtime = AgentRuntime(model, registry, ToolExecutor(registry))
    service = TaskService(repository, runtime, workspace)
    return ApplicationComponents(
        database=database,
        repository=repository,
        task_service=service,
        model=model,
        workspace=workspace,
    )


def build_model_adapter() -> ModelAdapter:
    provider = os.getenv("MINIHARNESS_MODEL_PROVIDER", "openai").strip().lower()
    if provider == "ollama":
        return OllamaModelAdapter(
            os.getenv("MINIHARNESS_OLLAMA_MODEL", "qwen2.5-coder:3b"),
            base_url=os.getenv(
                "MINIHARNESS_OLLAMA_BASE_URL",
                "http://127.0.0.1:11434/v1",
            ),
        )
    if provider != "openai":
        raise RuntimeError(f"Unsupported model provider: {provider}")

    model_name = os.getenv("MINIHARNESS_LLM_MODEL", "").strip()
    if not model_name:
        raise RuntimeError(
            "MINIHARNESS_LLM_MODEL must be configured for the openai provider"
        )
    return OpenAICompatibleModelAdapter(
        model_name,
        api_key=os.getenv("MINIHARNESS_LLM_API_KEY"),
        base_url=os.getenv("MINIHARNESS_LLM_BASE_URL"),
    )
