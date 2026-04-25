---
name: rating-ai
description: Project blueprint for the Prediction Rating UI (rating_UI) — FastAPI + vanilla JS app for rating road-surface AI predictions. Contains the v2 refactor plan (task-based + 2-level RBAC), current architecture map, data model, API surface, state machine, and phased rollout. ALWAYS load this skill when the user is working in the rating_UI repo, mentions "rating UI", "prediction rating", "annotator", "assigner/reviewer", "task dashboard", "QC workflow", or asks about refactoring the app toward a task-based / Label-Studio-style workflow. Use it to ground any code change, design discussion, or planning question in the agreed architecture instead of reinventing it.
---

# Rating UI — Project Blueprint (v2 plan)

This skill captures the **agreed implementation plan** for refactoring the Prediction Rating UI from a single-session tool into a task-based, role-based system. When the user asks for changes, ground your work in this blueprint — don't redesign from scratch unless the user explicitly says so.

---

## 1. What the app is (today)

A local FastAPI + vanilla JS app for rating AI predictions on road surface images. Current single-session flow:

1. Load a folder of prediction images
2. (Optional) Link `detailed_results.csv` → draws model bounding boxes
3. (Optional) Link XenomatiX `scale_profile.csv` → auto-calc polygon area (m²) / crack length (m)
4. Mark each image Correct / Wrong; draw correction polygons on Wrong
5. Export Updated CSV / ZIP (images + annotated + YOLO labels + classes.txt) / TXT

Key files: `app/main.py`, `app/review_store.py`, `app/models.py`, `templates/index.html`, `static/app.js`, `static/styles.css`, `RATING_TEAM_GUIDE.md`.

---

## 2. The v2 direction (agreed with user)

**Collapse the current web page into a "task detail" view. Landing page becomes a task dashboard (card grid, Label-Studio style). Add 2 user levels with strict RBAC.**

- **Level 1 — Assigner/Reviewer**: creates tasks, sets paths, assigns to L2, does QC, exports. Only L1 can export/save (data security).
- **Level 2 — Annotator**: opens assigned tasks, rates + draws polygons, submits for QC. Cannot export.

---

## 3. Data model (SQLite)

Chosen for zero-ops deployment, file-level backup, fits a 5–30 person team.

```
users(id, username, password_hash, display_name, role ENUM('L1','L2'),
      created_at, last_login_at)

tasks(id, title, description,
      folder_path, csv_path, scale_profile_path, target_folder_path,
      created_by FK, assigned_to FK NULLABLE,
      status ENUM('draft','assigned','in_progress','submitted',
                  'in_qc','returned','approved','exported'),
      due_date, created_at, updated_at,
      -- cached progress counters (updated on each review save)
      total_images, reviewed_count, correct_count, wrong_count, annotated_count)

task_events(id, task_id FK, actor FK,
            event_type ENUM('created','assigned','started','submitted',
                            'qc_started','returned','approved','exported','comment'),
            message, created_at,
            read_by_assigner BOOL, read_by_annotator BOOL)
```

Per-image decisions + polygons stay in the existing `.rating_session.json` inside each folder for v1 (avoid risky migration). Move into DB only if multi-annotator-on-same-folder becomes a real need.

---

## 4. Task state machine

```
draft ──(L1 set paths + assign)──▶ assigned
                                      │
                         (L2 opens)   ▼
                                 in_progress
                                      │
                      (L2 Submit for QC)
                                      ▼
                                  submitted ──(L1 opens QC)──▶ in_qc
                                                                 │
                                            (Return w/ comment)  │  (Approve)
                                                ▼                ▼
                                             returned        approved
                                                │                │
                                         (L2 resumes)      (L1 Export)
                                                ▼                ▼
                                           in_progress        exported
```

Visibility rules:
- **L2 sees**: tasks where `assigned_to = self` AND status ∈ {assigned, in_progress, returned}.
- **L1 sees**: all tasks, highlights `submitted` with a red badge (QC queue).

---

## 5. Backend changes

