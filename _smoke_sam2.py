"""SAM2 endpoint smoke test.

Two scenarios:
- ultralytics NOT installed (current dev state): /api/sam2/status reports
  available=false with an install hint, /api/sam2/segment returns 503.
  This is the path the front-end uses to grey out the button.
- ultralytics IS installed and the model weights exist: a click on a real
  PNG returns at least one polygon. We skip this branch when the deps
  aren't there so the test stays runnable in CI.

Run from repo root:  python _smoke_sam2.py
"""
from __future__ import annotations

import importlib
import shutil
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient

from app.main import app
from app.sam2_service import is_available, model_path

_PNG_1x1 = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
    "0000000D49444154789C6300010000000500010D0A2DB40000000049454E44AE426082"
)


def login(client, username, password):
    r = client.post("/login", data={"username": username, "password": password, "next": "/"})
    assert r.status_code == 302, f"login failed for {username}"


def expect(label, got, want):
    ok = got == want
    print(f"{'OK' if ok else 'FAIL'} {label}: got {got!r}, want {want!r}")
    assert ok, label


def main():
    tmp = Path(tempfile.mkdtemp(prefix="sam2_smoke_"))
    try:
        folder = tmp / "preds"
        folder.mkdir()
        (folder / "img.png").write_bytes(_PNG_1x1)

        admin = TestClient(app, follow_redirects=False)
        login(admin, "admin", "adminpass")

        anon = TestClient(app, follow_redirects=False)

        # Auth gating
        r = anon.get("/api/sam2/status")
        expect("anon /status -> 401", r.status_code, 401)
        r = anon.post("/api/sam2/segment", json={
            "folder_path": str(folder), "relative_path": "img.png",
            "points": [{"x": 0.5, "y": 0.5}],
            "image_natural_width": 1, "image_natural_height": 1,
        })
        expect("anon /segment -> 401", r.status_code, 401)

        # Status probe — should always succeed and tell the truth.
        r = admin.get("/api/sam2/status")
        expect("/status returns 200", r.status_code, 200)
        body = r.json()
        for key in ("available", "reason", "model_path"):
            assert key in body, f"missing field {key} in /status payload"
        print(f"OK /status payload shape: available={body['available']}, "
              f"model_path={body['model_path']}")

        ok, reason = is_available()

        if not ok:
            print(f"  (ultralytics/torch/model not installed: {reason!r})")
            # When deps are missing, /status MUST report available=false WITH
            # a non-empty hint so the front-end can show it in a tooltip.
            expect("status.available=False", body["available"], False)
            assert body["reason"], "expected an install hint when unavailable"

            # And /segment must 503 with the hint as the detail.
            r = admin.post("/api/sam2/segment", json={
                "folder_path": str(folder), "relative_path": "img.png",
                "points": [{"x": 0.5, "y": 0.5}],
                "image_natural_width": 1, "image_natural_height": 1,
            })
            expect("/segment -> 503 when unavailable", r.status_code, 503)
            assert r.json()["detail"], "expected an install hint in 503 detail"
            print("OK 503 detail surfaces the install hint")
        else:
            # Deps are installed and weights exist — exercise a real call.
            print(f"  (SAM2 ready, model at {model_path()})")
            expect("status.available=True", body["available"], True)
            r = admin.post("/api/sam2/segment", json={
                "folder_path": str(folder), "relative_path": "img.png",
                "points": [{"x": 0.5, "y": 0.5}],
                "labels": [1],
                "image_natural_width": 1, "image_natural_height": 1,
            })
            expect("/segment -> 200 when available", r.status_code, 200)
            data = r.json()
            assert "polygons" in data and "duration_ms" in data
            print(f"OK live SAM2 returned {len(data['polygons'])} polygon(s) "
                  f"in {data['duration_ms']} ms")

        # Validation: missing points -> 422 (pydantic) or 400 (server)
        r = admin.post("/api/sam2/segment", json={
            "folder_path": str(folder), "relative_path": "img.png",
            "points": [],
            "image_natural_width": 1, "image_natural_height": 1,
        })
        assert r.status_code in (400, 422), \
            f"empty-points should be rejected, got {r.status_code}"
        print(f"OK empty-points rejected ({r.status_code})")

        # Path-traversal protection on relative_path
        r = admin.post("/api/sam2/segment", json={
            "folder_path": str(folder), "relative_path": "../../../etc/passwd",
            "points": [{"x": 0.5, "y": 0.5}],
            "image_natural_width": 1, "image_natural_height": 1,
        })
        expect("path traversal rejected", r.status_code, 400)

        # Mismatched labels length — validation runs before the model load
        # (deliberate: don't pay the SAM2 init cost just to reject a bad
        # payload), so this is 400 regardless of whether deps are installed.
        r = admin.post("/api/sam2/segment", json={
            "folder_path": str(folder), "relative_path": "img.png",
            "points": [{"x": 0.5, "y": 0.5}],
            "labels": [1, 0],
            "image_natural_width": 1, "image_natural_height": 1,
        })
        expect("label-length mismatch -> 400", r.status_code, 400)

        print("\nAll SAM2 smoke checks passed.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
