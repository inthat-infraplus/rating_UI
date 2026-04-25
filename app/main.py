from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy import select

from . import task_service
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
from .models_db import User, UserRole
from .schemas_task import (
    AssignRequest,
    CommentRequest,
    ReturnRequest,
    TaskCreate,
    TaskUpdate,
    UserCreate,
)
from .models import (
    AreaCalculationRequest,
    CsvLinkRequest,
    FolderRequest,
    ImageAnnotationUpdateRequest,
    ReviewUpdateRequest,
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
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        }
    return JSONResponse(content={"user": data}, status_code=201)
