from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy import select

from . import sam3_service, task_service
from .auth import (
    authenticate,
    current_user,
    get_secret_key,
    hash_password,
    login_user,
    logout_user,
    require_user,
)
from .db import db_session, init_db
from .models_db import Task, TaskStatus, User, UserRole
from .schemas_task import (
    AssignRequest,
    CommentRequest,
    PasswordReset,
    ReturnRequest,
    TaskCreate,
    TaskUpdate,
    UserCreate,
    UserPatch,
)
from .models import (
    AreaCalculationRequest,
    CsvLinkRequest,
    Decision,
    FolderRequest,
    ImageAnnotationUpdateRequest,
    ReviewBatchUpdateRequest,
    ReviewUpdateRequest,
    Sam2SegmentRequest,
    ScaleProfileLinkRequest,
    SessionConfigUpdateRequest,
    UiStateUpdateRequest,
    to_payload_dict,
)
from .review_store import (
    SUPPORTED_EXTENSIONS,
    ReviewStore,
    import_root,
    normalize_folder,
    validate_relative_path,
)

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="Rating UI", version="1.0.0")

# Session cookie (signed via itsdangerous). Must come before routes that use request.session.
app.add_middleware(
    SessionMiddleware,
    secret_key=get_secret_key(),
    session_cookie="rating_ui_session",
    same_site="lax",
    https_only=False,  # local-first; flip to True behind HTTPS proxy
    max_age=60 * 60 * 24 * 7,  # 7 days
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
def _startup() -> None:
    """Create DB tables on first run. Idempotent."""
    init_db()


def open_folder_dialog() -> str | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(title="Select image folder for rating")
    root.destroy()
    return selected or None


def normalize_upload_relative_path(raw_name: str) -> str:
    if not raw_name:
        raise ValueError("Uploaded file is missing a relative path.")

    normalized = raw_name.replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("Uploaded file path is invalid.")
    return Path(*parts).as_posix()


def safe_folder_name(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in name.strip())
    return cleaned.strip("-_") or "browser-import"


def _parse_iso_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _week_start_iso(dt: datetime) -> str:
    week_start = dt.date() - timedelta(days=dt.weekday())
    return week_start.isoformat()


def _build_kpi_summary() -> dict[str, Any]:
    with db_session() as db:
        tasks = list(db.scalars(select(Task).where(Task.deleted_at.is_(None))).all())
        l2_users = list(
            db.scalars(
                select(User).where(User.role == UserRole.L2).order_by(User.username),
            ).all(),
        )

    unique_folders = sorted({str(task.folder_path).strip() for task in tasks if task.folder_path})
    approved_folders = {
        str(task.folder_path).strip()
        for task in tasks
        if task.folder_path and task.status in {TaskStatus.APPROVED, TaskStatus.EXPORTED}
    }

    reviewed_datetimes: list[datetime] = []
    for folder_path in unique_folders:
        try:
            store = ReviewStore.open(folder_path)
        except (FileNotFoundError, NotADirectoryError, ValueError, OSError):
            continue
        raw_images = store.state.get("images", {})
        if not isinstance(raw_images, dict):
            continue
        for image_state in raw_images.values():
            if not isinstance(image_state, dict):
                continue
            decision = str(image_state.get("decision", "")).strip().lower()
            if decision not in {Decision.CORRECT.value, Decision.WRONG.value}:
                continue
            reviewed_at = _parse_iso_datetime(image_state.get("reviewed_at"))
            if reviewed_at is not None:
                reviewed_datetimes.append(reviewed_at)

    counts_by_week: dict[str, int] = defaultdict(int)
    for reviewed_at in reviewed_datetimes:
        counts_by_week[_week_start_iso(reviewed_at)] += 1
    weekly_rows: list[dict[str, Any]] = []
    cumulative = 0
    for week_start in sorted(counts_by_week):
        week_count = counts_by_week[week_start]
        cumulative += week_count
        week_date = datetime.strptime(week_start, "%Y-%m-%d").date()
        iso_week = week_date.isocalendar()
        weekly_rows.append(
            {
                "week_start": week_start,
                "week_label": f"{iso_week.year}-W{iso_week.week:02d}",
                "images_done": week_count,
                "cumulative": cumulative,
            }
        )

    active_statuses = {
        TaskStatus.ASSIGNED,
        TaskStatus.IN_PROGRESS,
        TaskStatus.SUBMITTED,
        TaskStatus.IN_QC,
        TaskStatus.RETURNED,
    }
    done_statuses = {TaskStatus.APPROVED, TaskStatus.EXPORTED}

    workload_by_user: dict[int, dict[str, Any]] = {}
    for user in l2_users:
        workload_by_user[user.id] = {
            "user_id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "is_active": user.is_active,
            "assigned_task_count": 0,
            "active_task_count": 0,
            "approved_task_count": 0,
            "total_images": 0,
            "reviewed_images": 0,
            "correct_images": 0,
            "wrong_images": 0,
            "annotated_images": 0,
            "completion_pct": 0.0,
        }

    for task in tasks:
        if task.assigned_to is None:
            continue
        user_row = workload_by_user.get(task.assigned_to)
        if user_row is None:
            user_row = {
                "user_id": task.assigned_to,
                "username": f"user_{task.assigned_to}",
                "display_name": f"User #{task.assigned_to}",
                "is_active": False,
                "assigned_task_count": 0,
                "active_task_count": 0,
                "approved_task_count": 0,
                "total_images": 0,
                "reviewed_images": 0,
                "correct_images": 0,
                "wrong_images": 0,
                "annotated_images": 0,
                "completion_pct": 0.0,
            }
            workload_by_user[task.assigned_to] = user_row

        user_row["assigned_task_count"] += 1
        if task.status in active_statuses:
            user_row["active_task_count"] += 1
        if task.status in done_statuses:
            user_row["approved_task_count"] += 1
        user_row["total_images"] += int(task.total_images or 0)
        user_row["reviewed_images"] += int(task.reviewed_count or 0)
        user_row["correct_images"] += int(task.correct_count or 0)
        user_row["wrong_images"] += int(task.wrong_count or 0)
        user_row["annotated_images"] += int(task.annotated_count or 0)

    workload_rows = list(workload_by_user.values())
    for row in workload_rows:
        total_images = int(row["total_images"] or 0)
        reviewed_images = int(row["reviewed_images"] or 0)
        row["completion_pct"] = round((reviewed_images / total_images) * 100, 1) if total_images else 0.0

    workload_rows.sort(
        key=lambda item: (
            -int(item.get("reviewed_images", 0)),
            -int(item.get("assigned_task_count", 0)),
            str(item.get("username", "")),
        ),
    )

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "totals": {
            "images_done": len(reviewed_datetimes),
            "approved_folders": len(approved_folders),
            "total_folders": len(unique_folders),
            "l2_users": len(l2_users),
            "tasks": len(tasks),
        },
        "timeline_weekly": weekly_rows,
        "workload_by_labeler": workload_rows,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Landing page = task dashboard. Anonymous → /login."""
    user = current_user(request)
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        request, "dashboard.html", context={"current_user": user},
    )


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_detail_page(task_id: int, request: Request):
    """Task detail = the review UI. Phase 4 will pass task_id into the JS to
    scope review_store; for now it just renders the same UI behind auth."""
    user = current_user(request)
    if user is None:
        return RedirectResponse(url=f"/login?next=/tasks/{task_id}", status_code=302)
    return templates.TemplateResponse(
        request, "index.html",
        context={"current_user": user, "task_id": task_id},
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


# --- Auth routes ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    # If already logged in, bounce to next (default /).
    if current_user(request) is not None:
        return RedirectResponse(url=next or "/", status_code=302)
    return templates.TemplateResponse(
        request, "login.html", context={"error": None, "next": next, "username": ""},
    )


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    user = await run_in_threadpool(authenticate, username, password)
    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            context={"error": "Invalid username or password.", "next": next, "username": username},
            status_code=401,
        )
    login_user(request, user)
    # Prevent open-redirect: only allow same-origin relative paths.
    target = next if (next or "").startswith("/") else "/"
    return RedirectResponse(url=target, status_code=302)


@app.post("/logout")
async def logout(request: Request):
    logout_user(request)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/api/me")
async def me(request: Request) -> JSONResponse:
    user: User = require_user(request)
    return JSONResponse(
        content={
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role.value,
        }
    )


@app.post("/api/select-folder")
async def select_folder() -> JSONResponse:
    selected = open_folder_dialog()
    if not selected:
        raise HTTPException(status_code=400, detail="Folder selection was cancelled.")
    session = await run_in_threadpool(ReviewStore.open(selected).load_session)
    return JSONResponse(content={"session": to_payload_dict(session)})


@app.post("/api/select-target-folder")
async def select_target_folder(request: FolderRequest) -> JSONResponse:
    selected = open_folder_dialog()
    if not selected:
        raise HTTPException(status_code=400, detail="Folder selection was cancelled.")
    try:
        session = await run_in_threadpool(
            ReviewStore.open(request.folder_path).update_target_folder_path,
            selected,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content={"session": to_payload_dict(session)})


@app.post("/api/load-folder")
async def load_folder(request: FolderRequest) -> JSONResponse:
    try:
        session = await run_in_threadpool(ReviewStore.open(request.folder_path).load_session)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content={"session": to_payload_dict(session)})


@app.post("/api/import-folder")
async def import_folder(
    root_name: str = Form("browser-import"),
    files: list[UploadFile] = File(...),
) -> JSONResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    batch_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    target_root = import_root() / batch_name / safe_folder_name(root_name)
    target_root.mkdir(parents=True, exist_ok=True)
    target_root_resolved = target_root.resolve()

    imported_count = 0

    try:
        for upload in files:
            relative_path = normalize_upload_relative_path(upload.filename or "")
            if Path(relative_path).suffix.lower() not in SUPPORTED_EXTENSIONS:
                await upload.close()
                continue

            target_path = (target_root / relative_path).resolve()
            if target_root_resolved not in target_path.parents:
                raise HTTPException(status_code=400, detail="Uploaded file path is invalid.")

            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(await upload.read())
            imported_count += 1
            await upload.close()
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if imported_count == 0:
        raise HTTPException(status_code=400, detail="No supported image files were found in the selected folder.")

    session = await run_in_threadpool(ReviewStore.open(str(target_root)).load_session)
    return JSONResponse(
        content={
            "session": to_payload_dict(session),
            "imported_count": imported_count,
            "source": "browser-upload",
        }
    )


@app.post("/api/review")
async def update_review(request: ReviewUpdateRequest) -> JSONResponse:
    try:
        session = await run_in_threadpool(
            ReviewStore.open(request.folder_path).update_decision,
            request.relative_path,
            request.decision,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _sync_task_progress(request.folder_path, session)
    return JSONResponse(content={"session": to_payload_dict(session)})


@app.post("/api/review/batch")
async def update_review_batch(request: ReviewBatchUpdateRequest) -> JSONResponse:
    try:
        session = await run_in_threadpool(
            ReviewStore.open(request.folder_path).update_decisions_batch,
            request.relative_paths,
            request.decision,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _sync_task_progress(request.folder_path, session)
    return JSONResponse(content={"session": to_payload_dict(session)})


@app.post("/api/ui-state")
async def update_ui_state(request: UiStateUpdateRequest) -> JSONResponse:
    try:
        session = await run_in_threadpool(
            ReviewStore.open(request.folder_path).update_ui_state,
            request.current_relative_path,
            request.filter_mode,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content={"session": to_payload_dict(session)})


@app.post("/api/session-config")
async def update_session_config(request: SessionConfigUpdateRequest) -> JSONResponse:
    try:
        session = await run_in_threadpool(
            ReviewStore.open(request.folder_path).update_target_folder_path,
            request.target_folder_path,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content={"session": to_payload_dict(session)})


@app.post("/api/export")
async def export_selected(request: FolderRequest) -> FileResponse:
    try:
        export_path, export_name, _ = await run_in_threadpool(
            ReviewStore.open(request.folder_path).export_selected
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileResponse(
        export_path,
        media_type="application/zip",
        filename=export_name,
        background=BackgroundTask(lambda path=export_path: path.unlink(missing_ok=True)),
    )


@app.post("/api/export-filenames")
async def export_selected_filenames(request: FolderRequest) -> FileResponse:
    try:
        export_path, export_name, _ = await run_in_threadpool(
            ReviewStore.open(request.folder_path).export_selected_filenames_txt
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileResponse(
        export_path,
        media_type="text/plain; charset=utf-8",
        filename=export_name,
        background=BackgroundTask(lambda path=export_path: path.unlink(missing_ok=True)),
    )


@app.get("/api/image")
async def get_image(
    folder_path: str = Query(..., min_length=1),
    relative_path: str = Query(..., min_length=1),
) -> FileResponse:
    try:
        folder = normalize_folder(folder_path)
        image_path = validate_relative_path(folder, relative_path)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(image_path)


# --- CSV and annotation endpoints ---

@app.post("/api/link-csv")
async def link_csv(request: CsvLinkRequest) -> JSONResponse:
    """Link a CSV results file (server path) to the current session."""
    try:
        session = await run_in_threadpool(
            ReviewStore.open(request.folder_path).link_csv,
            request.csv_path,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content={"session": to_payload_dict(session)})


@app.post("/api/import-csv")
async def import_csv(
    folder_path: str = Form(...),
    csv_file: UploadFile = File(...),
) -> JSONResponse:
    """Upload a CSV file from the browser and link it to the current session."""
    if not folder_path:
        raise HTTPException(status_code=400, detail="folder_path is required.")

    csv_dir = import_root() / "csvs"
    csv_dir.mkdir(parents=True, exist_ok=True)

    original_name = csv_file.filename or "results.csv"
    safe_name = "".join(
        c if c.isalnum() or c in {"-", "_", "."} else "_" for c in original_name
    )
    timestamp_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_path = csv_dir / f"{timestamp_prefix}_{safe_name}"
    saved_path.write_bytes(await csv_file.read())
    await csv_file.close()

    try:
        session = await run_in_threadpool(
            ReviewStore.open(folder_path).link_csv,
            str(saved_path),
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(content={"session": to_payload_dict(session)})


@app.post("/api/annotations")
async def update_annotations(request: ImageAnnotationUpdateRequest) -> JSONResponse:
    """Save polygon annotations for a single image."""
    try:
        session = await run_in_threadpool(
            ReviewStore.open(request.folder_path).update_annotations,
            request.relative_path,
            [poly.model_dump(mode="json") for poly in request.polygons],
            request.image_natural_width,
            request.image_natural_height,
            request.correction_mode,
            request.prediction_actions,
            request.prediction_class_overrides,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _sync_task_progress(request.folder_path, session)
    return JSONResponse(content={"session": to_payload_dict(session)})


@app.post("/api/link-scale-profile")
async def link_scale_profile(request: ScaleProfileLinkRequest) -> JSONResponse:
    """Link a scale_profile.csv (server path) for pixel-to-metre calculations."""
    try:
        session = await run_in_threadpool(
            ReviewStore.open(request.folder_path).link_scale_profile,
            request.scale_profile_path,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content={"session": to_payload_dict(session)})


@app.post("/api/import-scale-profile")
async def import_scale_profile(
    folder_path: str = Form(...),
    scale_file: UploadFile = File(...),
) -> JSONResponse:
    """Upload a scale_profile.csv from the browser and link it to the current session."""
    if not folder_path:
        raise HTTPException(status_code=400, detail="folder_path is required.")

    csv_dir = import_root() / "scale_profiles"
    csv_dir.mkdir(parents=True, exist_ok=True)

    original_name = scale_file.filename or "scale_profile.csv"
    safe_name = "".join(c if c.isalnum() or c in {"-", "_", "."} else "_" for c in original_name)
    timestamp_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_path = csv_dir / f"{timestamp_prefix}_{safe_name}"
    saved_path.write_bytes(await scale_file.read())
    await scale_file.close()

    try:
        session = await run_in_threadpool(
            ReviewStore.open(folder_path).link_scale_profile,
            str(saved_path),
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(content={"session": to_payload_dict(session)})


@app.post("/api/calculate-area")
async def calculate_area(request: AreaCalculationRequest) -> JSONResponse:
    """Calculate real-world area (m²) or crack length (m) for a polygon."""
    try:
        points_dicts = [p.model_dump(mode="json") for p in request.points]
        value, unit = await run_in_threadpool(
            ReviewStore.open(request.folder_path).calculate_polygon_metrics,
            request.class_label,
            points_dicts,
            request.image_natural_width,
            request.image_natural_height,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content={"value": value, "unit": unit})


@app.get("/api/sam3/status")
async def sam3_status(request: Request) -> JSONResponse:
    """Cheap probe: does the server have SAM3 ready to go?"""
    require_user(request)
    ok, reason = sam3_service.is_available()
    return JSONResponse(
        content={
            "available": ok,
            "reason": reason,
            "model_path": str(sam3_service.model_path()),
            "device": sam3_service.preferred_device(),
            "engine": "sam3",
        }
    )


@app.get("/api/sam2/status")
async def sam2_status_alias(request: Request) -> JSONResponse:
    """Backward-compatible alias for older front-end builds."""
    return await sam3_status(request)


@app.post("/api/sam3/segment")
async def sam3_segment(request: Request, payload: Sam2SegmentRequest) -> JSONResponse:
    """Run SAM3 Tracker on point and/or box prompts and return polygons in
    normalized 0..1 coordinates for the existing annotation flow."""
    require_user(request)

    # Reuse the same path-validation helpers /api/image uses, so a malicious
    # `relative_path` can't escape the folder.
    try:
        folder = normalize_folder(payload.folder_path)
        image_path = validate_relative_path(folder, payload.relative_path)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    points_norm = [(p.x, p.y) for p in payload.points]
    box_norm = None
    if payload.box is not None:
        box_norm = (payload.box.x1, payload.box.y1, payload.box.x2, payload.box.y2)
    if not points_norm and box_norm is None:
        raise HTTPException(
            status_code=400, detail="At least one point or box prompt is required."
        )

    try:
        result = await run_in_threadpool(
            sam3_service.segment_with_prompts,
            image_path,
            points_norm,
            payload.labels,
            box_norm,
            image_natural_width=payload.image_natural_width,
            image_natural_height=payload.image_natural_height,
        )
    except sam3_service.Sam3Unavailable as exc:
        # 503 (service unavailable) — distinguishes "feature not configured"
        # from request validation errors and lets the front-end surface the
        # install hint to the operator.
        raise HTTPException(
            status_code=503,
            detail=exc.hint or str(exc),
        ) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(
        content={
            "polygons": [{"points": p.points} for p in result.polygons],
            "duration_ms": result.duration_ms,
            "model_path": result.model_path,
            "device": result.device,
            "engine": "sam3",
        }
    )


@app.post("/api/sam2/segment")
async def sam2_segment_alias(request: Request, payload: Sam2SegmentRequest) -> JSONResponse:
    """Backward-compatible alias for older front-end builds."""
    return await sam3_segment(request, payload)


@app.post("/api/export-updated-csv")
async def export_updated_csv(request: FolderRequest) -> FileResponse:
    """Export an updated CSV with polygon corrections applied to wrong-marked images."""
    try:
        export_path, export_name, _ = await run_in_threadpool(
            ReviewStore.open(request.folder_path).export_updated_csv
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(
        export_path,
        media_type="text/csv; charset=utf-8",
        filename=export_name,
        background=BackgroundTask(lambda path=export_path: path.unlink(missing_ok=True)),
    )


# ─── Phase 2: Task management endpoints ────────────────────────────────────
#
# Permission rules live in app/task_service.py — endpoints just translate
# HTTP into service calls and map service errors onto HTTP status codes.

def _http_from_service_error(exc: task_service.TaskServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _sync_task_progress(folder_path: str, session) -> None:
    """Push the latest review summary into any task pointing at this folder.

    Called fire-and-forget after /api/review and /api/annotations so the
    dashboard cards reflect L2's live progress without polling. Failures are
    swallowed — the review action itself already succeeded."""
    try:
        summary = session.summary
        with db_session() as db:
            task_service.sync_progress_for_folder(
                db,
                folder_path,
                total=summary.total_count,
                reviewed=summary.reviewed_count,
                correct=summary.correct_count,
                wrong=summary.selected_count,
                annotated=summary.annotated_count,
            )
    except Exception:
        pass


@app.get("/api/tasks")
async def api_list_tasks(request: Request) -> JSONResponse:
    user = require_user(request)
    with db_session() as db:
        # Re-attach user to this session so relationship loads work
        db_user = db.get(User, user.id)
        tasks = task_service.list_tasks_for_user(db, db_user)
        payload = [task_service.task_to_dict(t) for t in tasks]
    return JSONResponse(content={"tasks": payload})


@app.post("/api/tasks")
async def api_create_task(request: Request, payload: TaskCreate) -> JSONResponse:
    user = require_user(request)
    try:
        with db_session() as db:
            db_user = db.get(User, user.id)
            task = task_service.create_task(db, db_user, payload)
            db.flush()
            data = task_service.task_to_dict(task)
    except task_service.TaskServiceError as exc:
        raise _http_from_service_error(exc) from exc
    return JSONResponse(content={"task": data}, status_code=201)


@app.get("/api/tasks/{task_id}")
async def api_get_task(task_id: int, request: Request) -> JSONResponse:
    user = require_user(request)
    try:
        with db_session() as db:
            db_user = db.get(User, user.id)
            task = task_service.get_task(db, task_id)
            task_service._require_view(task, db_user)
            data = task_service.task_to_dict(task)
            events = [task_service.event_to_dict(e) for e in task.events]
    except task_service.TaskServiceError as exc:
        raise _http_from_service_error(exc) from exc
    return JSONResponse(content={"task": data, "events": events})


@app.patch("/api/tasks/{task_id}")
async def api_update_task(task_id: int, request: Request, payload: TaskUpdate) -> JSONResponse:
    user = require_user(request)
    try:
        with db_session() as db:
            db_user = db.get(User, user.id)
            task = task_service.update_task(db, db_user, task_id, payload)
            db.flush()
            data = task_service.task_to_dict(task)
    except task_service.TaskServiceError as exc:
        raise _http_from_service_error(exc) from exc
    return JSONResponse(content={"task": data})


@app.delete("/api/tasks/{task_id}")
async def api_delete_task(task_id: int, request: Request) -> JSONResponse:
    user = require_user(request)
    try:
        with db_session() as db:
            db_user = db.get(User, user.id)
            task_service.soft_delete_task(db, db_user, task_id)
    except task_service.TaskServiceError as exc:
        raise _http_from_service_error(exc) from exc
    return JSONResponse(content={"ok": True})


@app.post("/api/tasks/{task_id}/assign")
async def api_assign_task(
    task_id: int, request: Request, payload: AssignRequest
) -> JSONResponse:
    user = require_user(request)
    try:
        with db_session() as db:
            db_user = db.get(User, user.id)
            task = task_service.assign_task(db, db_user, task_id, payload.assigned_to)
            db.flush()
            data = task_service.task_to_dict(task)
    except task_service.TaskServiceError as exc:
        raise _http_from_service_error(exc) from exc
    return JSONResponse(content={"task": data})


@app.post("/api/tasks/{task_id}/submit")
async def api_submit_task(task_id: int, request: Request) -> JSONResponse:
    user = require_user(request)
    try:
        with db_session() as db:
            db_user = db.get(User, user.id)
            task = task_service.submit_for_qc(db, db_user, task_id)
            db.flush()
            data = task_service.task_to_dict(task)
    except task_service.TaskServiceError as exc:
        raise _http_from_service_error(exc) from exc
    return JSONResponse(content={"task": data})


@app.post("/api/tasks/{task_id}/return")
async def api_return_task(
    task_id: int, request: Request, payload: ReturnRequest
) -> JSONResponse:
    user = require_user(request)
    try:
        with db_session() as db:
            db_user = db.get(User, user.id)
            task = task_service.return_to_annotator(
                db, db_user, task_id, payload.message,
            )
            db.flush()
            data = task_service.task_to_dict(task)
    except task_service.TaskServiceError as exc:
        raise _http_from_service_error(exc) from exc
    return JSONResponse(content={"task": data})


@app.post("/api/tasks/{task_id}/approve")
async def api_approve_task(task_id: int, request: Request) -> JSONResponse:
    user = require_user(request)
    try:
        with db_session() as db:
            db_user = db.get(User, user.id)
            task = task_service.approve_task(db, db_user, task_id)
            db.flush()
            data = task_service.task_to_dict(task)
    except task_service.TaskServiceError as exc:
        raise _http_from_service_error(exc) from exc
    return JSONResponse(content={"task": data})


@app.post("/api/tasks/{task_id}/qc-open")
async def api_open_qc(task_id: int, request: Request) -> JSONResponse:
    """Optional helper L1 calls when opening a submitted task — flips SUBMITTED→IN_QC."""
    user = require_user(request)
    try:
        with db_session() as db:
            db_user = db.get(User, user.id)
            task = task_service.open_qc(db, db_user, task_id)
            db.flush()
            data = task_service.task_to_dict(task)
    except task_service.TaskServiceError as exc:
        raise _http_from_service_error(exc) from exc
    return JSONResponse(content={"task": data})


@app.post("/api/tasks/{task_id}/start")
async def api_start_task(task_id: int, request: Request) -> JSONResponse:
    """Called when a user opens a task. For an L2 assignee this flips
    ASSIGNED→IN_PROGRESS (or RETURNED→IN_PROGRESS on resume). Idempotent for L1."""
    user = require_user(request)
    try:
        with db_session() as db:
            db_user = db.get(User, user.id)
            task = task_service.mark_started(db, db_user, task_id)
            db.flush()
            data = task_service.task_to_dict(task)
    except task_service.TaskServiceError as exc:
        raise _http_from_service_error(exc) from exc
    return JSONResponse(content={"task": data})


@app.get("/api/tasks/{task_id}/events")
async def api_list_events(task_id: int, request: Request) -> JSONResponse:
    user = require_user(request)
    try:
        with db_session() as db:
            db_user = db.get(User, user.id)
            events = task_service.list_events(db, db_user, task_id)
            data = [task_service.event_to_dict(e) for e in events]
    except task_service.TaskServiceError as exc:
        raise _http_from_service_error(exc) from exc
    return JSONResponse(content={"events": data})


@app.post("/api/tasks/{task_id}/events")
async def api_add_comment(
    task_id: int, request: Request, payload: CommentRequest
) -> JSONResponse:
    user = require_user(request)
    try:
        with db_session() as db:
            db_user = db.get(User, user.id)
            event = task_service.add_comment(db, db_user, task_id, payload.message)
            db.flush()
            data = task_service.event_to_dict(event)
    except task_service.TaskServiceError as exc:
        raise _http_from_service_error(exc) from exc
    return JSONResponse(content={"event": data}, status_code=201)


# ─── User management (L1 only) ─────────────────────────────────────────────

@app.get("/kpi", response_class=HTMLResponse)
async def kpi_page(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/kpi", status_code=302)
    if user.role != UserRole.L1:
        raise HTTPException(status_code=403, detail="Forbidden - L1 only.")
    return templates.TemplateResponse(
        request, "kpi.html", context={"current_user": user},
    )


@app.get("/api/kpi/summary")
async def api_kpi_summary(request: Request) -> JSONResponse:
    user = require_user(request)
    if user.role != UserRole.L1:
        raise HTTPException(status_code=403, detail="Forbidden - L1 only.")
    return JSONResponse(content=_build_kpi_summary())


@app.get("/api/users")
async def api_list_users(request: Request) -> JSONResponse:
    """Used to populate the assignee dropdown — L1 only, returns active L2 users
    by default. L1 can also pass ?role=L1 to list reviewers."""
    user = require_user(request)
    if user.role != UserRole.L1:
        raise HTTPException(status_code=403, detail="Forbidden — L1 only.")
    role_filter = request.query_params.get("role")
    with db_session() as db:
        q = select(User).where(User.is_active.is_(True))
        if role_filter in {"L1", "L2"}:
            q = q.where(User.role == UserRole(role_filter))
        users = db.scalars(q.order_by(User.username)).all()
        payload = [
            {
                "id": u.id,
                "username": u.username,
                "display_name": u.display_name,
                "role": u.role.value,
            }
            for u in users
        ]
    return JSONResponse(content={"users": payload})


@app.post("/api/admin/users")
async def api_create_user(request: Request, payload: UserCreate) -> JSONResponse:
    user = require_user(request)
    if user.role != UserRole.L1:
        raise HTTPException(status_code=403, detail="Forbidden — L1 only.")
    with db_session() as db:
        existing = db.scalars(
            select(User).where(User.username == payload.username)
        ).first()
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Username {payload.username!r} is already taken.",
            )
        new_user = User(
            username=payload.username,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name or payload.username,
            role=payload.role,
        )
        db.add(new_user)
        db.flush()
        data = {
            "id": new_user.id,
            "username": new_user.username,
            "display_name": new_user.display_name,
            "role": new_user.role.value,
            "is_active": new_user.is_active,
        }
    return JSONResponse(content={"user": data}, status_code=201)


@app.get("/api/admin/users")
async def api_list_all_users(request: Request) -> JSONResponse:
    """L1 admin listing — includes inactive users + last_login_at."""
    user = require_user(request)
    if user.role != UserRole.L1:
        raise HTTPException(status_code=403, detail="Forbidden — L1 only.")
    with db_session() as db:
        users = db.scalars(select(User).order_by(User.username)).all()
        payload = [
            {
                "id": u.id,
                "username": u.username,
                "display_name": u.display_name,
                "role": u.role.value,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            }
            for u in users
        ]
    return JSONResponse(content={"users": payload})


@app.patch("/api/admin/users/{user_id}")
async def api_update_user(
    user_id: int, request: Request, payload: UserPatch
) -> JSONResponse:
    """L1 only — change role / display_name / active flag. Cannot demote
    yourself out of L1 (lockout protection)."""
    actor = require_user(request)
    if actor.role != UserRole.L1:
        raise HTTPException(status_code=403, detail="Forbidden — L1 only.")
    with db_session() as db:
        target = db.get(User, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")

        fields = payload.model_dump(exclude_unset=True)

        # Self-protection: don't let an L1 lock themselves out.
        if user_id == actor.id:
            if fields.get("role") and fields["role"] != UserRole.L1:
                raise HTTPException(
                    status_code=400,
                    detail="You cannot demote yourself from L1.",
                )
            if fields.get("is_active") is False:
                raise HTTPException(
                    status_code=400,
                    detail="You cannot deactivate your own account.",
                )

        for key, value in fields.items():
            setattr(target, key, value)

        data = {
            "id": target.id,
            "username": target.username,
            "display_name": target.display_name,
            "role": target.role.value,
            "is_active": target.is_active,
        }
    return JSONResponse(content={"user": data})


@app.post("/api/admin/users/{user_id}/reset-password")
async def api_reset_password(
    user_id: int, request: Request, payload: PasswordReset
) -> JSONResponse:
    """L1 only — reset another user's password to a new value."""
    actor = require_user(request)
    if actor.role != UserRole.L1:
        raise HTTPException(status_code=403, detail="Forbidden — L1 only.")
    with db_session() as db:
        target = db.get(User, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")
        target.password_hash = hash_password(payload.new_password)
    return JSONResponse(content={"ok": True})


@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    """L1-only admin page rendering admin_users.html."""
    user = current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/admin/users", status_code=302)
    if user.role != UserRole.L1:
        raise HTTPException(status_code=403, detail="Forbidden — L1 only.")
    return templates.TemplateResponse(
        request, "admin_users.html", context={"current_user": user},
    )
