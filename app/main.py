from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import tasks_router
from app.bootstrap import build_application_components
from app.core.task_manager import TaskManager
from app.core.task_service import TaskService
from app.storage.database import Database
from app.storage.repository import TaskRepository


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
        components = build_application_components()
        database = components.database
        repository = components.repository
        task_service = components.task_service
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
