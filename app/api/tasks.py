from fastapi import APIRouter, HTTPException, Request, status

from app.api.schemas import CancelTaskResponse, CreateTaskRequest
from app.core.task_manager import TaskManager
from app.core.task_service import TaskService
from app.storage.models import TaskStatus
from app.storage.repository import TaskNotFoundError, TaskRepository
from app.storage.schemas import StoredTask, StoredTaskEvent, StoredToolCall

router = APIRouter(prefix="/tasks", tags=["tasks"])

_TERMINAL_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.INTERRUPTED,
}


@router.post("", response_model=StoredTask, status_code=status.HTTP_202_ACCEPTED)
def create_task(request: Request, payload: CreateTaskRequest) -> StoredTask:
    service: TaskService = request.app.state.task_service
    manager: TaskManager = request.app.state.task_manager

    task = service.create_task(payload.prompt)
    manager.submit(task.id)
    return task


@router.get("/{task_id}", response_model=StoredTask)
def get_task(request: Request, task_id: str) -> StoredTask:
    return _get_task(request.app.state.task_repository, task_id)


@router.get("/{task_id}/events", response_model=list[StoredTaskEvent])
def get_task_events(request: Request, task_id: str) -> list[StoredTaskEvent]:
    repository: TaskRepository = request.app.state.task_repository
    _get_task(repository, task_id)
    return repository.list_events(task_id)


@router.get("/{task_id}/tool-calls", response_model=list[StoredToolCall])
def get_task_tool_calls(request: Request, task_id: str) -> list[StoredToolCall]:
    repository: TaskRepository = request.app.state.task_repository
    _get_task(repository, task_id)
    return repository.list_tool_calls(task_id)


@router.post(
    "/{task_id}/cancel",
    response_model=CancelTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def cancel_task(request: Request, task_id: str) -> CancelTaskResponse:
    repository: TaskRepository = request.app.state.task_repository
    manager: TaskManager = request.app.state.task_manager
    task = _get_task(repository, task_id)

    if TaskStatus(task.status) in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is already terminal: {task.status}",
        )
    if not manager.cancel(task_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task is not running in this service process",
        )

    return CancelTaskResponse(
        task_id=task_id,
        cancellation_requested=True,
        message=(
            "Cancellation requested. The runtime will stop at its next "
            "cooperative checkpoint."
        ),
    )


def _get_task(repository: TaskRepository, task_id: str) -> StoredTask:
    try:
        return repository.get_task(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