### New files
```
app/
├── auth.py          -- login/logout, session cookie, role guard decorator
├── db.py            -- SQLAlchemy engine, session, init
├── models_db.py     -- User, Task, TaskEvent ORM classes
├── task_service.py  -- CRUD + state transitions + permission enforcement
└── cli.py           -- `python -m app.cli create-user --role L1 --username admin`
```

### Endpoint plan

All endpoints require an authenticated session. Role enforcement is central (decorator), not per-handler.

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/api/auth/login` | any | login |
| POST | `/api/auth/logout` | any | logout |
| GET  | `/api/me` | any | current user |
| GET  | `/api/tasks` | any | list (server filters by role) |
| POST | `/api/tasks` | L1 | create |
| GET  | `/api/tasks/{id}` | any w/ access | detail |
| PATCH| `/api/tasks/{id}` | L1 | edit paths, title, etc. |
| POST | `/api/tasks/{id}/assign` | L1 | set `assigned_to` |
| POST | `/api/tasks/{id}/submit` | L2 (owner) | mark `submitted` |
| POST | `/api/tasks/{id}/return` | L1 | mark `returned` + comment |
| POST | `/api/tasks/{id}/approve` | L1 | mark `approved` |
| POST | `/api/tasks/{id}/events` | any w/ access | add comment |
| GET  | `/api/users` | L1 | assignee dropdown source |
| POST | `/api/admin/users` | L1 | create user |

### Gating existing endpoints

| Existing endpoint | Who may call |
|---|---|
| `/api/review`, `/api/annotations`, `/api/ui-state` | L1, L2 (if owner of task) |
| `/api/load-folder`, `/api/import-folder`, `/api/link-csv`, `/api/link-scale-profile`, `/api/session-config` | **L1 only** |
| `/api/export`, `/api/export-filenames`, `/api/export-updated-csv` | **L1 only** — data security |

Existing endpoints need a `task_id` arg (maps to folder_path internally) so permission can be checked.

---

## 6. Frontend structure

### Routing
```
/login
/                    -- dashboard (cards)
/tasks/new      (L1)
/tasks/:id           -- task detail (current UI, feature-gated)
/tasks/:id/edit (L1)
/admin/users    (L1)
```

### Landing / dashboard
Card grid styled like Label Studio Projects page:
- Title + status pill (🟨 assigned, 🔵 in_progress, 🔴 submitted, 🟢 approved, ⚪ draft)
- `reviewed / total` + mini progress bar
- Counts: ✓ correct — ✗ wrong — 🟣 annotated
- Assignee avatar + due date + created date
- (L1) `⋯` menu → Edit / Reassign / Delete, plus top-right `+ New Task`

Filter chips:
- L1: `All / Waiting QC / In Progress / Approved / Mine`
- L2: `Assigned to me / In progress / Returned`

### Task detail (= existing review UI)
- Setup panel (Steps 1–3, 5): **read-only for L2** (paths visible, inputs/Browse/Load hidden).
- Step 5 Export buttons: **hidden for L2**.
- Header adds **Submit for QC** (L2, enabled when progress = 100%).
- QC panel (L1) with `Approve` / `Return (with comment)` + comment thread from `task_events`.
- Breadcrumb: `← Back to tasks`.

### Files to touch
```
templates/
├── base.html         NEW -- layout, nav bar, user menu, role-gated links
├── login.html        NEW
├── dashboard.html    NEW -- card grid
├── task_detail.html  RENAME from index.html, add role gating
├── task_new.html     NEW
└── admin_users.html  NEW

