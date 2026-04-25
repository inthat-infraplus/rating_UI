// dashboard.js — task card grid, filters, new-task modal.
//
// Bootstraps from #bootstrap-data (current user). Then fetches /api/tasks
// and renders cards. L1 sees a "+ New Task" button + a delete option per card;
// L2 sees only their own active tasks.
"use strict";

const bootstrap = JSON.parse(document.getElementById("bootstrap-data").textContent);
const ME = bootstrap.user;
const IS_L1 = ME.role === "L1";

const STATUS_LABELS = {
  draft:       "Draft",
  assigned:    "Assigned",
  in_progress: "In progress",
  submitted:   "Waiting QC",
  in_qc:       "In QC",
  returned:    "Returned",
  approved:    "Approved",
  exported:    "Exported",
};

// Filter chips per role. `match` is a (task) -> bool predicate.
const FILTERS_L1 = [
  { id: "all",        label: "All",          match: () => true },
  { id: "qc-queue",   label: "Waiting QC",   match: t => ["submitted", "in_qc"].includes(t.status), badge: true },
  { id: "in-progress",label: "In progress",  match: t => ["assigned", "in_progress", "returned"].includes(t.status) },
  { id: "approved",   label: "Approved",     match: t => ["approved", "exported"].includes(t.status) },
  { id: "mine",       label: "Mine",         match: t => t.created_by === ME.id || t.assigned_to === ME.id },
];
const FILTERS_L2 = [
  { id: "active",   label: "Assigned to me", match: t => ["assigned", "in_progress"].includes(t.status) },
  { id: "returned", label: "Returned",       match: t => t.status === "returned", badge: true },
  { id: "all",      label: "All my tasks",   match: () => true },
];
const FILTERS = IS_L1 ? FILTERS_L1 : FILTERS_L2;

// --- state ---
let allTasks = [];
let allUsers = [];          // L1 only — for assignee dropdown
let activeFilter = FILTERS[0].id;

// --- DOM helpers ---
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function showToast(message, kind = "info") {
  const el = $("#toast");
  el.textContent = message;
  el.dataset.kind = kind;
  el.classList.add("toast-show");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.remove("toast-show"), 3000);
}

