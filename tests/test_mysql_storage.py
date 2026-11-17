from datetime import timedelta

import pytest
from sqlalchemy import inspect, select, update

from app.storage.database import Database
from app.storage.models import TaskRow, TaskStatus, utc_now
from app.storage.repository import (
    InvalidTaskTransition,
    TaskNotFoundError,
    TaskRepository,
)


def test_mysql_connection_and_schema(mysql_database: Database) -> None:
    mysql_database.ping()
    tables = set(inspect(mysql_database.engine).get_table_names())

    assert {"tasks", "task_events", "tool_calls"} <= tables


def test_task_lifecycle_and_atomic_state_transitions(
    empty_mysql_database: Database,
) -> None:
    repository = TaskRepository(empty_mysql_database)
    task = repository.create_task("Fix a bug.", workspace="D:/workspace")

    assert task.status == TaskStatus.PENDING
    assert task.started_at is None

    with pytest.raises(InvalidTaskTransition):
        repository.transition_task(task.id, TaskStatus.COMPLETED)

    started = repository.transition_task(task.id, TaskStatus.RUNNING)
    completed = repository.transition_task(
        task.id,
        TaskStatus.COMPLETED,
        answer="Fixed.",
        stop_reason="final_answer",
        iterations=2,
        tool_call_count=1,
        total_tokens=30,
        elapsed_seconds=0.5,
    )

    assert started.status == TaskStatus.RUNNING
    assert started.started_at is not None
    assert completed.status == TaskStatus.COMPLETED
    assert completed.answer == "Fixed."
    assert completed.finished_at is not None

    with pytest.raises(InvalidTaskTransition):
        repository.transition_task(task.id, TaskStatus.RUNNING)


def test_events_are_ordered_and_update_heartbeat(
    empty_mysql_database: Database,
) -> None:
    repository = TaskRepository(empty_mysql_database)
    task = repository.create_task("Run events.", workspace="D:/workspace")
    repository.transition_task(task.id, TaskStatus.RUNNING)
    before = repository.get_task(task.id).updated_at

    first = repository.append_event(
        task.id,
        "model_response",
        {"content": "Working"},
        iteration=1,
    )
    second = repository.append_event(
        task.id,
        "run_finished",
        {"status": "completed"},
        iteration=1,
    )
    events = repository.list_events(task.id)
    after = repository.get_task(task.id).updated_at

    assert first.id < second.id
    assert [event.event_type for event in events] == [
        "model_response",
        "run_finished",
    ]
    assert after >= before


def test_tool_call_records_success_and_failure(
    empty_mysql_database: Database,
) -> None:
    repository = TaskRepository(empty_mysql_database)
    task = repository.create_task("Call tools.", workspace="D:/workspace")
    repository.transition_task(task.id, TaskStatus.RUNNING)

    repository.record_tool_call(
        task.id,
        call_id="call-1",
        iteration=1,
        tool_name="read_file",
        arguments={"path": "app.py"},
        result={
            "success": True,
            "tool_name": "read_file",
            "data": "value = 1",
            "error": None,
            "error_type": None,
            "execution_time": 0.01,
        },
    )
    repository.record_tool_call(
        task.id,
        call_id="call-2",
        iteration=2,
        tool_name="run_tests",
        arguments={"test_path": "tests"},
        result={
            "success": False,
            "tool_name": "run_tests",
            "data": None,
            "error": "process timed out",
            "error_type": "execution_error",
            "execution_time": 3.0,
        },
    )

    calls = repository.list_tool_calls(task.id)

    assert [call.success for call in calls] == [True, False]
    assert calls[1].error == "process timed out"


def test_stale_running_task_is_marked_interrupted(
    empty_mysql_database: Database,
) -> None:
    repository = TaskRepository(empty_mysql_database)
    task = repository.create_task("Will be interrupted.", workspace="D:/workspace")
    repository.transition_task(task.id, TaskStatus.RUNNING)
    with empty_mysql_database.session() as session, session.begin():
        session.execute(
            update(TaskRow)
            .where(TaskRow.id == task.id)
            .values(updated_at=utc_now() - timedelta(minutes=10))
        )

    recovered = repository.recover_stale_running_tasks(utc_now())
    stored = repository.get_task(task.id)

    assert recovered == 1
    assert stored.status == TaskStatus.INTERRUPTED
    assert stored.stop_reason == "stale_running_task"
    assert stored.finished_at is not None


def test_repository_rejects_unknown_task(empty_mysql_database: Database) -> None:
    repository = TaskRepository(empty_mysql_database)

    with pytest.raises(TaskNotFoundError):
        repository.get_task("missing")
