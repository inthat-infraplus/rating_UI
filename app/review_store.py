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

    @classmethod
    def open(cls, folder_path: str) -> "ReviewStore":
        folder = normalize_folder(folder_path)
        session_key = session_key_for(folder)
        state_path = state_path_for(folder)
        state_path.parent.mkdir(parents=True, exist_ok=True)

        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            timestamp = utc_now_iso()
            state = {
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

        state["folder_path"] = str(folder)
        state["session_key"] = session_key
        state.setdefault("target_folder_path", None)
        state.setdefault("csv_path", None)
        state.setdefault("csv_rows", {})
        state.setdefault("scale_profile_path", None)
        state.setdefault("scale_profile", None)
        state.setdefault("images", {})
        state.setdefault("ui_state", DEFAULT_UI_STATE.model_dump())
        return cls(folder=folder, state_path=state_path, session_key=session_key, state=state)

    def save(self) -> None:
        self.state["updated_at"] = utc_now_iso()
        self.state_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

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

            # Load prediction boxes from linked CSV
            raw_boxes = csv_rows.get(filename, [])
            prediction_boxes = [PredictionBox(**box) for box in raw_boxes]

            # Load polygon annotations (including real-world value/unit if calculated)
            raw_polygons = stored.get("polygons", [])
            polygons = [
                PolygonAnnotation(
                    id=poly.get("id", ""),
                    class_label=poly.get("class_label", ""),
                    points=[PolygonPoint(**p) for p in poly.get("points", [])],
                    value=poly.get("value"),
                    unit=poly.get("unit", ""),
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
                )
            )

        ui_state = UiState(**self.state.get("ui_state", DEFAULT_UI_STATE.model_dump()))
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
            "filter_mode": filter_mode,
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
        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                filename = (row.get("Image Filename") or "").strip()
                if not filename:
                    continue
                if filename not in rows_by_filename:
                    rows_by_filename[filename] = []
                rows_by_filename[filename].append({
                    "object_id": _safe_int(row.get("Object ID", 0)),
                    "class_label": (row.get("Class") or "").strip(),
                    "value": _safe_float(row.get("Value", 0)),
                    "unit": (row.get("Unit") or "").strip(),
                    "x1": _safe_int(row.get("X1 (px)", 0)),
                    "y1": _safe_int(row.get("Y1 (px)", 0)),
                    "x2": _safe_int(row.get("X2 (px)", 0)),
                    "y2": _safe_int(row.get("Y2 (px)", 0)),
                    "confidence": _safe_float(row.get("Confidence", 0)),
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
    ) -> SessionPayload:
        """Store polygon annotations for a single image."""
        validate_relative_path(self.folder, relative_path)
        image_state = self.state["images"].setdefault(relative_path, {})
        image_state["polygons"] = polygons
        image_state["image_natural_width"] = image_natural_width
        image_state["image_natural_height"] = image_natural_height
        self.save()
        return self.load_session()

    def export_updated_csv(self) -> tuple[Path, str, int]:
        """Generate updated CSV combining original predictions with polygon corrections."""
        csv_path_str = self.state.get("csv_path")
        if not csv_path_str:
            raise ValueError("No CSV linked to this session. Link a results CSV first.")

        csv_file = Path(csv_path_str)
        if not csv_file.exists():
            raise FileNotFoundError(f"Linked CSV not found: {csv_file}")

        # Read original CSV
        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            original_fieldnames = list(reader.fieldnames or [])
            original_rows = list(reader)

        # Group original rows by filename, preserving file order
        rows_by_filename: dict[str, list[dict[str, Any]]] = defaultdict(list)
        filename_order: list[str] = []
        for row in original_rows:
            fname = (row.get("Image Filename") or "").strip()
            if fname not in rows_by_filename:
                filename_order.append(fname)
            rows_by_filename[fname].append(row)

        # Build filename -> image state mapping
        filename_to_state: dict[str, dict[str, Any]] = {}
        for rel_path, img_state in self.state["images"].items():
            filename_to_state[Path(rel_path).name] = img_state

        output_rows: list[dict[str, Any]] = []
        replaced_count = 0

        for fname in filename_order:
            img_state = filename_to_state.get(fname, {})
            decision = img_state.get("decision", "unreviewed")
            polygons = img_state.get("polygons", [])
            nat_w = img_state.get("image_natural_width", 0)
            nat_h = img_state.get("image_natural_height", 0)

            if decision == "wrong" and polygons and nat_w > 0 and nat_h > 0:
                # Replace original rows with polygon correction rows
                replaced_count += 1
                for i, poly in enumerate(polygons, start=1):
                    points = poly.get("points", [])
                    class_label = poly.get("class_label", "")
                    stored_value = poly.get("value")  # Real-world value if scale profile was used
                    stored_unit = poly.get("unit", "")

                    if points:
                        xs = [p["x"] * nat_w for p in points]
                        ys = [p["y"] * nat_h for p in points]
                        x1, y1 = int(min(xs)), int(min(ys))
                        x2, y2 = int(max(xs)), int(max(ys))
                    else:
                        x1 = y1 = x2 = y2 = 0

                    # Use stored real-world value if available; fall back to unit label only
                    if stored_unit:
                        unit = stored_unit
                    else:
                        unit = "m" if class_label.lower() == "crack" else "m^2"
                    export_value = "" if stored_value is None else stored_value

                    output_rows.append({
                        "Image Filename": fname,
                        "Object ID": i,
                        "Class": class_label,
                        "Value": export_value,
                        "Unit": unit,
                        "X1 (px)": x1,
                        "Y1 (px)": y1,
                        "X2 (px)": x2,
                        "Y2 (px)": y2,
                        "Confidence": "1.0",
                        "Polygon Points": json.dumps(
                            [{"x": round(p["x"], 6), "y": round(p["y"], 6)} for p in points]
                        ),
                    })
            else:
                # Keep original rows unchanged
                for orig_row in rows_by_filename[fname]:
                    out = dict(orig_row)
                    out["Polygon Points"] = ""
                    output_rows.append(out)

        if not output_rows:
            raise ValueError("No data to export.")

        # Fieldnames: all original columns + Polygon Points
        fieldnames = original_fieldnames + ["Polygon Points"]

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