async function fetchJson(url, opts = {}) {
  const res = await fetch(url, {
    credentials: "same-origin",
    headers: opts.body ? { "Content-Type": "application/json" } : {},
    ...opts,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const data = await res.json();
      msg = data.detail || msg;
    } catch (_) { /* ignore */ }
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

// --- render ---

function renderRoleVisibility() {
  // Hide L1-only elements for L2.
  $$(".role-l1-only").forEach((el) => {
    if (!IS_L1) el.style.display = "none";
  });
}

function renderFilters() {
  const bar = $("#filter-bar");
  bar.innerHTML = "";
  FILTERS.forEach((f) => {
    const count = allTasks.filter(f.match).length;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "filter-chip" + (activeFilter === f.id ? " active" : "");
    btn.dataset.filter = f.id;
    btn.innerHTML = `${f.label} <span class="filter-count">${count}</span>`;
    if (f.badge && count > 0) btn.classList.add("filter-chip-badge");
    btn.addEventListener("click", () => {
      activeFilter = f.id;
      renderFilters();
      renderGrid();
    });
    bar.appendChild(btn);
  });
}

function renderGrid() {
  const filter = FILTERS.find((f) => f.id === activeFilter) || FILTERS[0];
  const tasks = allTasks.filter(filter.match);

  const grid = $("#task-grid");
  grid.innerHTML = "";

  if (tasks.length === 0) {
    grid.style.display = "none";
    $("#task-empty").style.display = "";
    $("#task-empty-text").textContent =
      IS_L1
        ? (allTasks.length === 0
            ? "Click + New Task to create your first one."
            : "Nothing matches this filter — try another chip.")
        : "Nothing assigned to you yet. Ask your reviewer.";
    return;
  }
  grid.style.display = "";
  $("#task-empty").style.display = "none";

  for (const task of tasks) grid.appendChild(renderCard(task));
}

function renderCard(task) {
  const card = document.createElement("article");
  card.className = "task-card";
  card.tabIndex = 0;
  card.dataset.taskId = task.id;
  card.addEventListener("click", () => navigateToTask(task.id));
  card.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      navigateToTask(task.id);
    }
  });

  // Header: title + status pill
  const head = document.createElement("header");
  head.className = "task-card-head";
  const title = document.createElement("h3");
  title.className = "task-card-title";
  title.textContent = task.title;
  head.appendChild(title);
  head.appendChild(statusPill(task.status));
  card.appendChild(head);

  // Progress
  const total = task.total_images || 0;
  const reviewed = task.reviewed_count || 0;
  const pct = total > 0 ? Math.round((reviewed / total) * 100) : 0;

  const progress = document.createElement("div");
  progress.className = "task-card-progress";
  progress.innerHTML = `
    <span class="progress-text">${reviewed} / ${total}</span>
    <div class="progress progress-sm"><div class="progress-bar" style="width:${pct}%"></div></div>
  `;
  card.appendChild(progress);

  // Counts row
  const counts = document.createElement("div");
  counts.className = "task-card-counts";
  counts.innerHTML = `
    <span class="count-correct">${task.correct_count || 0} ✓</span>
    <span class="count-wrong">${task.wrong_count || 0} ✗</span>
    <span class="count-anno">${task.annotated_count || 0} ◆</span>
  `;
  card.appendChild(counts);

  // Footer: assignee, due, created
  const foot = document.createElement("footer");
  foot.className = "task-card-foot";

  const left = document.createElement("div");
  left.className = "task-card-foot-left";
  if (task.assignee_username) {
    left.innerHTML = `<span class="task-meta-pill">@${task.assignee_username}</span>`;
  } else {
    left.innerHTML = `<span class="task-meta-pill task-meta-muted">unassigned</span>`;
  }
  if (task.due_date) {
    left.innerHTML += ` <span class="task-meta-due">due ${task.due_date}</span>`;
  }

  const right = document.createElement("div");
  right.className = "task-card-foot-right";
  right.textContent = formatDate(task.created_at);

  foot.appendChild(left);
  foot.appendChild(right);
  card.appendChild(foot);

  // L1: ⋯ menu (Delete only for v1)
  if (IS_L1) {
    const menuWrap = document.createElement("div");
    menuWrap.className = "task-card-menu";
    menuWrap.innerHTML = `<button type="button" aria-label="Task actions">⋯</button>`;
    menuWrap.firstElementChild.addEventListener("click", (e) => {
      e.stopPropagation();
      openCardMenu(task, menuWrap);
    });
    card.appendChild(menuWrap);
  }

  return card;
}

