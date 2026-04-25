"""Task service: CRUD, state transitions, permission checks.

This is the ONLY place where task state machine rules and role checks live.
Endpoint handlers translate HTTP into service calls and let the service raise.

State machine (see .claude/skills/rating-ai/SKILL.md §4):

    draft ──(L1 set paths + assign)──▶ assigned
                                          │
                             (L2 opens)   ▼
                                     in_progress
                                          │
                          (L2 Submit for QC)
                                          ▼
                                      submitted ──(L1 opens QC)──▶ in_qc
                                                                     │
                                            (Return w/ comment)      │  (Approve)
                                                ▼                    ▼
                                             returned            approved
                                                │                    │
                                         (L2 resumes)          (L1 Export)
                                                ▼                    ▼
                                            in_progress          exported
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models_db import (
    Task,
    TaskEvent,
    TaskEventType,
    TaskStatus,
    User,
    UserRole,
)


# --- exceptions ---

class TaskServiceError(Exception):
    """Base error. HTTP layer maps to 400 by default."""

    status_code: int = 400


class NotFound(TaskServiceError):
    status_code = 404


class Forbidden(TaskServiceError):
    status_code = 403


class InvalidTransition(TaskServiceError):
    status_code = 409


# --- access / permission helpers ---

def _can_view(task: Task, user: User) -> bool:
    if user.role == UserRole.L1:
        return True
    return task.assigned_to == user.id


def _require_view(task: Task, user: User) -> None:
    if not _can_view(task, user):
        raise Forbidden("You do not have access to this task.")


def _require_l1(user: User) -> None:
    if user.role != UserRole.L1:
        raise Forbidden("This action is restricted to Assigner/Reviewer (L1).")


def _require_assignee(task: Task, user: User) -> None:
    if task.assigned_to != user.id:
        raise Forbidden("This action is restricted to the task's assignee.")


def get_task(db: Session, task_id: int, *, include_deleted: bool = False) -> Task:
    task = db.get(Task, task_id)
    if task is None or (task.deleted_at is not None and not include_deleted):
        raise NotFound("Task not found.")
    return task


# --- listing ---

def list_tasks_for_user(db: Session, user: User) -> list[Task]:
    """L1 sees everything (non-deleted). L2 sees only tasks assigned to them
    that are still in their workflow (assigned / in_progress / returned)."""
    q = select(Task).where(Task.deleted_at.is_(None))
    if user.role == UserRole.L2:
        q = q.where(
            Task.assigned_to == user.id,
            Task.status.in_([
                TaskStatus.ASSIGNED,
                TaskStatus.IN_PROGRESS,
                TaskStatus.RETURNED,
            ]),
        )
    q = q.order_by(Task.updated_at.desc())
    return list(db.scalars(q).all())


# --- create / update ---

def create_task(db: Session, actor: User, payload) -> Task:
    _require_l1(actor)

    if payload.assigned_to is not None:
        assignee = db.get(User, payload.assigned_to)
        if assignee is None or assignee.role != UserRole.L2 or not assignee.is_active:
            raise TaskServiceError("Assignee must be an active L2 user.")

    task = Task(
        title=payload.title,
        description=payload.description or "",
        folder_path=payload.folder_path,
        csv_path=payload.csv_path,
        scale_profile_path=payload.scale_profile_path,
        target_folder_path=payload.target_folder_path,
        assigned_to=payload.assigned_to,
        due_date=payload.due_date,
        created_by=actor.id,
        status=(
            TaskStatus.ASSIGNED if payload.assigned_to is not None else TaskStatus.DRAFT
        ),
    )
    db.add(task)
    db.flush()  # assign id

    db.add(TaskEvent(
        task_id=task.id, actor_id=actor.id,
        event_type=TaskEventType.CREATED, message=f"Created task {task.title!r}",
    ))
    if payload.assigned_to is not None:
        db.add(TaskEvent(
            task_id=task.id, actor_id=actor.id,
            event_type=TaskEventType.ASSIGNED,
            message=f"Assigned to user #{payload.assigned_to}",
        ))
    return task


# Status set in which L1 may still edit fields/paths.
_EDITABLE_STATUSES = {TaskStatus.DRAFT, TaskStatus.ASSIGNED, TaskStatus.RETURNED}


def update_task(db: Session, actor: User, task_id: int, payload) -> Task:
    _require_l1(actor)
    task = get_task(db, task_id)
    if task.status not in _EDITABLE_STATUSES:
        raise InvalidTransition(
            f"Task cannot be edited in status {task.status.value}."
        )

    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(task, key, value)
    return task


def assign_task(db: Session, actor: User, task_id: int, assigned_to: int) -> Task:
    _require_l1(actor)
    task = get_task(db, task_id)
    if task.status not in {TaskStatus.DRAFT, TaskStatus.ASSIGNED, TaskStatus.RETURNED}:
        raise InvalidTransition(
            f"Cannot reassign in status {task.status.value}."
        )

    assignee = db.get(User, assigned_to)
    if assignee is None or assignee.role != UserRole.L2 or not assignee.is_active:
        raise TaskServiceError("Assignee must be an active L2 user.")

    task.assigned_to = assigned_to
    if task.status == TaskStatus.DRAFT:
        task.status = TaskStatus.ASSIGNED

    db.add(TaskEvent(
        task_id=task.id, actor_id=actor.id,
        event_type=TaskEventType.ASSIGNED,
        message=f"Assigned to user #{assigned_to}",
    ))
    return task


def soft_delete_task(db: Session, actor: User, task_id: int) -> None:
    from datetime import datetime
    _require_l1(actor)
    task = get_task(db, task_id)
    task.deleted_at = datetime.utcnow()


# --- state transitions ---

def mark_started(db: Session, actor: User, task_id: int) -> Task:
    """Called the first time L2 opens an assigned task. Idempotent — only flips
    ASSIGNED → IN_PROGRESS. RETURNED tasks also flip back to IN_PROGRESS."""
    task = get_task(db, task_id)
    _require_view(task, actor)
    if actor.role != UserRole.L2:
        return task  # L1 viewing doesn't change state
    _require_assignee(task, actor)

    if task.status == TaskStatus.ASSIGNED:
        task.status = TaskStatus.IN_PROGRESS
        db.add(TaskEvent(
            task_id=task.id, actor_id=actor.id,
            event_type=TaskEventType.STARTED, message="Started",
        ))
    elif task.status == TaskStatus.RETURNED:
        task.status = TaskStatus.IN_PROGRESS
        db.add(TaskEvent(
            task_id=task.id, actor_id=actor.id,
            event_type=TaskEventType.STARTED, message="Resumed after return",
        ))
    return task


def submit_for_qc(db: Session, actor: User, task_id: int) -> Task:
    task = get_task(db, task_id)
    _require_view(task, actor)
    _require_assignee(task, actor)
    if actor.role != UserRole.L2:
        raise Forbidden("Only the assigned annotator (L2) can submit for QC.")
    if task.status not in {TaskStatus.IN_PROGRESS, TaskStatus.ASSIGNED, TaskStatus.RETURNED}:
        raise InvalidTransition(
            f"Cannot submit a task in status {task.status.value}."
        )
    task.status = TaskStatus.SUBMITTED
    db.add(TaskEvent(
        task_id=task.id, actor_id=actor.id,
        event_type=TaskEventType.SUBMITTED, message="Submitted for QC",
    ))
    return task


def open_qc(db: Session, actor: User, task_id: int) -> Task:
    """Optional: marks SUBMITTED → IN_QC when L1 opens the task. Idempotent."""
    _require_l1(actor)
    task = get_task(db, task_id)
    if task.status == TaskStatus.SUBMITTED:
        task.status = TaskStatus.IN_QC
        db.add(TaskEvent(
            task_id=task.id, actor_id=actor.id,
            event_type=TaskEventType.QC_STARTED, message="QC started",
        ))
    return task


def return_to_annotator(db: Session, actor: User, task_id: int, message: str) -> Task:
    _require_l1(actor)
    task = get_task(db, task_id)
    if task.status not in {TaskStatus.SUBMITTED, TaskStatus.IN_QC}:
        raise InvalidTransition(
            f"Cannot return a task in status {task.status.value}."
        )
    if not message.strip():
        raise TaskServiceError("Return requires a comment explaining what to fix.")
    task.status = TaskStatus.RETURNED
    db.add(TaskEvent(
        task_id=task.id, actor_id=actor.id,
        event_type=TaskEventType.RETURNED, message=message,
    ))
    return task


def approve_task(db: Session, actor: User, task_id: int) -> Task:
    _require_l1(actor)
    task = get_task(db, task_id)
    if task.status not in {TaskStatus.SUBMITTED, TaskStatus.IN_QC}:
        raise InvalidTransition(
            f"Cannot approve a task in status {task.status.value}."
        )
    task.status = TaskStatus.APPROVED
    db.add(TaskEvent(
        task_id=task.id, actor_id=actor.id,
        event_type=TaskEventType.APPROVED, message="Approved",
    ))
    return task


def mark_exported(db: Session, actor: User, task_id: int) -> Task:
    """Called by export endpoints AFTER a successful export."""
    _require_l1(actor)
    task = get_task(db, task_id)
    if task.status not in {TaskStatus.APPROVED, TaskStatus.EXPORTED}:
        raise InvalidTransition(
            f"Cannot export a task in status {task.status.value}."
        )
    task.status = TaskStatus.EXPORTED
    db.add(TaskEvent(
        task_id=task.id, actor_id=actor.id,
        event_type=TaskEventType.EXPORTED, message="Exported",
    ))
    return task


# --- comments ---

def add_comment(db: Session, actor: User, task_id: int, message: str) -> TaskEvent:
    task = get_task(db, task_id)
    _require_view(task, actor)
    if not message.strip():
        raise TaskServiceError("Comment cannot be empty.")
    event = TaskEvent(
        task_id=task.id, actor_id=actor.id,
        event_type=TaskEventType.COMMENT, message=message,
    )
    db.add(event)
    return event


def list_events(db: Session, actor: User, task_id: int) -> list[TaskEvent]:
    task = get_task(db, task_id)
    _require_view(task, actor)
    return list(task.events)


# --- progress counter helper (called from review_store later) ---

def update_progress_counters(
    db: Session,
    task_id: int,
    *,
    total: int,
    reviewed: int,
    correct: int,
    wrong: int,
    annotated: int,
) -> None:
    task = db.get(Task, task_id)
    if task is None:
        return
    task.total_images = total
    task.reviewed_count = reviewed
    task.correct_count = correct
    task.wrong_count = wrong
    task.annotated_count = annotated


# --- serialization ---

def task_to_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "folder_path": task.folder_path,
        "csv_path": task.csv_path,
        "scale_profile_path": task.scale_profile_path,
        "target_folder_path": task.target_folder_path,
        "created_by": task.created_by,
        "creator_username": task.creator.username if task.creator else None,
        "assigned_to": task.assigned_to,
        "assignee_username": task.assignee.username if task.assignee else None,
        "status": task.status.value,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "total_images": task.total_images,
        "reviewed_count": task.reviewed_count,
        "correct_count": task.correct_count,
        "wrong_count": task.wrong_count,
        "annotated_count": task.annotated_count,
    }


def event_to_dict(event: TaskEvent) -> dict:
    return {
        "id": event.id,
        "task_id": event.task_id,
        "event_type": event.event_type.value,
        "message": event.message,
        "actor_id": event.actor_id,
        "actor_username": event.actor.username if event.actor else None,
        "created_at": event.created_at.isoformat(),
    }
