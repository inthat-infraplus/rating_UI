from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

from .models import (
    Decision,
    ImageRecord,
    PolygonAnnotation,
    PolygonPoint,
    PredictionBox,
    SessionPayload,
    SessionSummary,
    UiState,
)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tif", ".tiff"}
DEFAULT_UI_STATE = UiState()
DEFAULT_SCALE_PROFILE_PATH = Path(__file__).resolve().parent.parent / "scale_profile" / "scale_profile.csv"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _fix_path_input(raw: str) -> str:
    """
    Normalise a user-supplied path string before handing it to pathlib.

    Handles:
    • surrounding whitespace / quotes  (copy-paste artefacts)
    • missing colon after drive letter: "C\\foo" → "C:\\foo"
    • forward-slash paths on Windows:  "C:/foo"  → works fine with pathlib
    """
    import re as _re
    p = raw.strip().strip("\"'")
    # "C\path" → "C:\path"  (colon was omitted after the drive letter)
    p = _re.sub(r"^([A-Za-z])\\(?!\\)", r"\1:\\", p)
    return p


def normalize_folder(folder_path: str) -> Path:
    folder = Path(_fix_path_input(folder_path)).expanduser().resolve()
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Path is not a folder: {folder}")
    return folder


def relative_to_folder(folder: Path, file_path: Path) -> str:
    return file_path.relative_to(folder).as_posix()


def validate_relative_path(folder: Path, relative_path: str) -> Path:
    candidate = (folder / relative_path).resolve()
    common_path = os.path.commonpath([str(folder), str(candidate)])
    if common_path != str(folder):
        raise ValueError("Image path escapes selected folder.")
    if candidate.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("Unsupported image format.")
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"Image not found: {candidate}")
    return candidate


def state_root() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".rating-ui"))
    return root / "RatingUI" / "states"


def import_root() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".rating-ui"))
    return root / "RatingUI" / "imports"


def session_key_for(folder: Path) -> str:
    digest = hashlib.sha256(str(folder).encode("utf-8")).hexdigest()
    return digest[:16]


def state_path_for(folder: Path) -> Path:
    return state_root() / f"{session_key_for(folder)}.json"


def _safe_int(value: Any) -> int:
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(str(value))
    except (ValueError, TypeError):
        return 0.0


def _normalize_csv_header(value: Any) -> str:
    text = str(value or "").strip().lstrip("\ufeff").lower()
    return "".join(ch for ch in text if ch.isalnum())


def _resolve_csv_header_map(fieldnames: list[str] | None) -> dict[str, str | None]:
    normalized_to_actual: dict[str, str] = {}
    for field in fieldnames or []:
        key = _normalize_csv_header(field)
        if key and key not in normalized_to_actual:
            normalized_to_actual[key] = field

    def pick(*candidates: str) -> str | None:
        for candidate in candidates:
            actual = normalized_to_actual.get(_normalize_csv_header(candidate))
            if actual:
                return actual
        return None

    return {
        "image_filename": pick("Image Filename", "ImageFilename", "Filename"),
        "road_type": pick("Road Type", "RoadType", "road_type"),
        "object_id": pick("Object ID", "ObjectID"),
        "class_label": pick("Class", "Label"),
        "value": pick("Value"),
        "unit": pick("Unit"),
        "x1": pick("X1 (px)", "X1", "X1_px"),
        "y1": pick("Y1 (px)", "Y1", "Y1_px"),
        "x2": pick("X2 (px)", "X2", "X2_px"),
        "y2": pick("Y2 (px)", "Y2", "Y2_px"),
        "confidence": pick("Confidence", "Score"),
    }


def _row_value(row: dict[str, Any], header_map: dict[str, str | None], key: str) -> Any:
    actual = header_map.get(key)
    if not actual:
        return ""
    return row.get(actual, "")


def _normalize_correction_mode(value: Any) -> str:
    return "redraw_all" if str(value or "").strip().lower() == "redraw_all" else "patch"


def _normalize_prediction_action(value: Any) -> str:
    action = str(value or "").strip().lower()
    if action in {"replace", "delete"}:
        return action
    return "keep"


def _normalize_filter_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    if mode == "selected":
        return "wrong"
    if mode == "reviewed":
        return "completed"
    if mode in {"all", "unreviewed", "wrong", "completed"}:
        return mode
    return "unreviewed"


ScaleProfile = dict[int, tuple[float, float]]  # {row_index: (x_scale, y_scale)}


def load_scale_profile(scale_profile_path: str) -> ScaleProfile:
    """Parse scale_profile.csv → {row_index: (x_scale_m_per_px, y_scale_m_per_px)} for in_roi==1 rows."""
    path = Path(_fix_path_input(scale_profile_path)).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Scale profile not found: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    profile: ScaleProfile = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                in_roi = int(row.get("in_roi", 0))
            except (ValueError, TypeError):
                in_roi = 0
            if in_roi != 1:
                continue
            try:
                row_idx = int(row["row_index"])
                x_scale = float(row["x_scale_m_per_px"])
                y_scale = float(row["y_scale_m_per_px"])
                if x_scale > 0 and y_scale > 0:
                    profile[row_idx] = (x_scale, y_scale)
            except (KeyError, ValueError, TypeError):
                continue
    return profile