function statusPill(status) {
  const span = document.createElement("span");
  span.className = `status-pill status-${status}`;
  span.textContent = STATUS_LABELS[status] || status;
  return span;
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function navigateToTask(taskId) {
  window.location.href = `/tasks/${taskId}`;
}

function openCardMenu(task, anchor) {
  // Close any existing menus
  $$(".card-menu-popup").forEach((m) => m.remove());

  const menu = document.createElement("div");
  menu.className = "card-menu-popup";
  menu.innerHTML = `
    <button type="button" data-action="open">Open</button>
    <button type="button" data-action="delete" class="menu-danger">Delete</button>
  `;
  menu.addEventListener("click", async (e) => {
    e.stopPropagation();
    const action = e.target.dataset.action;
    if (action === "open") navigateToTask(task.id);
    if (action === "delete") {
      if (!confirm(`Delete task "${task.title}"? This cannot be undone from the UI.`)) return;
      try {
        await fetchJson(`/api/tasks/${task.id}`, { method: "DELETE" });
        showToast("Task deleted.", "success");
        await loadTasks();
      } catch (err) {
        showToast(err.message || "Delete failed.", "error");
      }
    }
    menu.remove();
  });
  anchor.appendChild(menu);

  // Close on outside click
  setTimeout(() => {
    document.addEventListener(
      "click",
      function close(ev) {
        if (!menu.contains(ev.target)) {
          menu.remove();
          document.removeEventListener("click", close);
        }
      },
      { once: true },
    );
  }, 0);
}

// --- new task modal ---

function openNewTaskModal() {
  $("#new-task-modal").classList.remove("hidden");
  $("#new-task-error").style.display = "none";
  $("#new-task-form").reset();
  // Populate assignee dropdown
  const sel = $("#nt-assignee");
  sel.innerHTML = `<option value="">(unassigned — keep as draft)</option>`;
  allUsers
    .filter((u) => u.role === "L2")
    .forEach((u) => {
      const opt = document.createElement("option");
      opt.value = String(u.id);
      opt.textContent = `${u.display_name || u.username} (@${u.username})`;
      sel.appendChild(opt);
    });
  setTimeout(() => $("#nt-title").focus(), 50);
}

function closeNewTaskModal() {
  $("#new-task-modal").classList.add("hidden");
}

async function submitNewTask(ev) {
  ev.preventDefault();
  const form = ev.target;
  const data = Object.fromEntries(new FormData(form).entries());
  // Trim + drop empties so server-side optional fields stay null
  const payload = {};
  for (const [k, v] of Object.entries(data)) {
    const trimmed = (v || "").trim();
    if (trimmed !== "") payload[k] = trimmed;
  }
  if (payload.assigned_to) payload.assigned_to = parseInt(payload.assigned_to, 10);
  if (!payload.title) {
    showError("Title is required.");
    return;
  }

  try {
    const res = await fetchJson("/api/tasks", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    closeNewTaskModal();
    showToast(`Created "${res.task.title}".`, "success");
    await loadTasks();
  } catch (err) {
    showError(err.message || "Could not create task.");
  }
}

function showError(msg) {
  const el = $("#new-task-error");
  el.textContent = msg;
  el.style.display = "";
}

// --- data loading ---

async function loadTasks() {
  $("#dashboard-subtitle").textContent = "Loading tasks…";
  try {
    const { tasks } = await fetchJson("/api/tasks");
    allTasks = tasks;
    $("#dashboard-subtitle").textContent =
      tasks.length === 0
        ? (IS_L1 ? "No tasks yet — start by creating one." : "Nothing assigned to you yet.")
        : `${tasks.length} task${tasks.length === 1 ? "" : "s"} in your queue.`;
    renderFilters();
    renderGrid();
  } catch (err) {
    if (err.status === 401) {
      window.location.href = "/login";
      return;
    }
    $("#dashboard-subtitle").textContent = "Could not load tasks.";
    showToast(err.message, "error");
  }
}

async function loadUsers() {
  if (!IS_L1) return;
  try {
    const { users } = await fetchJson("/api/users");
    allUsers = users;
  } catch (err) {
    // Non-fatal — assignee dropdown will just be empty.
    console.warn("Could not load users:", err);
  }
}

// --- init ---

function init() {
  renderRoleVisibility();
  $("#new-task-btn")?.addEventListener("click", openNewTaskModal);
  $("#new-task-close")?.addEventListener("click", closeNewTaskModal);
  $("#new-task-cancel")?.addEventListener("click", closeNewTaskModal);
  $("#new-task-form")?.addEventListener("submit", submitNewTask);
  // Click backdrop to close
  $("#new-task-modal")?.addEventListener("click", (e) => {
    if (e.target.id === "new-task-modal") closeNewTaskModal();
  });
  // Esc to close
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("#new-task-modal").classList.contains("hidden")) {
      closeNewTaskModal();
    }
  });

  Promise.all([loadUsers(), loadTasks()]);
}

init();
