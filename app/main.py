from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask

from .models import (
    FolderRequest,
    ReviewUpdateRequest,
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
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


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
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", context={})


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


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
