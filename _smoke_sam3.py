"""SAM3 endpoint smoke test.

Exercises the live SAM3 integration through FastAPI using the official source
repo codepath plus a local `models/sam3.pt` checkpoint.

Run from repo root:
    .\.venv\Scripts\python.exe _smoke_sam3.py
"""
from __future__ import annotations

import os
import shutil
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")


def login(client, username, password):
    response = client.post("/login", data={"username": username, "password": password, "next": "/"})
    assert response.status_code == 302, f"login failed for {username}"


def expect(label, got, want):
    ok = got == want
    print(f"{'OK' if ok else 'FAIL'} {label}: got {got!r}, want {want!r}")
    assert ok, label


def main():
    tmp = Path(tempfile.mkdtemp(prefix="sam3_smoke_"))
    repo_root = Path(__file__).resolve().parent
    model_dir = repo_root / "models"
    source_repo = repo_root / "sam3-git" / "official-sam3"

    try:
        os.environ["RATING_UI_DB"] = str(tmp / "smoke_rating_ui.db")
        os.environ["RATING_UI_SECRET_KEY"] = "sam3-smoke-secret"
        os.environ["RATING_UI_SAM3_MODEL"] = str(model_dir / "sam3.pt")
        os.environ["RATING_UI_SAM3_REPO"] = str(source_repo)

        from fastapi.testclient import TestClient
        from PIL import Image, ImageDraw

        from app.auth import hash_password
        from app.db import db_session, init_db
        from app.main import app
        from app.models_db import User, UserRole
        from app.sam3_service import is_available

        init_db()
        with db_session() as db:
            db.add(
                User(
                    username="admin",
                    password_hash=hash_password("adminpass"),
                    display_name="Admin",
                    role=UserRole.L1,
                )
            )

        folder = tmp / "preds"
        folder.mkdir()
        img_path = folder / "img.png"
        image = Image.new("RGB", (256, 256), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((60, 60, 196, 196), fill="black")
        image.save(img_path)

        ok, reason = is_available()
        assert ok, f"SAM3 should be available for this smoke test: {reason}"

        admin = TestClient(app, follow_redirects=False)
        login(admin, "admin", "adminpass")

        anon = TestClient(app, follow_redirects=False)
        response = anon.get("/api/sam3/status")
        expect("anon /api/sam3/status -> 401", response.status_code, 401)

        response = admin.get("/api/sam3/status")
        expect("/api/sam3/status -> 200", response.status_code, 200)
        status_payload = response.json()
        assert status_payload["available"] is True
        print(
            "OK SAM3 status:",
            f"device={status_payload.get('device')}",
            f"model_path={status_payload.get('model_path')}",
        )

        response = admin.post(
            "/api/sam3/segment",
            json={
                "folder_path": str(folder),
                "relative_path": "img.png",
                "points": [{"x": 0.5, "y": 0.5}],
                "labels": [1],
                "image_natural_width": 256,
                "image_natural_height": 256,
            },
        )
        expect("point /api/sam3/segment -> 200", response.status_code, 200)
        data = response.json()
        assert data["polygons"], "expected at least one polygon from point-prompt SAM3"
        print(
            "OK point prompt returned",
            f"{len(data['polygons'])} polygon(s) in {data['duration_ms']} ms on {data.get('device')}",
        )

        response = admin.post(
            "/api/sam3/segment",
            json={
                "folder_path": str(folder),
                "relative_path": "img.png",
                "points": [],
                "box": {"x1": 0.2, "y1": 0.2, "x2": 0.8, "y2": 0.8},
                "image_natural_width": 256,
                "image_natural_height": 256,
            },
        )
        expect("box /api/sam3/segment -> 200", response.status_code, 200)
        data = response.json()
        assert data["polygons"], "expected at least one polygon from box-prompt SAM3"
        print(
            "OK box prompt returned",
            f"{len(data['polygons'])} polygon(s) in {data['duration_ms']} ms on {data.get('device')}",
        )

        response = admin.get("/api/sam2/status")
        expect("legacy /api/sam2/status alias -> 200", response.status_code, 200)

        response = admin.post(
            "/api/sam2/segment",
            json={
                "folder_path": str(folder),
                "relative_path": "img.png",
                "points": [{"x": 0.5, "y": 0.5}],
                "labels": [1],
                "image_natural_width": 256,
                "image_natural_height": 256,
            },
        )
        expect("legacy /api/sam2/segment alias -> 200", response.status_code, 200)

        print("\nAll SAM3 smoke checks passed.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