static/
├── common.js         NEW -- auth fetch wrapper, current user, nav
├── dashboard.js      NEW
├── task.js           refactored from app.js (core review UI + submit/approve hooks)
├── admin.js          NEW
└── styles.css        add card grid + `.role-l1-only` / `.role-l2-only` visibility
```

---

## 7. Notifications (simple polling)

- Nav bar shows `🔔 N`. For L1 → count of `submitted` tasks. For L2 → count of `returned` tasks.
- Dashboard polls `GET /api/me/notifications` every 30s.
- Optional v1.1: SMTP email via env (`SMTP_HOST`, etc.). No WebSocket/SSE in v1 — team is small.

---

## 8. Phased rollout

| Phase | Scope | Est. | Status |
|---|---|---|---|
| P1 | DB + auth + seed CLI + `/login` | 0.5d | ✅ done |
| P2 | Task CRUD API + permission guards | 1d | ✅ done (`_smoke_p2.py`) |
| P3 | Dashboard landing page (cards) | 1d | ✅ done |
| P4 | Refactor review UI → task detail (role-gate + hide L2 exports) | 1d | ✅ done |
| P5 | Submit/QC workflow + comments + notification badge | 0.5d | ✅ done — counter sync via `task_service.sync_progress_for_folder` |
| P6 | Admin user page + polish + docs update | 0.5d | ✅ done (`_smoke_p6.py`) |
| **Total** | | **~4.5d** | **All phases shipped on `infallible-gould` worktree.** |

Each phase ends testable end-to-end. Build on a feature branch; single merge when all phases pass.

**Smoke tests at repo root**: `_smoke_p2.py` (task CRUD + RBAC + state machine), `_smoke_p6.py` (admin user endpoints + self-lockout). Run with `python _smoke_pN.py` after the dev server's seed users (`admin/adminpass`, `alice/alicepass`, `bob/bobpass`) are present.

---

## 9. Open decisions (ask user before coding each phase)

1. **Migration**: clean start (recommended) vs. auto-import old `.rating_session.json` folders as draft tasks.
2. **Assignee cardinality**: one L2 per task (recommended v1) vs. many.
3. **Multi-L1**: who reviews? Default: creator is reviewer, reassignable.
4. **Post-approve lock**: lock annotations after approve; reopen sends back to `returned`.
5. **Email notifications**: skip in v1 (recommended) or include.
6. **Delete semantics**: soft-delete recommended.
7. **Password policy**: min length, force-rotate on first login?

---

## 10. Risks / constraints

- **Local-first path visibility**: server-side paths (`D:\...`) only resolve on the host machine. If deploying for a distributed team, either everyone RDP/SSH into the same host, or switch to uploads-only (drop path inputs). Keep this in mind when any L2 says "path not found".
- **Breaking change**: all existing endpoints get auth + task_id wiring simultaneously. Do NOT ship partial — frontend and backend must update together on the feature branch.
- **Session JSON concurrency**: if two users ever open the same folder-backed task, last-write-wins. Acceptable for 1:1 assignment; revisit if moving to multi-annotator.
- **Windows paths**: keep using the existing `_fix_path_input()` and JS `normalizePath()` helpers — don't regress the `C\path` → `C:\path` fixups.

---

## 11. Conventions to preserve (don't break these)

- **Units in CSV/XLSX exports**: use ASCII `m^2` (not `m²`) + `utf-8-sig` BOM. The UI converts `m^2` → `m²` for display only.
- **Polygon storage**: normalized coords (0–1) + class_label + optional `value`/`unit` from scale profile.
- **YOLO segmentation export**: `class_id x1 y1 ... xn yn` normalized. Class IDs fixed: alligator crack=0, crack=1, patching=2, pothole=3, pavement=4.
- **Annotated ZIP structure**: `images/`, `annotated/`, `labels/`, `classes.txt`, `manifest.json`, `manifest.csv`.
- **Workflow stepper**: explicit `.wf-line` divs between steps (pseudo-elements don't flex).
- **Bbox toggle** defaults OFF.
- **Keyboard shortcuts**: `C`/`W`/`U` decide, `A`/`←` prev, `D`/`→` next, `P` draw polygon, `Esc` cancel. Disabled while typing in inputs.

---

## 12. When working on this project

Before writing code, check:
1. Does the change fit §6 (frontend) or §5 (backend) as scoped? If not, call out the deviation.
2. Does it respect §11 conventions?
3. Which phase (§8) does it belong to? If the user is asking mid-plan, confirm phase scope before sprawling.
4. Does it need one of the §9 decisions resolved first? Ask, don't guess.
