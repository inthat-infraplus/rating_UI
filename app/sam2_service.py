"""SAM2 AI-assist segmentation service.

Wraps Ultralytics' SAM2 (the "sam2.1_b.pt" naming convention is theirs:
https://docs.ultralytics.com/models/sam-2/) so the rating UI can offer
click-to-segment as an annotation tool.

Design notes:
- The model is large (~160 MB) and torch is heavy. We lazy-load on first
  use, never at import time, and never at app startup.
- If ultralytics or torch is not installed, `is_available()` returns False
  with a hint string so the API layer can return 503 with an actionable
  install message instead of crashing.
- The model path is configurable via the `RATING_UI_SAM2_MODEL` env var.
  Default: `<repo-root>/models/sam2.1_b.pt`. Both worktrees and the main
  checkout look in the same relative location, but ops can point this at a
  shared location if they don't want a 160 MB binary in every worktree.
- We accept normalized point coords (0..1) so the front-end doesn't need
  to know the image's natural pixel dimensions twice — same convention as
  the existing polygon storage.
- Output polygons are also normalized 0..1 to match what
  `/api/annotations` already accepts. The front-end can drop them
  straight into `state.finishedPolygons` after un-normalizing to canvas
  coords.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_PATH = BASE_DIR / "models" / "sam2.1_b.pt"

# Minimum number of points a polygon needs to be useful downstream
# (the Draw Polygon tool also enforces ≥3).
_MIN_POLYGON_VERTICES = 3

# How aggressively to thin Ultralytics' raw mask contours. SAM2 returns
# very dense polygons (often 100+ points per object) which are slow to
# draw and edit. We Douglas-Peucker simplify down to something a human
# can grab. Tunable by env var if anyone wants fewer/more vertices.
_DEFAULT_SIMPLIFY_EPS = float(os.environ.get("RATING_UI_SAM2_SIMPLIFY_EPS", "0.003"))


@dataclass
class Sam2Polygon:
    """Normalized polygon vertices in [0, 1] x [0, 1]."""
    points: list[dict]  # [{"x": float, "y": float}, ...]


@dataclass
class Sam2Result:
    polygons: list[Sam2Polygon]
    duration_ms: int
    model_path: str


class Sam2Unavailable(RuntimeError):
    """Raised when ultralytics/torch isn't installed or the model file is
    missing. The API layer should map this to HTTP 503 + a hint."""

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


_LOCK = threading.Lock()
_MODEL = None  # cached ultralytics.SAM instance
_MODEL_LOAD_PATH: str | None = None  # absolute path the cached model was loaded from


def model_path() -> Path:
    raw = os.environ.get("RATING_UI_SAM2_MODEL")
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_MODEL_PATH


def is_available() -> tuple[bool, str]:
    """Returns (ok, reason). When ok=False, `reason` is the user-facing
    install hint. Cheap — does not load the model, just inspects deps and
    file existence so the front-end can grey out the SAM2 button without
    paying the model-load cost."""
    try:
        import ultralytics  # noqa: F401
    except ImportError:
        return False, (
            "SAM2 requires the ultralytics package. Install it once with: "
            "`pip install ultralytics` (this also pulls torch — ~2 GB)."
        )
    try:
        import torch  # noqa: F401
    except ImportError:
        return False, "SAM2 requires PyTorch. Install with `pip install torch`."

    p = model_path()
    if not p.exists():
        return False, (
            f"SAM2 weights not found at {p}. Set RATING_UI_SAM2_MODEL to the "
            f"absolute path of sam2.1_b.pt, or place it at {DEFAULT_MODEL_PATH}."
        )
    return True, ""


def _load_model():
    """Lazy-load the SAM2 model. Thread-safe via _LOCK."""
    global _MODEL, _MODEL_LOAD_PATH
    ok, reason = is_available()
    if not ok:
        raise Sam2Unavailable("SAM2 is not available.", hint=reason)

    p = str(model_path().resolve())
    with _LOCK:
        if _MODEL is not None and _MODEL_LOAD_PATH == p:
            return _MODEL
        # Import inside the lock so the import happens exactly once.
        from ultralytics import SAM
        _MODEL = SAM(p)
        _MODEL_LOAD_PATH = p
        return _MODEL


def _simplify_polygon(points_xy, eps_norm: float, w: int, h: int):
    """Douglas-Peucker simplify a list of (x, y) pixel-coord tuples.

    `eps_norm` is the tolerance expressed in normalized image-fraction
    units (0.003 = 0.3% of the image diagonal). Implemented inline so we
    don't take a hard dependency on cv2 just for `cv2.approxPolyDP`.
    """
    if len(points_xy) <= _MIN_POLYGON_VERTICES:
        return points_xy

    diag = (w * w + h * h) ** 0.5
    eps_px = max(1.0, eps_norm * diag)

    def _perp_distance(pt, a, b):
        # perpendicular distance from pt to segment ab
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return ((pt[0] - ax) ** 2 + (pt[1] - ay) ** 2) ** 0.5
        t = max(0.0, min(1.0, ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / (dx * dx + dy * dy)))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return ((pt[0] - proj_x) ** 2 + (pt[1] - proj_y) ** 2) ** 0.5

    def _dp(pts):
        if len(pts) < 3:
            return pts
        dmax, idx = 0.0, 0
        for i in range(1, len(pts) - 1):
            d = _perp_distance(pts[i], pts[0], pts[-1])
            if d > dmax:
                dmax, idx = d, i
        if dmax <= eps_px:
            return [pts[0], pts[-1]]
        left = _dp(pts[: idx + 1])
        right = _dp(pts[idx:])
        return left[:-1] + right

    simplified = _dp(list(points_xy))
    return simplified if len(simplified) >= _MIN_POLYGON_VERTICES else points_xy


def segment_at_points(
    image_path: str | Path,
    points_norm: list[tuple[float, float]],
    labels: list[int] | None = None,
    *,
    image_natural_width: int | None = None,
    image_natural_height: int | None = None,
    simplify_eps: float = _DEFAULT_SIMPLIFY_EPS,
) -> Sam2Result:
    """Run SAM2 with click prompts and return polygon(s) for the resulting
    mask, all in normalized 0..1 coordinates.

    `points_norm` and `labels` use the convention from Meta's SAM /
    Ultralytics: label 1 = foreground (include), 0 = background (exclude).
    The front-end currently only sends one foreground point per call but
    multi-point support comes for free.
    """
    import time
    from PIL import Image

    if not points_norm:
        raise ValueError("At least one click point is required.")
    if labels is None:
        labels = [1] * len(points_norm)
    if len(labels) != len(points_norm):
        raise ValueError("`labels` length must match `points_norm` length.")

    img_path = Path(image_path)
    if not img_path.exists():
        raise FileNotFoundError(f"Image not found: {img_path}")

    # Resolve true image size if the caller didn't pre-supply it.
    if not image_natural_width or not image_natural_height:
        with Image.open(img_path) as im:
            image_natural_width, image_natural_height = im.size

    w = int(image_natural_width)
    h = int(image_natural_height)

    # Convert normalized clicks to pixel coords for ultralytics.
    px_points = [[float(p[0]) * w, float(p[1]) * h] for p in points_norm]

    model = _load_model()
    t0 = time.perf_counter()
    # Ultralytics SAM signature: model(source, points=[[x, y], ...], labels=[1, 0, ...])
    results = model(str(img_path), points=px_points, labels=labels, verbose=False)
    duration_ms = int((time.perf_counter() - t0) * 1000)

    polygons: list[Sam2Polygon] = []
    for r in results or []:
        masks = getattr(r, "masks", None)
        if masks is None:
            continue
        # masks.xy is a list of (N, 2) arrays — one per detected object,
        # in pixel coords on the original image.
        xy_list = getattr(masks, "xy", None) or []
        for arr in xy_list:
            # arr is numpy ndarray of shape (N, 2).
            pts = [(float(x), float(y)) for x, y in arr.tolist()]
            if len(pts) < _MIN_POLYGON_VERTICES:
                continue
            simplified = _simplify_polygon(pts, simplify_eps, w, h)
            normalized = [
                {"x": max(0.0, min(1.0, x / w)), "y": max(0.0, min(1.0, y / h))}
                for (x, y) in simplified
            ]
            polygons.append(Sam2Polygon(points=normalized))

    return Sam2Result(
        polygons=polygons,
        duration_ms=duration_ms,
        model_path=str(model_path()),
    )