def default_scale_profile_path() -> Path | None:
    path = DEFAULT_SCALE_PROFILE_PATH.resolve()
    if not path.exists() or not path.is_file():
        return None
    return path


def _calculate_polygon_metrics(
    points: list[dict[str, Any]],
    nat_w: int,
    nat_h: int,
    class_label: str,
    scale_profile: ScaleProfile,
) -> tuple[float, str]:
    """
    Compute real-world measurement for a normalized polygon.

    For 'crack': perimeter length in metres (sum of edge segments scaled by midpoint row scale).
    For area classes: scanline integration of pixel rows × per-row x_scale × y_scale → m^2.
    Returns (value, unit).
    """
    if not points or not scale_profile:
        return 0.0, ""

    pixel_pts = [(p["x"] * nat_w, p["y"] * nat_h) for p in points]
    n = len(pixel_pts)

    if class_label.lower() == "crack":
        total = 0.0
        for i in range(n):
            x1, y1 = pixel_pts[i]
            x2, y2 = pixel_pts[(i + 1) % n]
            y_mid = max(0, min(int((y1 + y2) / 2), nat_h - 1))
            x_s, y_s = scale_profile.get(y_mid, (0.0, 0.0))
            total += math.sqrt(((x2 - x1) * x_s) ** 2 + ((y2 - y1) * y_s) ** 2)
        return round(total, 4), "m"
    else:
        # Scanline area integration
        ys = [p[1] for p in pixel_pts]
        y_min, y_max = int(math.floor(min(ys))), int(math.ceil(max(ys)))
        area = 0.0
        for y in range(y_min, y_max + 1):
            x_s, y_s = scale_profile.get(y, (0.0, 0.0))
            if not x_s:
                continue
            # Even-odd scanline fill intersections
            intersections: list[float] = []
            for i in range(n):
                x1, y1 = pixel_pts[i]
                x2, y2 = pixel_pts[(i + 1) % n]
                if y1 == y2:
                    continue
                if min(y1, y2) <= y < max(y1, y2):
                    t = (y - y1) / (y2 - y1)
                    intersections.append(x1 + t * (x2 - x1))
            intersections.sort()
            for k in range(0, len(intersections) - 1, 2):
                span_px = intersections[k + 1] - intersections[k]
                area += span_px * x_s * y_s
        return round(area, 4), "m^2"


class _ListWriter(list[str]):
    def write(self, value: str) -> int:
        self.append(value)
        return len(value)


def build_summary(images: list[ImageRecord]) -> SessionSummary:
    total_count = len(images)
    reviewed_count = sum(1 for item in images if item.reviewed)
    selected_count = sum(1 for item in images if item.selected)
    correct_count = sum(1 for item in images if item.decision == Decision.CORRECT)
    annotated_count = sum(1 for item in images if item.annotation_count > 0)
    percent_reviewed = round((reviewed_count / total_count) * 100, 1) if total_count else 0.0
    return SessionSummary(
        total_count=total_count,
        reviewed_count=reviewed_count,
        selected_count=selected_count,
        correct_count=correct_count,
        annotated_count=annotated_count,
        percent_reviewed=percent_reviewed,
    )


def build_csv(rows: list[dict[str, Any]]) -> str:
    header = [
        "index",
        "filename",
        "relative_path",
        "source_path",
        "target_filename",
        "target_relative_path",
        "target_source_path",
        "decision",
        "reviewed_at",
    ]
    output = _ListWriter()
    writer = csv.DictWriter(output, fieldnames=header)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return "".join(output)


def build_selected_filenames_txt(images: list[ImageRecord]) -> str:
    return "\n".join(item.filename for item in images) + "\n"


def sanitize_export_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    cleaned = cleaned.strip("._-")
    return cleaned or "rating_export"


def export_label_for_filename(filename: str) -> str | None:
    parts = Path(filename).stem.split("_")
    if len(parts) >= 2:
        return sanitize_export_name("_".join(parts[:2]))
    if parts:
        return sanitize_export_name(parts[0])
    return None


def infer_export_base_name(images: list[ImageRecord], session_key: str) -> str:
    labels = [label for item in images if (label := export_label_for_filename(item.filename))]
    unique_labels = set(labels)
    if len(unique_labels) == 1:
        return f"rating_{unique_labels.pop()}"

    first_tokens = {
        sanitize_export_name(Path(item.filename).stem.split("_")[0])
        for item in images
        if Path(item.filename).stem
    }
    if len(first_tokens) == 1:
        return f"rating_{first_tokens.pop()}"

    return f"rating_mixed_{session_key}"


def _new_state_payload(folder: Path, session_key: str) -> dict[str, Any]:
    timestamp = utc_now_iso()
    return {
        "folder_path": str(folder),
        "session_key": session_key,
        "created_at": timestamp,
        "updated_at": timestamp,
        "target_folder_path": None,
        "csv_path": None,
        "csv_rows": {},
        "images": {},
        "ui_state": DEFAULT_UI_STATE.model_dump(),
    }


