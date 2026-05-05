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


class ReviewBatchUpdateRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)
    relative_paths: list[str] = Field(default_factory=list, min_length=1)
    decision: Decision


class UiStateUpdateRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)
    current_relative_path: str | None = None
    filter_mode: str = Field(
        default="unreviewed",
        pattern="^(all|reviewed|unreviewed|selected|wrong|completed)$",
    )


class SessionConfigUpdateRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)
    target_folder_path: str | None = None


class CsvLinkRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)
    csv_path: str = Field(..., min_length=1)


class PolygonPoint(BaseModel):
    x: float  # normalized [0, 1] relative to image natural width
    y: float  # normalized [0, 1] relative to image natural height


class NormalizedBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class PolygonAnnotation(BaseModel):
    id: str
    class_label: str
    points: list[PolygonPoint]
    value: float | None = None   # Real-world measurement (m or m²) from scale profile
    unit: str = ""               # "m" for crack length, "m²" for area classes
    source_object_id: int | None = None
    merge_action: str = Field(default="add", pattern="^(add|replace)$")


class ImageAnnotationUpdateRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)
    relative_path: str = Field(..., min_length=1)
    polygons: list[PolygonAnnotation]
    image_natural_width: int
    image_natural_height: int
    correction_mode: str = Field(default="patch", pattern="^(patch|redraw_all)$")
    prediction_actions: dict[str, str] = Field(default_factory=dict)
    prediction_class_overrides: dict[str, str] = Field(default_factory=dict)


class ScaleProfileLinkRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)
    scale_profile_path: str = Field(..., min_length=1)


class AreaCalculationRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)
    class_label: str
    points: list[PolygonPoint]
    image_natural_width: int
    image_natural_height: int


class Sam2SegmentRequest(BaseModel):
    """Point/box prompt request for interactive SAM segmentation.

    `points` are normalized 0..1 image coords; `labels` are 1 for
    foreground (include) / 0 for background (exclude), one per point.
    `box` is an optional normalized xyxy box prompt.
    """
    folder_path: str = Field(..., min_length=1)
    relative_path: str = Field(..., min_length=1)
    points: list[PolygonPoint] = Field(default_factory=list)
    labels: list[int] | None = None
    box: NormalizedBox | None = None
    image_natural_width: int
    image_natural_height: int
    correction_mode: str = Field(default="patch", pattern="^(patch|redraw_all)$")
    prediction_actions: dict[str, str] = Field(default_factory=dict)


class PredictionBox(BaseModel):
    object_id: int
    road_type: str = ""
    class_label: str
    original_class_label: str | None = None
    class_override: str | None = None
    value: float | None = None
    unit: str = ""
    x1: int = 0
    y1: int = 0
    x2: int = 0
    y2: int = 0
    confidence: float = 0.0
    action: str = Field(default="keep", pattern="^(keep|replace|delete)$")


class ImageRecord(BaseModel):
    relative_path: str
    filename: str
    image_url: str
    decision: Decision = Decision.UNREVIEWED
    reviewed: bool = False
    selected: bool = False
    reviewed_at: str | None = None
    annotation_count: int = 0
    polygons: list[PolygonAnnotation] = Field(default_factory=list)
    prediction_boxes: list[PredictionBox] = Field(default_factory=list)
    image_natural_width: int | None = None
    image_natural_height: int | None = None
    correction_mode: str = Field(default="patch", pattern="^(patch|redraw_all)$")


class SessionSummary(BaseModel):
    total_count: int
    reviewed_count: int
    selected_count: int
    correct_count: int
    annotated_count: int
    percent_reviewed: float


class UiState(BaseModel):
    current_relative_path: str | None = None
    filter_mode: str = "all"


class SessionPayload(BaseModel):
    folder_path: str
    session_key: str
    target_folder_path: str | None = None
    csv_path: str | None = None
    scale_profile_path: str | None = None
    images: list[ImageRecord]
    summary: SessionSummary
    ui_state: UiState


def to_payload_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")
