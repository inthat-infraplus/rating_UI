"""SQLAlchemy ORM models: User, Task, TaskEvent."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class UserRole(str, Enum):
    L1 = "L1"  # Assigner / Reviewer
    L2 = "L2"  # Annotator


class TaskStatus(str, Enum):
    DRAFT       = "draft"        # L1 building, not yet assigned
    ASSIGNED    = "assigned"     # assigned to L2, not started
    IN_PROGRESS = "in_progress"  # L2 has opened/edited
    SUBMITTED   = "submitted"    # L2 submitted for QC
    IN_QC       = "in_qc"        # L1 actively reviewing
    RETURNED    = "returned"     # L1 sent back to L2 with comment
    APPROVED    = "approved"     # L1 accepted; ready to export
    EXPORTED    = "exported"     # L1 has exported


class TaskEventType(str, Enum):
    CREATED      = "created"
    ASSIGNED     = "assigned"
    STARTED      = "started"
    SUBMITTED    = "submitted"
    QC_STARTED   = "qc_started"
    RETURNED     = "returned"
    APPROVED     = "approved"
    EXPORTED     = "exported"
    COMMENT      = "comment"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole, name="user_role"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} username={self.username!r} role={self.role.value}>"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Paths — owned by L1; L2 may not edit
    folder_path: Mapped[str | None]         = mapped_column(String(1024), nullable=True)
    csv_path: Mapped[str | None]            = mapped_column(String(1024), nullable=True)
    scale_profile_path: Mapped[str | None]  = mapped_column(String(1024), nullable=True)
    target_folder_path: Mapped[str | None]  = mapped_column(String(1024), nullable=True)

    created_by: Mapped[int]         = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status"),
        nullable=False, default=TaskStatus.DRAFT, index=True,
    )

    due_date: Mapped[date | None]    = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime]     = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime]     = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow,
    )

    # Cached progress counters — updated whenever a review is saved
    total_images: Mapped[int]     = mapped_column(Integer, nullable=False, default=0)
    reviewed_count: Mapped[int]   = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int]    = mapped_column(Integer, nullable=False, default=0)
    wrong_count: Mapped[int]      = mapped_column(Integer, nullable=False, default=0)
    annotated_count: Mapped[int]  = mapped_column(Integer, nullable=False, default=0)

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    creator: Mapped["User"]         = relationship("User", foreign_keys=[created_by])
    assignee: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_to])
    events: Mapped[list["TaskEvent"]] = relationship(
        "TaskEvent", back_populates="task", order_by="TaskEvent.created_at",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Task id={self.id} title={self.title!r} status={self.status.value}>"


class TaskEvent(Base):
    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    event_type: Mapped[TaskEventType] = mapped_column(
        SAEnum(TaskEventType, name="task_event_type"), nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    read_by_assigner: Mapped[bool]  = mapped_column(Boolean, nullable=False, default=False)
    read_by_annotator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    task: Mapped["Task"] = relationship("Task", back_populates="events")
    actor: Mapped["User"] = relationship("User", foreign_keys=[actor_id])
