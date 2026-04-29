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

import os
import shutil
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")


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
        os.environ["RATING_UI_DB"] = str(tmp / "smoke_rating_ui.db")
        os.environ["RATING_UI_SECRET_KEY"] = "smoke-test-secret"

        from fastapi.testclient import TestClient

        from app.auth import hash_password
        from app.db import db_session, init_db
        from app.main import app
        from app.models_db import User, UserRole
        from app.sam2_service import is_available, model_path
        from PIL import Image, ImageDraw

        init_db()
        with db_session() as db:
            admin = User(
                username="admin",
                password_hash=hash_password("adminpass"),
                display_name="Admin",
                role=UserRole.L1,
            )
            db.add(admin)

        folder = tmp / "preds"
        folder.mkdir()
        img_path = folder / "img.png"
        image = Image.new("RGB", (256, 256), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((60, 60, 196, 196), fill="black")
        image.save(img_path)

        admin = TestClient(app, follow_redirects=False)
        login(admin, "admin", "adminpass")

        anon = TestClient(app, follow_redirects=False)

        # Auth gating
        r = anon.get("/api/sam2/status")
        expect("anon /status -> 401", r.status_code, 401)
        r = anon.post("/api/sam2/segment", json={
            "folder_path": str(folder), "relative_path": "img.png",
            "points": [{"x": 0.5, "y": 0.5}],
            "image_natural_width": 256, "image_natural_height": 256,
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
                "image_natural_width": 256, "image_natural_height": 256,
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
                "image_natural_width": 256, "image_natural_height": 256,
            })
            expect("/segment -> 200 when available", r.status_code, 200)
            data = r.json()
            assert "polygons" in data and "duration_ms" in data
            assert data["polygons"], "expected at least one polygon from live SAM2"
            print(f"OK live SAM2 returned {len(data['polygons'])} polygon(s) "
                  f"in {data['duration_ms']} ms")

        # Validation: missing points -> 422 (pydantic) or 400 (server)
        r = admin.post("/api/sam2/segment", json={
            "folder_path": str(folder), "relative_path": "img.png",
            "points": [],
            "image_natural_width": 256, "image_natural_height": 256,
        })
        assert r.status_code in (400, 422), \
            f"empty prompts should be rejected, got {r.status_code}"
        print(f"OK empty prompts rejected ({r.status_code})")

        # Box-only prompt should also work when SAM2 is available.
        if ok:
            r = admin.post("/api/sam2/segment", json={
                "folder_path": str(folder), "relative_path": "img.png",
                "points": [],
                "box": {"x1": 0.2, "y1": 0.2, "x2": 0.8, "y2": 0.8},
                "image_natural_width": 256, "image_natural_height": 256,
            })
            expect("box-only /segment -> 200 when available", r.status_code, 200)
            data = r.json()
            assert data["polygons"], "expected at least one polygon from box-prompt SAM2"
            print(f"OK box-prompt SAM2 returned {len(data['polygons'])} polygon(s)")

        # Path-traversal protection on relative_path
        r = admin.post("/api/sam2/segment", json={
            "folder_path": str(folder), "relative_path": "../../../etc/passwd",
            "points": [{"x": 0.5, "y": 0.5}],
            "image_natural_width": 256, "image_natural_height": 256,
        })
        expect("path traversal rejected", r.status_code, 400)

        # Mismatched labels length — validation runs before the model load
        # (deliberate: don't pay the SAM2 init cost just to reject a bad
        # payload), so this is 400 regardless of whether deps are installed.
        r = admin.post("/api/sam2/segment", json={
            "folder_path": str(folder), "relative_path": "img.png",
            "points": [{"x": 0.5, "y": 0.5}],
            "labels": [1, 0],
            "image_natural_width": 256, "image_natural_height": 256,
        })
        expect("label-length mismatch -> 400", r.status_code, 400)

        print("\nAll SAM2 smoke checks passed.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
