"""End-to-end smoke test covering the full system workflow.

Complements _smoke_p2.py (task CRUD/RBAC) and _smoke_p6.py (admin endpoints).
This one covers the gaps:
- HTML page renders + auth gating
- Login success/failure + /api/me + /healthz
- /api/tasks/{id}/start  (assigned -> in_progress)
- Image review pipeline through /api/review with counter sync verification
- Polygon annotations through /api/annotations with annotated_count sync
- TXT and ZIP exports (the two L1-only data-out endpoints)
- /api/calculate-area without a scale profile (graceful 400)
- Comments (events) listing for both roles

Creates a real tempdir of tiny PNG fixtures so the review_store has something
to scan. Does NOT touch the user's working DB — uses the seeded admin/alice/bob.

Run from repo root:  python _smoke_e2e.py
"""
from __future__ import annotations

import shutil
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient

from app.main import app


# Smallest valid PNG: 1x1 transparent pixel, 67 bytes.
_PNG_1x1 = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
    "0000000D49444154789C6300010000000500010D0A2DB40000000049454E44AE426082"
)


def make_image_folder(parent: Path, n: int = 3) -> Path:
    folder = parent / "preds"
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (folder / f"img_{i:03d}.png").write_bytes(_PNG_1x1)
    return folder


def login(client, username, password):
    r = client.post("/login", data={"username": username, "password": password, "next": "/"})
    assert r.status_code == 302, f"login failed for {username}: {r.status_code} {r.text}"


def expect(label, got, want):
    ok = got == want
    print(f"{'OK' if ok else 'FAIL'} {label}: got {got!r}, want {want!r}")
    assert ok, label


def expect_in(label, needle, haystack):
    ok = needle in haystack
    print(f"{'OK' if ok else 'FAIL'} {label}: {needle!r} in response")
    assert ok, label


