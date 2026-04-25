// admin_users.js — L1 admin page: list users, create user, toggle role / active,
// reset password.
//
// Bootstraps from #bootstrap-data (the current L1 user). All actions hit the
// /api/admin/users/* endpoints. Self-actions (demote / deactivate) are blocked
// server-side; we additionally hide those buttons client-side for clarity.
"use strict";

const bootstrap = JSON.parse(document.getElementById("bootstrap-data").textContent);
const ME = bootstrap.user;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

// --- state ---
let allUsers = [];
let resetTargetId = null;

// --- helpers ---

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

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch (_) {
    return iso;
  }
}

// --- render ---

function renderSubtitle() {
  const n = allUsers.length;
  const active = allUsers.filter(u => u.is_active).length;
  $("#users-subtitle").textContent =
    `${n} user${n === 1 ? "" : "s"} · ${active} active`;
}

function renderTable() {
  const tbody = $("#users-tbody");
  tbody.innerHTML = "";

  if (allUsers.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="6" class="users-empty">No users yet.</td>`;
    tbody.appendChild(tr);
    return;
  }

  for (const u of allUsers) {
    const tr = document.createElement("tr");
    tr.dataset.userId = String(u.id);
    if (!u.is_active) tr.classList.add("user-row-inactive");

    const isMe = u.id === ME.id;

    tr.innerHTML = `
      <td class="user-username">
        ${escapeHtml(u.username)}
        ${isMe ? '<span class="user-self-badge">you</span>' : ""}
      </td>
      <td>${escapeHtml(u.display_name || "")}</td>
      <td>
        <select class="form-select form-select-sm user-role-select"
                ${isMe ? "disabled title='Cannot change your own role'" : ""}>
          <option value="L1" ${u.role === "L1" ? "selected" : ""}>L1</option>
          <option value="L2" ${u.role === "L2" ? "selected" : ""}>L2</option>
        </select>
      </td>
      <td>
        <span class="user-status-pill ${u.is_active ? 'active' : 'inactive'}">
          ${u.is_active ? "Active" : "Inactive"}
        </span>
      </td>
      <td class="user-last-login">${fmtDate(u.last_login_at)}</td>
      <td class="user-actions">
        <button class="btn btn-sm btn-outline-secondary user-pw-btn" type="button">
          Reset password
        </button>
        <button class="btn btn-sm ${u.is_active ? 'btn-outline-danger' : 'btn-outline-success'} user-toggle-btn"
                type="button" ${isMe ? "disabled title='Cannot deactivate yourself'" : ""}>
          ${u.is_active ? "Deactivate" : "Reactivate"}
        </button>
      </td>
    `;

    // Wire row actions
    const roleSel = tr.querySelector(".user-role-select");
    if (roleSel && !isMe) {
      roleSel.addEventListener("change", () => onChangeRole(u.id, roleSel.value, roleSel));
    }
    tr.querySelector(".user-pw-btn").addEventListener("click", () => openResetPwModal(u));
    const toggleBtn = tr.querySelector(".user-toggle-btn");
    if (toggleBtn && !isMe) {
      toggleBtn.addEventListener("click", () => onToggleActive(u.id, !u.is_active, toggleBtn));
    }

    tbody.appendChild(tr);
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// --- API ---

async function loadUsers() {
  try {
    const data = await fetchJson("/api/admin/users");
    allUsers = data.users || [];
    renderSubtitle();
    renderTable();
  } catch (err) {
    showToast(`Failed to load users: ${err.message}`, "error");
  }
}

async function onChangeRole(userId, newRole, selectEl) {
  const prev = allUsers.find(u => u.id === userId)?.role;
  selectEl.disabled = true;
  try {
    await fetchJson(`/api/admin/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({ role: newRole }),
    });
    showToast(`Role updated to ${newRole}`, "success");
    await loadUsers();
  } catch (err) {
    showToast(err.message, "error");
    if (prev) selectEl.value = prev;
  } finally {
    selectEl.disabled = false;
  }
}