# ── Annotation rendering helpers ──────────────────────────────────────────────

# YOLO segmentation class IDs (must match your model's class list)
YOLO_CLASS_ID: dict[str, int] = {
    "alligator crack": 0,
    "crack":           1,
    "patching":        2,
    "pothole":         3,
    "pavement":        4,
}

# RGBA fill/outline colours per class (matches JS CLASS_COLORS)
_CLASS_RGBA: dict[str, tuple[int, int, int]] = {
    "alligator crack": (230, 57,  70),
    "crack":           (244, 162, 97),
    "patching":        (42,  157, 143),
    "pothole":         (233, 196, 106),
    "pavement":        (69,  123, 157),
}
_FALLBACK_COLORS = [
    (6, 214, 160), (17, 138, 178), (255, 209, 102),
    (239, 71, 111), (168, 218, 220), (248, 150, 30),
]

CLASSES_TXT = "\n".join(
    f"{cid}: {name}"
    for name, cid in sorted(YOLO_CLASS_ID.items(), key=lambda x: x[1])
) + "\n"


def _class_color(class_label: str, fallback_index: int = 0) -> tuple[int, int, int]:
    return _CLASS_RGBA.get(class_label.lower(), _FALLBACK_COLORS[fallback_index % len(_FALLBACK_COLORS)])