def main():
    tmp = Path(tempfile.mkdtemp(prefix="ratingui_e2e_"))
    pred_folder = make_image_folder(tmp / "src", n=3)
    target_folder = make_image_folder(tmp / "dst", n=3)

    try:
        # ── Block 1: anonymous access ──────────────────────────────────────
        anon = TestClient(app, follow_redirects=False)
        r = anon.get("/")
        expect("anon GET / -> 302 to /login", r.status_code, 302)
        assert "/login" in r.headers.get("location", ""), "should redirect to /login"

        r = anon.get("/admin/users")
        expect("anon GET /admin/users -> 302", r.status_code, 302)

        r = anon.get("/tasks/1")
        expect("anon GET /tasks/1 -> 302", r.status_code, 302)

        r = anon.get("/healthz")
        expect("healthz public", r.status_code, 200)
        expect("healthz body", r.json()["status"], "ok")

        r = anon.post("/login", data={"username": "admin", "password": "wrong", "next": "/"})
        expect("bad password -> 401", r.status_code, 401)
        expect_in("login error message", "Invalid", r.text)

        # ── Block 2: authenticated sessions for all three roles ───────────
        admin = TestClient(app, follow_redirects=False)
        login(admin, "admin", "adminpass")
        alice = TestClient(app, follow_redirects=False)
        login(alice, "alice", "alicepass")
        bob = TestClient(app, follow_redirects=False)
        login(bob, "bob", "bobpass")

        r = admin.get("/api/me")
        expect("admin /api/me", r.status_code, 200)
        expect("admin role", r.json()["role"], "L1")

        r = alice.get("/api/me")
        expect("alice role", r.json()["role"], "L2")

        # ── Block 3: HTML page renders ────────────────────────────────────
        r = admin.get("/")
        expect("admin GET / 200", r.status_code, 200)
        expect_in("dashboard renders bootstrap-data", "bootstrap-data", r.text)
        expect_in("dashboard shows L1 nav admin link", "/admin/users", r.text)

        r = alice.get("/")
        expect("alice GET / 200", r.status_code, 200)
        # L2 should NOT see the admin link rendered server-side
        assert "href=\"/admin/users\"" not in r.text, \
            "L2 dashboard should not render admin link"
        print("OK L2 dashboard hides /admin/users link")

        r = admin.get("/admin/users")
        expect("admin GET /admin/users 200", r.status_code, 200)
        expect_in("admin page loads admin_users.js", "admin_users.js", r.text)

        r = alice.get("/admin/users")
        expect("alice GET /admin/users -> 403", r.status_code, 403)

        # ── Block 4: full task lifecycle with real folders ────────────────
        # 4a. L1 creates task with folder_path pointing at tempdir
        r = admin.post("/api/tasks", json={
            "title": "E2E test batch",
            "description": "Smoke test fixture — auto-created",
            "folder_path": str(pred_folder),
            "target_folder_path": str(target_folder),
        })
        expect("create task with folder", r.status_code, 201)
        task = r.json()["task"]
        task_id = task["id"]
        expect("status=draft", task["status"], "draft")

        # 4b. Assign to alice
        alice_id = next(
            u["id"] for u in admin.get("/api/users").json()["users"]
            if u["username"] == "alice"
        )
        r = admin.post(f"/api/tasks/{task_id}/assign", json={"assigned_to": alice_id})
        expect("assign to alice", r.status_code, 200)
        expect("status=assigned after assign", r.json()["task"]["status"], "assigned")

        # 4c. Bob cannot view; alice can render the task page
        r = bob.get(f"/api/tasks/{task_id}")
        expect("bob view forbidden", r.status_code, 403)

        r = alice.get(f"/tasks/{task_id}")
        expect("alice GET /tasks/{id} HTML 200", r.status_code, 200)
        expect_in("task page injects task-bootstrap-data",
                  "task-bootstrap-data", r.text)

        # 4d. /start endpoint flips assigned -> in_progress
        r = alice.post(f"/api/tasks/{task_id}/start", json={})
        expect("alice /start", r.status_code, 200)
        expect("status=in_progress after /start",
               r.json()["task"]["status"], "in_progress")

        # 4e. Alice loads the folder via the review_store endpoint
        r = alice.post("/api/load-folder", json={"folder_path": str(pred_folder)})
        expect("load-folder", r.status_code, 200)
        session = r.json()["session"]
        images = session.get("images", [])
        expect("3 images discovered", len(images), 3)

        # 4f. Review the images: 2 correct, 1 wrong
        decisions = ["correct", "correct", "wrong"]
        for img, decision in zip(images, decisions):
            r = alice.post("/api/review", json={
                "folder_path": str(pred_folder),
                "relative_path": img["relative_path"],
                "decision": decision,
            })
            expect(f"review {img['relative_path']}={decision}", r.status_code, 200)

        # 4g. Verify counter sync pushed into Task row
        r = alice.get(f"/api/tasks/{task_id}")
        td = r.json()["task"]
        expect("synced total_images", td["total_images"], 3)
        expect("synced reviewed_count", td["reviewed_count"], 3)
        expect("synced correct_count", td["correct_count"], 2)
        expect("synced wrong_count",   td["wrong_count"], 1)

        # 4h. Save a polygon annotation on the wrong image
        wrong_img = images[2]["relative_path"]
        r = alice.post("/api/annotations", json={
            "folder_path": str(pred_folder),
            "relative_path": wrong_img,
            "polygons": [{
                "id": "poly-1",
                "class_label": "pothole",
                "points": [
                    {"x": 0.1, "y": 0.1},
                    {"x": 0.9, "y": 0.1},
                    {"x": 0.9, "y": 0.9},
                    {"x": 0.1, "y": 0.9},
                ],
                "value": None,
                "unit": "",
            }],
            "image_natural_width": 1,
            "image_natural_height": 1,
        })
        expect("save annotation", r.status_code, 200)

        r = alice.get(f"/api/tasks/{task_id}")
        expect("synced annotated_count after polygon",
               r.json()["task"]["annotated_count"], 1)

        # 4i. /api/calculate-area without scale profile -> 400
        r = alice.post("/api/calculate-area", json={
            "folder_path": str(pred_folder),
            "class_label": "pothole",
            "points": [
                {"x": 0.1, "y": 0.1},
                {"x": 0.9, "y": 0.1},
                {"x": 0.9, "y": 0.9},
            ],
            "image_natural_width": 1,
            "image_natural_height": 1,
        })
        expect("calculate-area without scale profile -> 400", r.status_code, 400)

        # 4j. /api/image returns a real file
        r = alice.get("/api/image", params={
            "folder_path": str(pred_folder),
            "relative_path": images[0]["relative_path"],
        })
        expect("GET /api/image", r.status_code, 200)
        assert r.content.startswith(b"\x89PNG"), "should return PNG bytes"
        print("OK /api/image streams PNG bytes")

        # 4k. Submit -> L1 returns with comment -> alice resubmits -> L1 approves
        r = alice.post(f"/api/tasks/{task_id}/submit", json={})
        expect("alice submit", r.status_code, 200)
        expect("status=submitted", r.json()["task"]["status"], "submitted")

        r = admin.post(f"/api/tasks/{task_id}/return",
                       json={"message": "please redo last polygon"})
        expect("L1 return with comment", r.status_code, 200)
        expect("status=returned", r.json()["task"]["status"], "returned")

        # /start should also work on returned (returned -> in_progress)
        r = alice.post(f"/api/tasks/{task_id}/start", json={})
        expect("alice /start after return", r.status_code, 200)
        expect("status=in_progress after restart",
               r.json()["task"]["status"], "in_progress")

        r = alice.post(f"/api/tasks/{task_id}/submit", json={})
        expect("alice resubmit", r.status_code, 200)

        r = admin.post(f"/api/tasks/{task_id}/approve", json={})
        expect("L1 approve", r.status_code, 200)
        expect("status=approved", r.json()["task"]["status"], "approved")

        # ── Block 5: exports (L1 only, after approval) ────────────────────
        # TXT export — only needs wrong-marked images, no target folder needed.
        r = admin.post("/api/export-filenames", json={"folder_path": str(pred_folder)})
        expect("L1 export TXT", r.status_code, 200)
        body = r.text
        # The wrong-marked file should appear in the TXT
        expect_in("TXT contains wrong image", "img_002.png", body)

        # ZIP export needs target_folder_path bound to the review_store session.
        # The Task carries it but ReviewStore reads its own JSON state, so the L1
        # binds it via /api/session-config first (mirrors what the UI does when
        # the operator sets the target path on the task detail page).
        r = admin.post("/api/session-config", json={
            "folder_path": str(pred_folder),
            "target_folder_path": str(target_folder),
        })
        expect("bind target folder to session", r.status_code, 200)

        r = admin.post("/api/export", json={"folder_path": str(pred_folder)})
        expect("L1 export ZIP", r.status_code, 200)
        assert r.headers.get("content-type", "").startswith("application/zip"), \
            "expected zip content-type"
        assert len(r.content) > 100, "zip seems too small"
        print(f"OK ZIP export delivered ({len(r.content)} bytes)")

        # CSV export should still work even though no CSV was linked — it just
        # returns an empty/header-only file. Accept either 200 or 400.
        r = admin.post("/api/export-updated-csv", json={"folder_path": str(pred_folder)})
        assert r.status_code in (200, 400), \
            f"export-updated-csv unexpected status {r.status_code}"
        print(f"OK export-updated-csv responded ({r.status_code})")

        # ── Block 6: events / comments for both roles ─────────────────────
        r = alice.post(f"/api/tasks/{task_id}/events",
                       json={"message": "all polygons fixed"})
        expect("alice add comment", r.status_code, 201)

        r = admin.post(f"/api/tasks/{task_id}/events",
                       json={"message": "looks good — approved."})
        expect("admin add comment", r.status_code, 201)

        r = alice.get(f"/api/tasks/{task_id}/events")
        events = r.json()["events"]
        types = {e["event_type"] for e in events}
        for needed in ("submitted", "returned", "approved", "comment"):
            assert needed in types, f"event type {needed!r} missing from events log"
        print(f"OK events log has all expected types ({len(events)} events)")

        # ── Block 7: cleanup soft-delete + verify gone from listings ──────
        r = admin.delete(f"/api/tasks/{task_id}")
        expect("admin soft-delete", r.status_code, 200)

        r = admin.get(f"/api/tasks/{task_id}")
        expect("get after delete -> 404", r.status_code, 404)

        # Alice's task list should no longer include it
        r = alice.get("/api/tasks")
        ids = [t["id"] for t in r.json()["tasks"]]
        assert task_id not in ids, "soft-deleted task should disappear from listings"
        print("OK soft-deleted task hidden from list")

        # ── Block 8: logout invalidates session ───────────────────────────
        r = alice.post("/logout")
        expect("alice logout -> 302", r.status_code, 302)
        r = alice.get("/api/me")
        expect("after logout /api/me -> 401", r.status_code, 401)

        print("\nAll E2E checks passed.")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
