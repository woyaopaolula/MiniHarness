import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

from app.api import tasks_router
from app.core.model import OllamaModelAdapter, OpenAICompatibleModelAdapter
from app.core.runtime import AgentRuntime
from app.core.task_manager import TaskManager
from app.core.task_service import TaskService
from app.storage.database import Database
from app.storage.repository import TaskRepository
from app.tools.file_tools import ReadFileTool, SearchFilesTool, WriteFileTool
from app.tools.registry import ToolRegistry
from app.tools.test_tools import RunTestsTool
from app.tools.executor import ToolExecutor


def create_app(
    *,
    task_service: TaskService | None = None,
    repository: TaskRepository | None = None,
    database: Database | None = None,
    max_workers: int = 2,
) -> FastAPI:
    owns_database = False
    if task_service is None or repository is None:
        if task_service is not None or repository is not None:
            raise ValueError("task_service and repository must be provided together")
        database, repository, task_service = _build_default_components()
        owns_database = True
    elif database is None:
        raise ValueError("database is required with injected application components")

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        manager = TaskManager(task_service, max_workers=max_workers)
        application.state.task_service = task_service
        application.state.task_repository = repository
        application.state.task_manager = manager
        application.state.database = database
        try:
            yield
        finally:
            manager.shutdown()
            if owns_database:
                database.dispose()

    application = FastAPI(
        title="MiniHarness",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(tasks_router)

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        database.ping()
        return {"status": "ok", "database": "mysql"}

    return application


def _build_default_components() -> tuple[
    Database,
    TaskRepository,
    TaskService,
]:
    workspace = Path(
        os.getenv("MINIHARNESS_WORKSPACE_ROOT", str(PROJECT_ROOT))
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
    provider = os.getenv("MINIHARNESS_MODEL_PROVIDER", "openai").strip().lower()
    if provider == "ollama":
        model = OllamaModelAdapter(
            os.getenv(
                "MINIHARNESS_OLLAMA_MODEL",
                "qwen2.5-coder:3b",
            ),
            base_url=os.getenv(
                "MINIHARNESS_OLLAMA_BASE_URL",
                "http://127.0.0.1:11434/v1",
            ),
        )
    else:
        model_name = os.getenv("MINIHARNESS_LLM_MODEL", "").strip()
        if not model_name:
            raise RuntimeError(
                "MINIHARNESS_LLM_MODEL must be configured for the openai provider"
            )
        model = OpenAICompatibleModelAdapter(
            model_name,
            api_key=os.getenv("MINIHARNESS_LLM_API_KEY"),
            base_url=os.getenv("MINIHARNESS_LLM_BASE_URL"),
        )
    runtime = AgentRuntime(model, registry, ToolExecutor(registry))
    return database, repository, TaskService(repository, runtime, workspace)
