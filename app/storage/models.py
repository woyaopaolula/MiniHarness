from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


class Base(DeclarativeBase):
    pass


class TaskRow(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    prompt: Mapped[str] = mapped_column(Text)
    workspace: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    iterations: Mapped[int] = mapped_column(Integer, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    events: Mapped[list["TaskEventRow"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    tool_calls: Mapped[list["ToolCallRow"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )


class TaskEventRow(Base):
    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
    )
    iteration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    task: Mapped[TaskRow] = relationship(back_populates="events")


class ToolCallRow(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        UniqueConstraint("task_id", "call_id", name="uq_tool_calls_task_call"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
    )
    call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_time: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    task: Mapped[TaskRow] = relationship(back_populates="tool_calls")
