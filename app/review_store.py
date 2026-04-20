from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

from .models import Decision, ImageRecord, SessionPayload, SessionSummary, UiState

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tif", ".tiff"}
DEFAULT_UI_STATE = UiState()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_folder(folder_path: str) -> Path:
    folder = Path(folder_path).expanduser().resolve()
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


class _ListWriter(list[str]):
    def write(self, value: str) -> int:
        self.append(value)
        return len(value)


def build_summary(images: list[ImageRecord]) -> SessionSummary:
    total_count = len(images)
    reviewed_count = sum(1 for item in images if item.reviewed)
    selected_count = sum(1 for item in images if item.selected)
    correct_count = sum(1 for item in images if item.decision == Decision.CORRECT)
    percent_reviewed = round((reviewed_count / total_count) * 100, 1) if total_count else 0.0
    return SessionSummary(
        total_count=total_count,
        reviewed_count=reviewed_count,
        selected_count=selected_count,
        correct_count=correct_count,
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
                "images": {},
                "ui_state": DEFAULT_UI_STATE.model_dump(),
            }

        state["folder_path"] = str(folder)
        state["session_key"] = session_key
        state.setdefault("target_folder_path", None)
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

        for relative_path in self._scan_images():
            stored = self._record_for(relative_path)
            decision = Decision(stored.get("decision", Decision.UNREVIEWED.value))
            image_records.append(
                ImageRecord(
                    relative_path=relative_path,
                    filename=Path(relative_path).name,
                    image_url=(
                        f"/api/image?folder_path={quote(str(self.folder), safe='')}"
                        f"&relative_path={quote(relative_path, safe='')}"
                    ),
                    decision=decision,
                    reviewed=decision != Decision.UNREVIEWED,
                    selected=decision == Decision.WRONG,
                    reviewed_at=stored.get("reviewed_at"),
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
            for item in selected_images:
                target_path = target_paths_by_relative_path[item.relative_path]
                zip_file.write(target_path, arcname=f"images/{item.relative_path}")

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