def render_annotation_on_image(
    target_path: Path,
    polygons: list[dict[str, Any]],
) -> bytes:
    """
    Draw polygon annotations on top of the target image.
    Returns JPEG bytes of the annotated image.
    Coordinates in `polygons` are normalized [0, 1]; scaled to target image size.
    """
    from PIL import Image, ImageDraw, ImageFont  # type: ignore

    base = Image.open(target_path).convert("RGBA")
    w, h = base.size

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Try to load a font; fall back to default if unavailable
    try:
        font = ImageFont.truetype("arial.ttf", size=max(14, h // 40))
        font_small = ImageFont.truetype("arial.ttf", size=max(12, h // 50))
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    for idx, poly in enumerate(polygons):
        points_norm = poly.get("points", [])
        class_label = poly.get("class_label", "unknown")
        value = poly.get("value")
        unit  = poly.get("unit", "")

        if len(points_norm) < 3:
            continue

        pixel_pts = [(round(p["x"] * w), round(p["y"] * h)) for p in points_norm]
        rgb = _class_color(class_label, idx)

        # Semi-transparent filled polygon
        draw.polygon(pixel_pts, fill=(*rgb, 70), outline=(*rgb, 220))

        # Thicker outline by drawing each edge as a line
        for j in range(len(pixel_pts)):
            draw.line(
                [pixel_pts[j], pixel_pts[(j + 1) % len(pixel_pts)]],
                fill=(*rgb, 230),
                width=max(2, w // 400),
            )

        # Label badge at centroid
        cx = int(sum(p[0] for p in pixel_pts) / len(pixel_pts))
        cy = int(sum(p[1] for p in pixel_pts) / len(pixel_pts))

        label_line1 = class_label.upper()
        label_line2 = f"{value} {unit}".strip() if value is not None else ""

        # Measure text to draw background box
        bbox1 = draw.textbbox((0, 0), label_line1, font=font)
        tw1 = bbox1[2] - bbox1[0]
        th1 = bbox1[3] - bbox1[1]
        tw2, th2 = 0, 0
        if label_line2:
            bbox2 = draw.textbbox((0, 0), label_line2, font=font_small)
            tw2 = bbox2[2] - bbox2[0]
            th2 = bbox2[3] - bbox2[1]

        pad = 6
        box_w = max(tw1, tw2) + pad * 2
        box_h = th1 + (th2 + 2 if label_line2 else 0) + pad * 2

        bx0 = cx - box_w // 2
        by0 = cy - box_h // 2
        bx1, by1 = bx0 + box_w, by0 + box_h

        # Dark pill background
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=4, fill=(15, 20, 28, 200))

        # Colour left accent strip
        draw.rounded_rectangle([bx0, by0, bx0 + 4, by1], radius=2, fill=(*rgb, 230))

        # Text
        draw.text((bx0 + pad + 4, by0 + pad), label_line1, font=font, fill=(255, 255, 255, 255))
        if label_line2:
            draw.text(
                (bx0 + pad + 4, by0 + pad + th1 + 2),
                label_line2, font=font_small, fill=(220, 220, 220, 200),
            )

    result = Image.alpha_composite(base, overlay).convert("RGB")

    import io
    buf = io.BytesIO()
    result.save(buf, format="JPEG", quality=93, optimize=True)
    return buf.getvalue()


def build_yolo_label(polygons: list[dict[str, Any]]) -> str:
    """
    Build YOLO segmentation label file content.
    Format per line: <class_id> <x1> <y1> <x2> <y2> … <xn> <yn>  (normalized 0-1)
    """
    lines: list[str] = []
    for poly in polygons:
        class_label = (poly.get("class_label") or "").lower()
        class_id = YOLO_CLASS_ID.get(class_label)
        if class_id is None:
            continue
        points = poly.get("points", [])
        if len(points) < 3:
            continue
        coords = " ".join(f"{p['x']:.6f} {p['y']:.6f}" for p in points)
        lines.append(f"{class_id} {coords}")
    return ("\n".join(lines) + "\n") if lines else ""


@dataclass
class ReviewStore:
    folder: Path
    state_path: Path
    session_key: str
    state: dict[str, Any]

    def _apply_default_scale_profile(self) -> bool:
        if self.state.get("scale_profile_path"):
            return False
        default_path = default_scale_profile_path()
        if default_path is None:
            return False
        profile = load_scale_profile(str(default_path))
        if not profile:
            return False
        self.state["scale_profile_path"] = str(default_path)
        self.state["scale_profile"] = [
            [k, v[0], v[1]] for k, v in sorted(profile.items())
        ]
        return True

    @classmethod
    def open(cls, folder_path: str) -> "ReviewStore":
        folder = normalize_folder(folder_path)
        session_key = session_key_for(folder)
        state_path = state_path_for(folder)
        state_path.parent.mkdir(parents=True, exist_ok=True)

        if state_path.exists():
            raw_text = state_path.read_text(encoding="utf-8")
            try:
                state = json.loads(raw_text)
            except json.JSONDecodeError:
                # Recovery path for partially-corrupted state files:
                # 1) keep a sidecar copy for manual inspection
                # 2) salvage first JSON object when possible
                # 3) otherwise start a fresh state
                backup_name = f"{state_path.stem}.corrupt-{datetime.now().strftime('%Y%m%d_%H%M%S')}{state_path.suffix}"
                backup_path = state_path.with_name(backup_name)
                try:
                    backup_path.write_text(raw_text, encoding="utf-8")
                except Exception:
                    pass

                recovered: dict[str, Any] | None = None
                stripped = raw_text.lstrip("\ufeff \t\r\n")
                try:
                    decoded, _ = json.JSONDecoder().raw_decode(stripped)
                    if isinstance(decoded, dict):
                        recovered = decoded
                except Exception:
                    recovered = None

                state = recovered if recovered is not None else _new_state_payload(folder, session_key)
        else:
            state = _new_state_payload(folder, session_key)

        if not isinstance(state, dict):
            state = _new_state_payload(folder, session_key)

        state["folder_path"] = str(folder)
        state["session_key"] = session_key
        state.setdefault("target_folder_path", None)
        state.setdefault("csv_path", None)
        state.setdefault("csv_rows", {})
        state.setdefault("scale_profile_path", None)
        state.setdefault("scale_profile", None)
        state.setdefault("images", {})
        state.setdefault("ui_state", DEFAULT_UI_STATE.model_dump())
        for image_state in state["images"].values():
            if isinstance(image_state, dict):
                image_state.setdefault("correction_mode", "patch")
                image_state.setdefault("prediction_actions", {})
        store = cls(folder=folder, state_path=state_path, session_key=session_key, state=state)
        if store._apply_default_scale_profile():
            store.save()
        return store

    def save(self) -> None:
        self.state["updated_at"] = utc_now_iso()
        payload = json.dumps(self.state, indent=2)
        tmp_path = self.state_path.with_suffix(f"{self.state_path.suffix}.tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, self.state_path)

    def _scan_images(self) -> list[str]:
        files = [
            relative_to_folder(self.folder, file_path)
            for file_path in self.folder.rglob("*")
            if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        return sorted(files, key=str.casefold)

    def _record_for(self, relative_path: str) -> dict[str, Any]:
        return self.state["images"].get(relative_path, {})

    def load_session(self) -> SessionPayload:
        image_records: list[ImageRecord] = []
        csv_rows: dict[str, list[dict[str, Any]]] = self.state.get("csv_rows", {})

        for relative_path in self._scan_images():
            stored = self._record_for(relative_path)
            decision = Decision(stored.get("decision", Decision.UNREVIEWED.value))
            filename = Path(relative_path).name
            correction_mode = _normalize_correction_mode(stored.get("correction_mode"))
            prediction_actions = {
                str(key): _normalize_prediction_action(value)
                for key, value in (stored.get("prediction_actions") or {}).items()
            }

            # Load prediction boxes from linked CSV
            raw_boxes = csv_rows.get(filename, [])
            prediction_boxes = [
                PredictionBox(
                    **box,
                    action=prediction_actions.get(str(box.get("object_id", "")), "keep"),
                )
                for box in raw_boxes
            ]

            # Load polygon annotations (including real-world value/unit if calculated)
            raw_polygons = stored.get("polygons", [])
            polygons = [
                PolygonAnnotation(
                    id=poly.get("id", ""),
                    class_label=poly.get("class_label", ""),
                    points=[PolygonPoint(**p) for p in poly.get("points", [])],
                    value=poly.get("value"),
                    unit=poly.get("unit", ""),
                    source_object_id=poly.get("source_object_id"),
                    merge_action="replace" if str(poly.get("merge_action", "add")).lower() == "replace" else "add",
                )
                for poly in raw_polygons
            ]

            image_records.append(
                ImageRecord(
                    relative_path=relative_path,
                    filename=filename,
                    image_url=(
                        f"/api/image?folder_path={quote(str(self.folder), safe='')}"
                        f"&relative_path={quote(relative_path, safe='')}"
                    ),
                    decision=decision,
                    reviewed=decision != Decision.UNREVIEWED,
                    selected=decision == Decision.WRONG,
                    reviewed_at=stored.get("reviewed_at"),
                    annotation_count=len(raw_polygons),
                    polygons=polygons,
                    prediction_boxes=prediction_boxes,
                    image_natural_width=stored.get("image_natural_width"),
                    image_natural_height=stored.get("image_natural_height"),
                    correction_mode=correction_mode,
                )
            )

        ui_state = UiState(**self.state.get("ui_state", DEFAULT_UI_STATE.model_dump()))
        ui_state.filter_mode = _normalize_filter_mode(ui_state.filter_mode)
        if ui_state.current_relative_path and ui_state.current_relative_path not in {
            item.relative_path for item in image_records
        }:
            ui_state.current_relative_path = None

        return SessionPayload(
            folder_path=str(self.folder),
            session_key=self.session_key,
            target_folder_path=self.state.get("target_folder_path"),
            csv_path=self.state.get("csv_path"),
            scale_profile_path=self.state.get("scale_profile_path"),
            images=image_records,
            summary=build_summary(image_records),
            ui_state=ui_state,
        )

    def update_decision(self, relative_path: str, decision: Decision) -> SessionPayload:
        validate_relative_path(self.folder, relative_path)
        image_state = self.state["images"].setdefault(relative_path, {})
        image_state["decision"] = decision.value

        if decision == Decision.UNREVIEWED:
            image_state.pop("reviewed_at", None)
        else:
            image_state["reviewed_at"] = utc_now_iso()

        self.save()
        return self.load_session()

    def update_ui_state(self, current_relative_path: str | None, filter_mode: str) -> SessionPayload:
        if current_relative_path:
            validate_relative_path(self.folder, current_relative_path)

        self.state["ui_state"] = {
            "current_relative_path": current_relative_path,
            "filter_mode": _normalize_filter_mode(filter_mode),
        }
        self.save()
        return self.load_session()

    def update_target_folder_path(self, target_folder_path: str | None) -> SessionPayload:
        normalized_target = None
        if target_folder_path:
            normalized_target = str(normalize_folder(target_folder_path))

        self.state["target_folder_path"] = normalized_target
        self.save()
        return self.load_session()

    def link_csv(self, csv_path: str) -> SessionPayload:
        """Parse a CSV results file and link it to this session."""
        csv_file = Path(_fix_path_input(csv_path)).resolve()
        if not csv_file.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_file}")
        if not csv_file.is_file():
            raise ValueError(f"Path is not a file: {csv_file}")

        rows_by_filename: dict[str, list[dict[str, Any]]] = {}
        with open(csv_file, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            header_map = _resolve_csv_header_map(list(reader.fieldnames or []))
            if not header_map.get("image_filename"):
                raise ValueError("CSV is missing required column: Image Filename")
            for row in reader:
                filename = str(_row_value(row, header_map, "image_filename") or "").strip()
                if not filename:
                    continue
                if filename not in rows_by_filename:
                    rows_by_filename[filename] = []
                rows_by_filename[filename].append({
                    "object_id": _safe_int(_row_value(row, header_map, "object_id")),
                    "road_type": str(_row_value(row, header_map, "road_type") or "").strip(),
                    "class_label": str(_row_value(row, header_map, "class_label") or "").strip(),
                    "value": _safe_float(_row_value(row, header_map, "value")),
                    "unit": str(_row_value(row, header_map, "unit") or "").strip(),
                    "x1": _safe_int(_row_value(row, header_map, "x1")),
                    "y1": _safe_int(_row_value(row, header_map, "y1")),
                    "x2": _safe_int(_row_value(row, header_map, "x2")),
                    "y2": _safe_int(_row_value(row, header_map, "y2")),
                    "confidence": _safe_float(_row_value(row, header_map, "confidence")),
                })

        self.state["csv_path"] = str(csv_file)
        self.state["csv_rows"] = rows_by_filename
        self.save()
        return self.load_session()

    def link_scale_profile(self, scale_profile_path: str) -> SessionPayload:
        """Parse a scale_profile.csv and persist it in the session for real-world calculations."""
        profile = load_scale_profile(scale_profile_path)
        if not profile:
            raise ValueError(
                "Scale profile CSV contained no valid rows with in_roi=1. "
                "Check that the file has columns: row_index, in_roi, x_scale_m_per_px, y_scale_m_per_px"
            )
        self.state["scale_profile_path"] = str(Path(scale_profile_path).resolve())
        # Serialize as list of [row_idx, x_scale, y_scale] for compact JSON storage
        self.state["scale_profile"] = [
            [k, v[0], v[1]] for k, v in sorted(profile.items())
        ]
        self.save()
        return self.load_session()

    def calculate_polygon_metrics(
        self,
        class_label: str,
        points: list[dict[str, Any]],
        nat_w: int,
        nat_h: int,
    ) -> tuple[float, str]:
        """Compute real-world area/length for a polygon using the linked scale profile."""
        raw_profile = self.state.get("scale_profile")
        if not raw_profile:
            raise ValueError(
                "No scale profile linked to this session. "
                "Link a scale_profile.csv file first."
            )
        scale_profile: ScaleProfile = {
            int(row[0]): (float(row[1]), float(row[2])) for row in raw_profile
        }
        return _calculate_polygon_metrics(points, nat_w, nat_h, class_label, scale_profile)

    def update_annotations(
        self,
        relative_path: str,
        polygons: list[dict[str, Any]],
        image_natural_width: int,
        image_natural_height: int,
        correction_mode: str = "patch",
        prediction_actions: dict[str, str] | None = None,
    ) -> SessionPayload:
        """Store polygon annotations for a single image."""
        validate_relative_path(self.folder, relative_path)
        image_state = self.state["images"].setdefault(relative_path, {})
        normalized_actions = {
            str(key): _normalize_prediction_action(value)
            for key, value in (prediction_actions or {}).items()
        }
        normalized_polygons = []
        for poly in polygons:
            normalized_polygons.append({
                **poly,
                "source_object_id": poly.get("source_object_id"),
                "merge_action": "replace" if str(poly.get("merge_action", "add")).lower() == "replace" else "add",
            })
        image_state["polygons"] = normalized_polygons
        image_state["image_natural_width"] = image_natural_width
        image_state["image_natural_height"] = image_natural_height
        image_state["correction_mode"] = _normalize_correction_mode(correction_mode)
        image_state["prediction_actions"] = normalized_actions
        self.save()
        return self.load_session()

    def update_decisions_batch(self, relative_paths: list[str], decision: Decision) -> SessionPayload:
        if not relative_paths:
            raise ValueError("At least one image path is required.")

        for relative_path in relative_paths:
            validate_relative_path(self.folder, relative_path)
            image_state = self.state["images"].setdefault(relative_path, {})
            image_state["decision"] = decision.value
            if decision == Decision.UNREVIEWED:
                image_state.pop("reviewed_at", None)
            else:
                image_state["reviewed_at"] = utc_now_iso()

        self.save()
        return self.load_session()

    def export_updated_csv(self) -> tuple[Path, str, int]:
        """Generate updated CSV combining original predictions with patch/redraw corrections."""
        csv_path_str = self.state.get("csv_path")
        if not csv_path_str:
            raise ValueError("No CSV linked to this session. Link a results CSV first.")

        csv_file = Path(csv_path_str)
        if not csv_file.exists():
            raise FileNotFoundError(f"Linked CSV not found: {csv_file}")

        # Read original CSV
        with open(csv_file, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            original_fieldnames = list(reader.fieldnames or [])
            header_map = _resolve_csv_header_map(original_fieldnames)
            original_rows = list(reader)

        image_filename_header = header_map.get("image_filename") or "Image Filename"
        road_type_header = header_map.get("road_type")
        object_id_header = header_map.get("object_id") or "Object ID"
        class_label_header = header_map.get("class_label") or "Class"
        value_header = header_map.get("value") or "Value"
        unit_header = header_map.get("unit") or "Unit"
        x1_header = header_map.get("x1") or "X1 (px)"
        y1_header = header_map.get("y1") or "Y1 (px)"
        x2_header = header_map.get("x2") or "X2 (px)"
        y2_header = header_map.get("y2") or "Y2 (px)"
        confidence_header = header_map.get("confidence") or "Confidence"

        if not original_fieldnames:
            raise ValueError("Linked CSV has no header row.")
        if not header_map.get("image_filename"):
            raise ValueError("Linked CSV is missing required column: Image Filename")

        # Group original rows by filename, preserving file order
        rows_by_filename: dict[str, list[dict[str, Any]]] = defaultdict(list)
        filename_order: list[str] = []
        road_type_by_filename: dict[str, str] = {}
        for row in original_rows:
            fname = str(row.get(image_filename_header, "") or "").strip()
            if fname not in rows_by_filename:
                filename_order.append(fname)
            rows_by_filename[fname].append(row)
            if road_type_header and fname and fname not in road_type_by_filename:
                road_type_by_filename[fname] = str(row.get(road_type_header, "") or "").strip()

        # Build filename -> image state mapping
        filename_to_state: dict[str, dict[str, Any]] = {}
        for rel_path, img_state in self.state["images"].items():
            filename_to_state[Path(rel_path).name] = img_state
            if Path(rel_path).name not in rows_by_filename:
                filename_order.append(Path(rel_path).name)

        output_rows: list[dict[str, Any]] = []
        replaced_count = 0

        def polygon_bbox(points: list[dict[str, Any]], nat_w: int, nat_h: int) -> tuple[int, int, int, int]:
            if not points or nat_w <= 0 or nat_h <= 0:
                return 0, 0, 0, 0
            xs = [p["x"] * nat_w for p in points]
            ys = [p["y"] * nat_h for p in points]
            return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))

        def export_row_for_polygon(
            fname: str,
            poly: dict[str, Any],
            nat_w: int,
            nat_h: int,
            object_id: int,
        ) -> dict[str, Any]:
            points = poly.get("points", [])
            class_label = poly.get("class_label", "")
            stored_value = poly.get("value")
            stored_unit = poly.get("unit", "")
            x1, y1, x2, y2 = polygon_bbox(points, nat_w, nat_h)
            unit = stored_unit or ("m" if class_label.lower() == "crack" else "m^2")
            export_value = "" if stored_value is None else stored_value
            out: dict[str, Any] = {
                image_filename_header: fname,
                object_id_header: object_id,
                class_label_header: class_label,
                value_header: export_value,
                unit_header: unit,
                x1_header: x1,
                y1_header: y1,
                x2_header: x2,
                y2_header: y2,
                confidence_header: "1.0",
                "Polygon Points": json.dumps(
                    [{"x": round(p["x"], 6), "y": round(p["y"], 6)} for p in points]
                ),
            }
            if road_type_header:
                out[road_type_header] = road_type_by_filename.get(fname, "")
            return out

        for fname in filename_order:
            img_state = filename_to_state.get(fname, {})
            decision = img_state.get("decision", "unreviewed")
            polygons = img_state.get("polygons", [])
            nat_w = img_state.get("image_natural_width", 0)
            nat_h = img_state.get("image_natural_height", 0)
            correction_mode = _normalize_correction_mode(img_state.get("correction_mode"))
            prediction_actions = {
                str(key): _normalize_prediction_action(value)
                for key, value in (img_state.get("prediction_actions") or {}).items()
            }
            original_rows_for_file = rows_by_filename.get(fname, [])
            original_ids = [_safe_int(row.get(object_id_header, 0)) for row in original_rows_for_file]
            unique_original_ids = sorted({oid for oid in original_ids if oid > 0})
            next_object_id = max(unique_original_ids, default=0) + 1
            retained_object_ids: set[int] = set()

            replace_polygons_by_object: dict[str, dict[str, Any]] = {}
            add_polygons: list[dict[str, Any]] = []
            for poly in polygons:
                merge_action = "replace" if str(poly.get("merge_action", "add")).lower() == "replace" else "add"
                source_object_id = poly.get("source_object_id")
                if merge_action == "replace" and source_object_id is not None:
                    replace_polygons_by_object[str(source_object_id)] = poly
                else:
                    add_polygons.append(poly)

            has_merge_changes = (
                decision == "wrong"
                or bool(polygons)
                or any(action != "keep" for action in prediction_actions.values())
                or correction_mode == "redraw_all"
            )

            if not has_merge_changes:
                for orig_row in original_rows_for_file:
                    out = dict(orig_row)
                    out["Polygon Points"] = out.get("Polygon Points", "")
                    output_rows.append(out)
                continue

            replaced_count += 1

            if correction_mode == "redraw_all":
                reusable_object_ids = list(unique_original_ids)
                for poly in polygons:
                    if reusable_object_ids:
                        object_id = reusable_object_ids.pop(0)
                    else:
                        object_id = next_object_id
                        next_object_id += 1
                    output_rows.append(export_row_for_polygon(fname, poly, nat_w, nat_h, object_id))
                continue

            for orig_row in original_rows_for_file:
                object_id = _safe_int(orig_row.get(object_id_header, 0))
                action = prediction_actions.get(str(object_id), "keep")
                if action == "delete":
                    continue
                if action == "replace":
                    replacement = replace_polygons_by_object.get(str(object_id))
                    if replacement is not None:
                        output_rows.append(export_row_for_polygon(fname, replacement, nat_w, nat_h, object_id))
                    else:
                        out = dict(orig_row)
                        out["Polygon Points"] = out.get("Polygon Points", "")
                        output_rows.append(out)
                    retained_object_ids.add(object_id)
                    continue
                out = dict(orig_row)
                out["Polygon Points"] = out.get("Polygon Points", "")
                output_rows.append(out)
                retained_object_ids.add(object_id)

            reusable_object_ids = [oid for oid in unique_original_ids if oid not in retained_object_ids]
            for poly in add_polygons:
                if reusable_object_ids:
                    object_id = reusable_object_ids.pop(0)
                else:
                    object_id = next_object_id
                    next_object_id += 1
                output_rows.append(export_row_for_polygon(fname, poly, nat_w, nat_h, object_id))

        if not output_rows:
            raise ValueError("No data to export.")

        # Fieldnames: all original columns + Polygon Points
        fieldnames = list(dict.fromkeys(original_fieldnames + ["Polygon Points"]))

        tmp_file = tempfile.NamedTemporaryFile(
            prefix="updated_", suffix=".csv", delete=False,
            mode="w", newline="", encoding="utf-8-sig",  # BOM so Excel opens as UTF-8
        )
        tmp_path = Path(tmp_file.name)
        writer = csv.DictWriter(tmp_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in output_rows:
            for field in fieldnames:
                row.setdefault(field, "")
            writer.writerow(row)
        tmp_file.close()

        stem = csv_file.stem
        export_name = f"{stem}_updated.csv"
        return tmp_path, export_name, replaced_count

    def resolve_target_image(self, relative_path: str) -> Path:
        target_folder_path = self.state.get("target_folder_path")
        if not target_folder_path:
            raise ValueError("Target image path is required before export.")

        target_folder = normalize_folder(target_folder_path)
        return validate_relative_path(target_folder, relative_path)

    def export_selected(self) -> tuple[Path, str, int]:
        session = self.load_session()
        selected_images = [item for item in session.images if item.selected]
        if not selected_images:
            raise ValueError("No selected images to export.")

        if not session.target_folder_path:
            raise ValueError("Target image path is required before export.")

        export_time = utc_now_iso()
        export_base_name = infer_export_base_name(selected_images, self.session_key)
        export_name = f"{export_base_name}.zip"
        tmp_file = tempfile.NamedTemporaryFile(prefix=f"{export_base_name}_", suffix=".zip", delete=False)
        tmp_path = Path(tmp_file.name)
        tmp_file.close()

        manifest_rows = []
        target_paths_by_relative_path: dict[str, Path] = {}
        missing_targets = []
        for index, item in enumerate(selected_images, start=1):
            try:
                target_path = self.resolve_target_image(item.relative_path)
            except (FileNotFoundError, NotADirectoryError, ValueError):
                missing_targets.append(item.relative_path)
                continue

            target_paths_by_relative_path[item.relative_path] = target_path

            manifest_rows.append(
                {
                    "index": index,
                    "filename": item.filename,
                    "relative_path": item.relative_path,
                    "source_path": str((self.folder / item.relative_path).resolve()),
                    "target_filename": target_path.name,
                    "target_relative_path": item.relative_path,
                    "target_source_path": str(target_path),
                    "decision": item.decision.value,
                    "reviewed_at": item.reviewed_at,
                }
            )

        if missing_targets:
            preview = ", ".join(missing_targets[:5])
            suffix = "" if len(missing_targets) <= 5 else " ..."
            raise ValueError(
                "Target image path does not contain matching files for: "
                f"{preview}{suffix}"
            )

        manifest_payload = {
            "folder_path": str(self.folder),
            "target_folder_path": session.target_folder_path,
            "session_key": self.session_key,
            "exported_at": export_time,
            "selected_count": len(selected_images),
            "images": manifest_rows,
        }

        with ZipFile(tmp_path, mode="w", compression=ZIP_DEFLATED) as zip_file:
            zip_file.writestr("manifest.json", json.dumps(manifest_payload, indent=2))
            zip_file.writestr("manifest.csv", build_csv(manifest_rows))
            zip_file.writestr("classes.txt", CLASSES_TXT)

            for item in selected_images:
                target_path = target_paths_by_relative_path[item.relative_path]
                img_state   = self.state["images"].get(item.relative_path, {})
                polygons    = img_state.get("polygons", [])

                # ── images/ — clean originals (use directly for YOLO training)
                zip_file.write(target_path, arcname=f"images/{item.relative_path}")

                # ── annotated/ — polygon overlays for visual review
                if polygons:
                    try:
                        annotated_bytes = render_annotation_on_image(target_path, polygons)
                        stem = Path(item.relative_path).stem
                        parent = Path(item.relative_path).parent.as_posix()
                        ann_path = f"{parent}/{stem}_annotated.jpg" if parent != "." else f"{stem}_annotated.jpg"
                        zip_file.writestr(f"annotated/{ann_path}", annotated_bytes)
                    except Exception:
                        # If rendering fails, fall back to the clean image
                        zip_file.write(target_path, arcname=f"annotated/{item.relative_path}")

                    # ── labels/ — YOLO segmentation label files
                    label_txt  = build_yolo_label(polygons)
                    label_rel  = Path(item.relative_path).with_suffix(".txt").as_posix()
                    zip_file.writestr(f"labels/{label_rel}", label_txt)

        return tmp_path, export_name, len(selected_images)

    def export_selected_filenames_txt(self) -> tuple[Path, str, int]:
        session = self.load_session()
        selected_images = [item for item in session.images if item.selected]
        if not selected_images:
            raise ValueError("No selected images to export.")

        export_base_name = infer_export_base_name(selected_images, self.session_key)
        export_name = f"{export_base_name}.txt"
        tmp_file = tempfile.NamedTemporaryFile(prefix=f"{export_base_name}_", suffix=".txt", delete=False)
        tmp_path = Path(tmp_file.name)
        tmp_file.close()
        tmp_path.write_text(build_selected_filenames_txt(selected_images), encoding="utf-8")
        return tmp_path, export_name, len(selected_images)
