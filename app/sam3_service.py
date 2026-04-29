"""SAM3 interactive segmentation service via the official source repo.

This service uses Meta's official SAM3 image codepath:
`build_sam3_image_model(...)` + `Sam3Processor.set_image(...)` +
`model.predict_inst(...)`.

The app keeps the existing point/box prompt UI, but the backend now runs the
official repo implementation directly instead of the Transformers wrapper.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_REPO_PATH = BASE_DIR / "sam3-git" / "official-sam3"
DEFAULT_CHECKPOINT_PATH = BASE_DIR / "models" / "sam3.pt"
_MIN_POLYGON_VERTICES = 3
_DEFAULT_SIMPLIFY_EPS = float(os.environ.get("RATING_UI_SAM3_SIMPLIFY_EPS", "0.003"))
_MIN_COMPONENT_AREA_RATIO = float(os.environ.get("RATING_UI_SAM3_MIN_COMPONENT_AREA_RATIO", "0.0015"))


@dataclass
class Sam3Polygon:
    points: list[dict]


@dataclass
class Sam3Result:
    polygons: list[Sam3Polygon]
    duration_ms: int
    model_path: str
    device: str


class Sam3Unavailable(RuntimeError):
    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


_LOCK = threading.Lock()
_THREAD_CACHE: dict[int, tuple[object, object, str, str]] = {}


def repo_path() -> Path:
    raw = os.environ.get("RATING_UI_SAM3_REPO")
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_REPO_PATH


def model_path() -> Path:
    raw = os.environ.get("RATING_UI_SAM3_MODEL")
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_CHECKPOINT_PATH


def preferred_device() -> str:
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def _reset_loaded_model() -> None:
    _THREAD_CACHE.clear()


def _should_retry_on_cpu(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(token in message for token in ("cuda", "cudnn", "out of memory", "cublas"))


def _ensure_repo_on_path() -> None:
    repo = repo_path().resolve()
    repo_str = str(repo)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)


def is_available() -> tuple[bool, str]:
    try:
        import torch  # noqa: F401
    except ImportError:
        return False, "SAM3 requires PyTorch. Install with a CUDA or CPU wheel first."

    repo = repo_path()
    if not repo.exists() or not repo.is_dir():
        return False, (
            f"SAM3 official repo not found at {repo}. Clone facebookresearch/sam3 there "
            f"or set RATING_UI_SAM3_REPO."
        )

    checkpoint = model_path()
    if not checkpoint.exists() or not checkpoint.is_file():
        return False, (
            f"SAM3 checkpoint not found at {checkpoint}. Set RATING_UI_SAM3_MODEL to sam3.pt "
            "from the gated Hugging Face snapshot."
        )

    try:
        _ensure_repo_on_path()
        import sam3  # noqa: F401
        from sam3 import build_sam3_image_model  # noqa: F401
        from sam3.model.sam3_image_processor import Sam3Processor  # noqa: F401
    except ImportError as exc:
        return False, (
            "SAM3 official repo dependencies are incomplete. Ensure the venv has "
            "`timm`, `ftfy`, `iopath`, `einops`, and `pycocotools`, and that the "
            "local official repo is importable."
        )
    return True, ""


def _load_model(force_device: str | None = None):
    ok, reason = is_available()
    if not ok:
        raise Sam3Unavailable("SAM3 is not available.", hint=reason)

    resolved_ckpt = str(model_path().resolve())
    device = force_device or preferred_device()
    thread_id = threading.get_ident()

    with _LOCK:
        cached = _THREAD_CACHE.get(thread_id)
        if cached is not None:
            model, processor, cached_path, cached_device = cached
            if cached_path == resolved_ckpt and cached_device == device:
                return model, processor, device

        import torch

        _ensure_repo_on_path()
        from sam3 import build_sam3_image_model
        from sam3.model.sam3_image_processor import Sam3Processor

        devices_to_try = [device]
        if device != "cpu":
            devices_to_try.append("cpu")

        last_exc: Exception | None = None
        for attempt_device in devices_to_try:
            try:
                model = build_sam3_image_model(
                    checkpoint_path=resolved_ckpt,
                    load_from_HF=False,
                    enable_inst_interactivity=True,
                    device=attempt_device,
                    eval_mode=True,
                )
                processor = Sam3Processor(model)

                _THREAD_CACHE[thread_id] = (model, processor, resolved_ckpt, attempt_device)
                return model, processor, attempt_device
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                _reset_loaded_model()
                if attempt_device != "cpu":
                    try:
                        torch.cuda.empty_cache()
                    except Exception:
                        pass
                    continue
                raise Sam3Unavailable("SAM3 failed to load.", hint=str(last_exc)) from exc

        raise Sam3Unavailable("SAM3 failed to load.", hint=str(last_exc or "unknown error"))


def _simplify_contour(contour: np.ndarray, eps_norm: float, w: int, h: int) -> np.ndarray:
    import cv2

    if contour.shape[0] <= _MIN_POLYGON_VERTICES:
        return contour
    diag = float((w * w + h * h) ** 0.5)
    eps_px = max(1.0, eps_norm * diag)
    simplified = cv2.approxPolyDP(contour, eps_px, closed=True)
    if simplified.shape[0] >= _MIN_POLYGON_VERTICES:
        return simplified
    return contour


def _mask_to_polygons(mask_2d: np.ndarray, simplify_eps: float) -> list[Sam3Polygon]:
    import cv2

    h, w = mask_2d.shape
    binary = (mask_2d > 0).astype(np.uint8) * 255
    if not np.any(binary):
        return []

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []

    min_area_px = max(32.0, float(w * h) * _MIN_COMPONENT_AREA_RATIO)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    polygons: list[Sam3Polygon] = []
    for contour in contours:
        if cv2.contourArea(contour) < min_area_px:
            continue
        contour = _simplify_contour(contour, simplify_eps, w, h)
        if contour.shape[0] < _MIN_POLYGON_VERTICES:
            continue
        points = [
            {
                "x": max(0.0, min(1.0, float(x) / w)),
                "y": max(0.0, min(1.0, float(y) / h)),
            }
            for x, y in contour.reshape(-1, 2).tolist()
        ]
        if len(points) >= _MIN_POLYGON_VERTICES:
            polygons.append(Sam3Polygon(points=points))
        if polygons:
            break
    return polygons


def segment_with_prompts(
    image_path: str | Path,
    points_norm: list[tuple[float, float]],
    labels: list[int] | None = None,
    box_norm: tuple[float, float, float, float] | None = None,
    *,
    image_natural_width: int | None = None,
    image_natural_height: int | None = None,
    simplify_eps: float = _DEFAULT_SIMPLIFY_EPS,
) -> Sam3Result:
    from PIL import Image
    import torch

    if not points_norm and box_norm is None:
        raise ValueError("At least one point or box prompt is required.")
    if labels is None:
        labels = [1] * len(points_norm)
    if len(labels) != len(points_norm):
        raise ValueError("`labels` length must match `points_norm` length.")

    img_path = Path(image_path)
    if not img_path.exists():
        raise FileNotFoundError(f"Image not found: {img_path}")

    with Image.open(img_path) as im:
        image = im.convert("RGB")
        if not image_natural_width or not image_natural_height:
            image_natural_width, image_natural_height = image.size

    w = int(image_natural_width)
    h = int(image_natural_height)

    px_points = None
    px_labels = None
    if points_norm:
        px_points = np.array([[float(x) * w, float(y) * h] for x, y in points_norm], dtype=np.float32)
        px_labels = np.array([int(label) for label in labels], dtype=np.int32)

    px_box = None
    if box_norm is not None:
        x1, y1, x2, y2 = box_norm
        left, right = sorted((float(x1) * w, float(x2) * w))
        top, bottom = sorted((float(y1) * h, float(y2) * h))
        if right - left < 1 or bottom - top < 1:
            raise ValueError("Box prompt must have non-zero width and height.")
        px_box = np.array([[left, top, right, bottom]], dtype=np.float32)

    def _infer_once(run_device: str | None = None):
        model, processor, active_device = _load_model(force_device=run_device)
        t0 = time.perf_counter()
        state = processor.set_image(image)
        masks, scores, _logits = model.predict_inst(
            state,
            point_coords=px_points,
            point_labels=px_labels,
            box=px_box,
            multimask_output=False,
        )
        duration_ms_local = int((time.perf_counter() - t0) * 1000)
        return masks, scores, duration_ms_local, active_device

    try:
        masks, _scores, duration_ms, device = _infer_once()
    except RuntimeError as exc:
        if preferred_device() != "cpu" and _should_retry_on_cpu(exc):
            _reset_loaded_model()
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
            masks, _scores, duration_ms, device = _infer_once("cpu")
        else:
            raise

    polygons: list[Sam3Polygon] = []
    mask_items = list(zip(masks, _scores if _scores is not None else [0] * len(masks)))
    mask_items.sort(key=lambda item: float(item[1]), reverse=True)
    for mask, _score in mask_items:
        polygons = _mask_to_polygons(np.asarray(mask), simplify_eps)
        if polygons:
            break

    return Sam3Result(
        polygons=polygons,
        duration_ms=duration_ms,
        model_path=str(model_path()),
        device=device,
    )
