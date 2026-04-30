"""Pydantic request/response schemas for task and user endpoints."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .models_db import TaskEventType, TaskStatus, UserRole


# --- Users ---

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: UserRole
    is_active: bool = True


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6)
    display_name: str = Field(default="", max_length=128)
    role: UserRole


class UserPatch(BaseModel):
    """L1-only partial update of a user (role, display_name, active flag)."""
    display_name: str | None = Field(default=None, max_length=128)
    role: UserRole | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(..., min_length=6)


class MeOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: UserRole


# --- Tasks ---

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    folder_path: str | None = None
    csv_path: str | None = None
    scale_profile_path: str | None = None
    target_folder_path: str | None = None
    assigned_to: int | None = None
    due_date: date | None = None


class TaskUpdate(BaseModel):
    """Partial update — only L1, only when status allows edits (draft / assigned / returned)."""
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    folder_path: str | None = None
    csv_path: str | None = None
    scale_profile_path: str | None = None
    target_folder_path: str | None = None
    assigned_to: int | None = None
    due_date: date | None = None


class AssignRequest(BaseModel):
    assigned_to: int  # user id


class CommentRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class ReturnRequest(BaseModel):
    """L1 returning a submitted task to L2."""
    message: str = Field(..., min_length=1, max_length=4000)


class TaskEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    event_type: TaskEventType
    message: str
    actor_id: int
    actor_username: str | None = None
    created_at: datetime


class TaskOut(BaseModel):
    """Detail/list payload — flattened, includes joined assignee + creator usernames."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str

    folder_path: str | None
    csv_path: str | None
    scale_profile_path: str | None
    target_folder_path: str | None

    created_by: int
    creator_username: str | None = None
    assigned_to: int | None
    assignee_username: str | None = None

    status: TaskStatus
    due_date: date | None
    created_at: datetime
    updated_at: datetime

    total_images: int
    reviewed_count: int
    correct_count: int
    wrong_count: int
    annotated_count: int


class TaskListItem(TaskOut):
    """Same as TaskOut for now — kept distinct so we can trim later if needed."""
    pass