async function onToggleActive(userId, makeActive, btn) {
  btn.disabled = true;
  try {
    await fetchJson(`/api/admin/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: makeActive }),
    });
    showToast(makeActive ? "User reactivated" : "User deactivated", "success");
    await loadUsers();
  } catch (err) {
    showToast(err.message, "error");
    btn.disabled = false;
  }
}

// --- New-user modal ---

function openNewUserModal() {
  $("#new-user-error").style.display = "none";
  $("#new-user-form").reset();
  $("#new-user-modal").classList.remove("hidden");
  setTimeout(() => $("#nu-username").focus(), 50);
}

function closeNewUserModal() {
  $("#new-user-modal").classList.add("hidden");
}

async function onSubmitNewUser(ev) {
  ev.preventDefault();
  const errBox = $("#new-user-error");
  errBox.style.display = "none";

  const payload = {
    username: $("#nu-username").value.trim(),
    password: $("#nu-password").value,
    display_name: $("#nu-display").value.trim(),
    role: $("#nu-role").value,
  };

  if (payload.username.length < 2 || payload.password.length < 6) {
    errBox.textContent = "Username must be ≥ 2 chars and password ≥ 6 chars.";
    errBox.style.display = "block";
    return;
  }

  const submitBtn = $("#new-user-submit");
  submitBtn.disabled = true;
  try {
    await fetchJson("/api/admin/users", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    closeNewUserModal();
    showToast(`User "${payload.username}" created`, "success");
    await loadUsers();
  } catch (err) {
    errBox.textContent = err.message;
    errBox.style.display = "block";
  } finally {
    submitBtn.disabled = false;
  }
}

// --- Reset-password modal ---

function openResetPwModal(u) {
  resetTargetId = u.id;
  $("#reset-pw-username").textContent = u.username;
  $("#reset-pw-error").style.display = "none";
  $("#reset-pw-form").reset();
  $("#reset-pw-modal").classList.remove("hidden");
  setTimeout(() => $("#rp-password").focus(), 50);
}

function closeResetPwModal() {
  $("#reset-pw-modal").classList.add("hidden");
  resetTargetId = null;
}

async function onSubmitResetPw(ev) {
  ev.preventDefault();
  if (resetTargetId == null) return;

  const errBox = $("#reset-pw-error");
  errBox.style.display = "none";
  const newPassword = $("#rp-password").value;
  if (newPassword.length < 6) {
    errBox.textContent = "Password must be ≥ 6 chars.";
    errBox.style.display = "block";
    return;
  }

  const submitBtn = $("#reset-pw-submit");
  submitBtn.disabled = true;
  try {
    await fetchJson(`/api/admin/users/${resetTargetId}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ new_password: newPassword }),
    });
    closeResetPwModal();
    showToast("Password updated", "success");
  } catch (err) {
    errBox.textContent = err.message;
    errBox.style.display = "block";
  } finally {
    submitBtn.disabled = false;
  }
}

// --- wire up ---

function init() {
  $("#new-user-btn").addEventListener("click", openNewUserModal);
  $("#new-user-close").addEventListener("click", closeNewUserModal);
  $("#new-user-cancel").addEventListener("click", closeNewUserModal);
  $("#new-user-form").addEventListener("submit", onSubmitNewUser);

  $("#reset-pw-close").addEventListener("click", closeResetPwModal);
  $("#reset-pw-cancel").addEventListener("click", closeResetPwModal);
  $("#reset-pw-form").addEventListener("submit", onSubmitResetPw);

  // Click outside modal to close
  $("#new-user-modal").addEventListener("click", (ev) => {
    if (ev.target.id === "new-user-modal") closeNewUserModal();
  });
  $("#reset-pw-modal").addEventListener("click", (ev) => {
    if (ev.target.id === "reset-pw-modal") closeResetPwModal();
  });

  // Esc to close any open modal
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      closeNewUserModal();
      closeResetPwModal();
    }
  });

  loadUsers();
}

init();
