"""Phase 2 smoke test: task CRUD + state machine + RBAC.

Run from repo root:  python _smoke_p2.py
Deletes itself? No — kept around so it can be re-run after schema changes.
"""
from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient

from app.main import app


def login(client, username, password):
    r = client.post("/login", data={"username": username, "password": password, "next": "/"})
    assert r.status_code == 302, f"login failed for {username}: {r.status_code}"


def expect(label, got, want):
    ok = got == want
    print(f"{'OK' if ok else 'FAIL'} {label}: got {got}, want {want}")
    assert ok, label


def main():
    admin = TestClient(app, follow_redirects=False)
    login(admin, "admin", "adminpass")

    alice = TestClient(app, follow_redirects=False)
    login(alice, "alice", "alicepass")

    bob = TestClient(app, follow_redirects=False)
    login(bob, "bob", "bobpass")

    # 1) L1 lists users → sees alice + bob (active L2s) + admin
    r = admin.get("/api/users")
    expect("L1 GET /api/users", r.status_code, 200)
    usernames = sorted(u["username"] for u in r.json()["users"])
    assert "alice" in usernames and "bob" in usernames

    # 2) L2 cannot list users
    r = alice.get("/api/users")
    expect("L2 GET /api/users forbidden", r.status_code, 403)

    # 3) L2 cannot create task
    r = alice.post("/api/tasks", json={"title": "x"})
    expect("L2 POST /api/tasks forbidden", r.status_code, 403)

    # 4) L1 creates task as draft (no assignee)
    r = admin.post("/api/tasks", json={"title": "Batch 20250509", "description": "first batch"})
    expect("L1 create draft", r.status_code, 201)
    draft = r.json()["task"]
    expect("status=draft", draft["status"], "draft")

    # 5) L1 patches paths
    r = admin.patch(f"/api/tasks/{draft['id']}", json={"folder_path": "C:/data/preds"})
    expect("PATCH paths", r.status_code, 200)
    expect("path saved", r.json()["task"]["folder_path"], "C:/data/preds")

    # 6) L1 assigns to alice (id 2)
    alice_id = next(u["id"] for u in admin.get("/api/users").json()["users"] if u["username"] == "alice")
    r = admin.post(f"/api/tasks/{draft['id']}/assign", json={"assigned_to": alice_id})
    expect("assign", r.status_code, 200)
    expect("status=assigned", r.json()["task"]["status"], "assigned")

    # 7) Bob (other L2) cannot view alice's task
    r = bob.get(f"/api/tasks/{draft['id']}")
    expect("bob view alice task", r.status_code, 403)

    # 8) Alice can view her assigned task
    r = alice.get(f"/api/tasks/{draft['id']}")
    expect("alice view her task", r.status_code, 200)

    # 9) Alice listing → sees the task
    r = alice.get("/api/tasks")
    expect("alice list", r.status_code, 200)
    expect("alice sees 1 task", len(r.json()["tasks"]), 1)

    # 10) Bob listing → empty
    r = bob.get("/api/tasks")
    expect("bob list empty", len(r.json()["tasks"]), 0)

    # 11) Alice cannot approve
    r = alice.post(f"/api/tasks/{draft['id']}/approve")
    expect("alice approve forbidden", r.status_code, 403)

    # 12) Alice cannot submit assigned task without going through in_progress... actually allowed
    # Let's test submit from assigned (allowed): then return → resubmit → approve.
    r = alice.post(f"/api/tasks/{draft['id']}/submit")
    expect("alice submit", r.status_code, 200)
    expect("status=submitted", r.json()["task"]["status"], "submitted")

    # 13) L1 returns with comment
    r = admin.post(
        f"/api/tasks/{draft['id']}/return",
        json={"message": "please redo image #3"},
    )
    expect("L1 return", r.status_code, 200)
    expect("status=returned", r.json()["task"]["status"], "returned")

    # 14) Alice resubmits
    r = alice.post(f"/api/tasks/{draft['id']}/submit")
    expect("alice resubmit", r.status_code, 200)
    expect("status=submitted again", r.json()["task"]["status"], "submitted")

    # 15) L1 approves
    r = admin.post(f"/api/tasks/{draft['id']}/approve")
    expect("L1 approve", r.status_code, 200)
    expect("status=approved", r.json()["task"]["status"], "approved")

    # 16) L1 cannot edit paths after approve
    r = admin.patch(f"/api/tasks/{draft['id']}", json={"folder_path": "C:/x"})
    expect("PATCH after approve blocked", r.status_code, 409)

    # 17) Alice cannot submit again after approve
    r = alice.post(f"/api/tasks/{draft['id']}/submit")
    expect("alice submit after approve blocked", r.status_code, 409)

    # 18) Comments — alice posts, admin reads via events list
    r = alice.post(
        f"/api/tasks/{draft['id']}/events",
        json={"message": "thanks for the review"},
    )
    expect("alice comment", r.status_code, 201)

    r = admin.get(f"/api/tasks/{draft['id']}/events")
    expect("admin events list", r.status_code, 200)
    types = [e["event_type"] for e in r.json()["events"]]
    assert "comment" in types and "approved" in types and "submitted" in types

    # 19) Soft delete
    r = admin.delete(f"/api/tasks/{draft['id']}")
    expect("admin delete", r.status_code, 200)

    r = admin.get(f"/api/tasks/{draft['id']}")
    expect("get after delete", r.status_code, 404)

    # 20) Alice cannot create user
    r = alice.post("/api/admin/users", json={
        "username": "rogue", "password": "secret123", "role": "L2",
    })
    expect("L2 create user forbidden", r.status_code, 403)

    # 21) L1 creates new user
    r = admin.post("/api/admin/users", json={
        "username": "carol", "password": "carolpass", "display_name": "Carol", "role": "L2",
    })
    expect("L1 create user", r.status_code, 201)

    # 22) Duplicate username → 409
    r = admin.post("/api/admin/users", json={
        "username": "carol", "password": "x", "role": "L2",
    })
    # Pydantic min_length on password is 6 so this would 422 instead. Use valid pw to test 409:
    if r.status_code == 422:
        r = admin.post("/api/admin/users", json={
            "username": "carol", "password": "another", "role": "L2",
        })
    expect("duplicate username", r.status_code, 409)

    print("\nAll P2 smoke checks PASSED.")


if __name__ == "__main__":
    main()
