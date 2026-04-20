from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Decision(str, Enum):
    UNREVIEWED = "unreviewed"
    CORRECT = "correct"
    WRONG = "wrong"


class FolderRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)


class ReviewUpdateRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)
    relative_path: str = Field(..., min_length=1)
    decision: Decision


class UiStateUpdateRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)
    current_relative_path: str | None = None
    filter_mode: str = Field(default="all", pattern="^(all|reviewed|unreviewed|selected)$")


class SessionConfigUpdateRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)
    target_folder_path: str | None = None


class ImageRecord(BaseModel):
    relative_path: str
    filename: str
    image_url: str
    decision: Decision = Decision.UNREVIEWED
    reviewed: bool = False
    selected: bool = False
    reviewed_at: str | None = None


class SessionSummary(BaseModel):
    total_count: int
    reviewed_count: int
    selected_count: int
    correct_count: int
    percent_reviewed: float


class UiState(BaseModel):
    current_relative_path: str | None = None
    filter_mode: str = "all"


class SessionPayload(BaseModel):
    folder_path: str
    session_key: str
    target_folder_path: str | None = None
    images: list[ImageRecord]
    summary: SessionSummary
    ui_state: UiState


def to_payload_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")
