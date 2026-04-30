"use strict";

const updatedAtEl = document.getElementById("kpi-updated-at");
const imagesDoneEl = document.getElementById("kpi-images-done");
const approvedFoldersEl = document.getElementById("kpi-approved-folders");
const labelersEl = document.getElementById("kpi-labelers");
const weeklyBarsEl = document.getElementById("kpi-weekly-bars");
const workloadTbodyEl = document.getElementById("kpi-workload-tbody");

function fmtInt(value) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? num.toLocaleString() : "0";
}

function fmtPercent(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "0.0%";
  return `${num.toFixed(1)}%`;
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await res.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (_err) {
      data = { detail: text };
    }
  }
  if (!res.ok) {
    const msg = data.detail || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

function renderWeeklyBars(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    weeklyBarsEl.innerHTML = '<p class="dashboard-subtitle mb-0">No reviewed images yet.</p>';
    return;
  }
  const maxDone = Math.max(...rows.map((r) => Number(r.images_done || 0)), 1);
  weeklyBarsEl.innerHTML = "";
  for (const row of rows) {
    const done = Number(row.images_done || 0);
    const ratio = Math.max(2, Math.round((done / maxDone) * 100));
    const item = document.createElement("div");
    item.className = "kpi-week-row";
    const label = document.createElement("div");
    label.className = "kpi-week-label";
    label.textContent = row.week_label || row.week_start || "-";

    const track = document.createElement("div");
    track.className = "kpi-week-bar-track";
    const fill = document.createElement("div");
    fill.className = "kpi-week-bar-fill";
    fill.style.width = `${ratio}%`;
    track.appendChild(fill);

    const count = document.createElement("div");
    count.className = "kpi-week-count";
    count.textContent = `${fmtInt(done)} `;
    const countSpan = document.createElement("span");
    countSpan.textContent = `(${fmtInt(row.cumulative)} total)`;
    count.appendChild(countSpan);

    item.appendChild(label);
    item.appendChild(track);
    item.appendChild(count);
    weeklyBarsEl.appendChild(item);
  }
}

function renderWorkload(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    workloadTbodyEl.innerHTML = '<tr><td colspan="6">No labeler workload data yet.</td></tr>';
    return;
  }
  workloadTbodyEl.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    const name = row.display_name || row.username || `User #${row.user_id}`;

    const tdName = document.createElement("td");
    const nameDiv = document.createElement("div");
    nameDiv.className = "kpi-user-name";
    nameDiv.textContent = name;
    const userDiv = document.createElement("div");
    userDiv.className = "kpi-user-sub";
    userDiv.textContent = row.username || "";
    tdName.appendChild(nameDiv);
    tdName.appendChild(userDiv);

    const tdAssigned = document.createElement("td");
    tdAssigned.textContent = fmtInt(row.assigned_task_count);
    const tdActive = document.createElement("td");
    tdActive.textContent = fmtInt(row.active_task_count);
    const tdApproved = document.createElement("td");
    tdApproved.textContent = fmtInt(row.approved_task_count);
    const tdImages = document.createElement("td");
    tdImages.textContent = `${fmtInt(row.reviewed_images)} / ${fmtInt(row.total_images)}`;
    const tdCompletion = document.createElement("td");
    tdCompletion.textContent = fmtPercent(row.completion_pct);

    tr.appendChild(tdName);
    tr.appendChild(tdAssigned);
    tr.appendChild(tdActive);
    tr.appendChild(tdApproved);
    tr.appendChild(tdImages);
    tr.appendChild(tdCompletion);
    workloadTbodyEl.appendChild(tr);
  }
}

async function init() {
  try {
    const data = await fetchJson("/api/kpi/summary");
    const totals = data.totals || {};
    const generatedAt = data.generated_at || null;
    imagesDoneEl.textContent = fmtInt(totals.images_done);
    approvedFoldersEl.textContent = fmtInt(totals.approved_folders);
    labelersEl.textContent = fmtInt(totals.l2_users);
    if (generatedAt) {
      const dt = new Date(generatedAt);
      const text = Number.isNaN(dt.getTime()) ? generatedAt : dt.toLocaleString();
      updatedAtEl.textContent = `Updated ${text}`;
    } else {
      updatedAtEl.textContent = "Updated just now";
    }
    renderWeeklyBars(data.timeline_weekly || []);
    renderWorkload(data.workload_by_labeler || []);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    updatedAtEl.textContent = `Failed to load KPI: ${message}`;
    weeklyBarsEl.innerHTML = "";
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.textContent = `Failed to load KPI data: ${message}`;
    tr.appendChild(td);
    workloadTbodyEl.innerHTML = "";
    workloadTbodyEl.appendChild(tr);
  }
}

init();
