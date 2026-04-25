"""Phase 6 smoke test: admin user page endpoints.

Covers:
- GET /api/admin/users (L1 only, includes inactive + last_login_at)
- POST /api/admin/users (L1 only, creates user)
- PATCH /api/admin/users/{id} (role / display_name / is_active)
- POST /api/admin/users/{id}/reset-password
- Self-lockout protection (cannot demote / deactivate self)
- GET /admin/users HTML page (L1 only)

Run from repo root:  python _smoke_p6.py
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

    # 1) L1 list-all-users includes is_active + last_login_at
    r = admin.get("/api/admin/users")
    expect("L1 GET /api/admin/users", r.status_code, 200)
    users = r.json()["users"]
    assert len(users) >= 3, f"expected ≥3 seed users, got {len(users)}"
    sample = users[0]
    for key in ("id", "username", "display_name", "role", "is_active", "created_at", "last_login_at"):
        assert key in sample, f"missing field {key} in user payload"
    print(f"OK admin listing has all fields ({len(users)} users)")

    # 2) L2 forbidden from admin listing
    r = alice.get("/api/admin/users")
    expect("L2 GET /api/admin/users forbidden", r.status_code, 403)

    # 3) L1 can render admin HTML page
    r = admin.get("/admin/users")
    expect("L1 GET /admin/users page", r.status_code, 200)
    assert "Users" in r.text and "admin_users.js" in r.text, "admin page missing expected markup"
    print("OK admin page renders with admin_users.js")

    # 4) L2 cannot reach admin HTML page
    r = alice.get("/admin/users")
    expect("L2 GET /admin/users forbidden", r.status_code, 403)

    # 5) L1 creates a fresh test user
    test_username = "smoke_p6_user"
    # Clean up if still around from a previous run
    existing_id = next((u["id"] for u in users if u["username"] == test_username), None)
    if existing_id is not None:
        # PATCH to reactivate so we can re-use
        admin.patch(f"/api/admin/users/{existing_id}", json={"is_active": True, "role": "L2"})
        new_id = existing_id
        print(f"OK reusing existing test user id={new_id}")
    else:
        r = admin.post("/api/admin/users", json={
            "username": test_username,
            "password": "testpass123",
            "display_name": "Smoke P6",
            "role": "L2",
        })
        expect("L1 create new user", r.status_code, 201)
        new_user = r.json()["user"]
        assert new_user["is_active"] is True, "new user should be active"
        new_id = new_user["id"]

    # 6) PATCH role to L1
    r = admin.patch(f"/api/admin/users/{new_id}", json={"role": "L1"})
    expect("PATCH role L2->L1", r.status_code, 200)
    expect("role updated", r.json()["user"]["role"], "L1")

    # 7) PATCH display_name
    r = admin.patch(f"/api/admin/users/{new_id}", json={"display_name": "Renamed Person"})
    expect("PATCH display_name", r.status_code, 200)
    expect("display_name updated", r.json()["user"]["display_name"], "Renamed Person")

    # 8) PATCH is_active=False (deactivate)
    r = admin.patch(f"/api/admin/users/{new_id}", json={"is_active": False})
    expect("PATCH deactivate", r.status_code, 200)
    expect("is_active=False", r.json()["user"]["is_active"], False)

    # 9) Reset password
    r = admin.post(f"/api/admin/users/{new_id}/reset-password",
                   json={"new_password": "newpass456"})
    expect("POST reset-password", r.status_code, 200)
    expect("ok=True", r.json()["ok"], True)

    # 10) Reactivate so that the user can log in
    r = admin.patch(f"/api/admin/users/{new_id}", json={"is_active": True, "role": "L2"})
    expect("PATCH reactivate", r.status_code, 200)

    # 11) Verify the password actually changed by logging in with the new pw
    fresh = TestClient(app, follow_redirects=False)
    login(fresh, test_username, "newpass456")
    print("OK new password works for login")

    # 12) Self-lockout: admin cannot demote themselves
    me = admin.get("/api/me").json()
    r = admin.patch(f"/api/admin/users/{me['id']}", json={"role": "L2"})
    expect("self-demote rejected", r.status_code, 400)

    # 13) Self-lockout: admin cannot deactivate themselves
    r = admin.patch(f"/api/admin/users/{me['id']}", json={"is_active": False})
    expect("self-deactivate rejected", r.status_code, 400)

    # 14) L2 forbidden from PATCH and reset-password
    r = alice.patch(f"/api/admin/users/{new_id}", json={"role": "L1"})
    expect("L2 PATCH forbidden", r.status_code, 403)
    r = alice.post(f"/api/admin/users/{new_id}/reset-password",
                   json={"new_password": "x" * 8})
    expect("L2 reset-pw forbidden", r.status_code, 403)

    # 15) Validation: reject too-short passwords on reset
    r = admin.post(f"/api/admin/users/{new_id}/reset-password",
                   json={"new_password": "abc"})
    expect("short pw rejected", r.status_code, 422)

    # 16) Validation: 404 on unknown user
    r = admin.patch("/api/admin/users/999999", json={"role": "L1"})
    expect("PATCH unknown user 404", r.status_code, 404)
    r = admin.post("/api/admin/users/999999/reset-password",
                   json={"new_password": "abcdef"})
    expect("reset-pw unknown user 404", r.status_code, 404)

    print("\nAll P6 admin checks passed.")


if __name__ == "__main__":
    main()
