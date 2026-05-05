"use strict";

const updatedAtEl = document.getElementById("kpi-updated-at");
const imagesDoneEl = document.getElementById("kpi-images-done");
const approvedFoldersEl = document.getElementById("kpi-approved-folders");
const labelersEl = document.getElementById("kpi-labelers");
const rangeGroupEl = document.getElementById("kpi-range-group");
const cumulativeWrapEl = document.getElementById("kpi-cumulative-wrap");
const weeklyBarsEl = document.getElementById("kpi-weekly-bars");
const workloadTbodyEl = document.getElementById("kpi-workload-tbody");
const SVG_NS = "http://www.w3.org/2000/svg";

let timelineWeekly = [];
let activeRange = "all";

function fmtInt(value) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? num.toLocaleString() : "0";
}

function fmtPercent(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "0.0%";
  return `${num.toFixed(1)}%`;
}

function createSvgEl(tag) {
  return document.createElementNS(SVG_NS, tag);
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

function rangeToCount(range) {
  if (range === "all") return null;
  const match = /^(\d+)w$/.exec(String(range || "").trim().toLowerCase());
  if (!match) return null;
  return Math.max(1, Number(match[1]));
}

function filterTimeline(rows, range) {
  if (!Array.isArray(rows) || rows.length === 0) return [];
  const count = rangeToCount(range);
  if (!count || rows.length <= count) return rows.slice();
  return rows.slice(rows.length - count);
}

function renderCumulativeLine(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    cumulativeWrapEl.innerHTML = '<p class="dashboard-subtitle mb-0">No reviewed images yet.</p>';
    return;
  }

  cumulativeWrapEl.innerHTML = "";
  const width = 920;
  const height = 260;
  const margin = { top: 18, right: 20, bottom: 40, left: 48 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const maxY = Math.max(...rows.map((r) => Number(r.cumulative || 0)), 1);
  const minY = 0;
  const xStep = rows.length <= 1 ? plotW : plotW / (rows.length - 1);
  const yScale = (value) => margin.top + plotH - ((value - minY) / (maxY - minY || 1)) * plotH;

  const points = rows.map((row, idx) => {
    const x = margin.left + xStep * idx;
    const y = yScale(Number(row.cumulative || 0));
    return { x, y, row };
  });

  const svg = createSvgEl("svg");
  svg.setAttribute("class", "kpi-line-svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Cumulative reviewed images line chart");

  for (let tick = 0; tick <= 4; tick += 1) {
    const yVal = (maxY / 4) * tick;
    const y = yScale(yVal);
    const grid = createSvgEl("line");
    grid.setAttribute("x1", String(margin.left));
    grid.setAttribute("y1", String(y));
    grid.setAttribute("x2", String(width - margin.right));
    grid.setAttribute("y2", String(y));
    grid.setAttribute("class", "kpi-line-grid");
    svg.appendChild(grid);
  }

  const axisX = createSvgEl("line");
  axisX.setAttribute("x1", String(margin.left));
  axisX.setAttribute("y1", String(margin.top + plotH));
  axisX.setAttribute("x2", String(width - margin.right));
  axisX.setAttribute("y2", String(margin.top + plotH));
  axisX.setAttribute("class", "kpi-line-axis");
  svg.appendChild(axisX);

  const axisY = createSvgEl("line");
  axisY.setAttribute("x1", String(margin.left));
  axisY.setAttribute("y1", String(margin.top));
  axisY.setAttribute("x2", String(margin.left));
  axisY.setAttribute("y2", String(margin.top + plotH));
  axisY.setAttribute("class", "kpi-line-axis");
  svg.appendChild(axisY);

  const polyline = createSvgEl("polyline");
  polyline.setAttribute(
    "points",
    points.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" "),
  );
  polyline.setAttribute("class", "kpi-line-path");
  svg.appendChild(polyline);

  for (const point of points) {
    const dot = createSvgEl("circle");
    dot.setAttribute("cx", String(point.x));
    dot.setAttribute("cy", String(point.y));
    dot.setAttribute("r", "3");
    dot.setAttribute("class", "kpi-line-dot");
    svg.appendChild(dot);
  }

  const firstPoint = points[0];
  const midPoint = points[Math.floor(points.length / 2)];
  const lastPoint = points[points.length - 1];
  for (const tickPoint of [firstPoint, midPoint, lastPoint]) {
    if (!tickPoint) continue;
    const label = createSvgEl("text");
    label.setAttribute("x", String(tickPoint.x));
    label.setAttribute("y", String(height - 12));
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("class", "kpi-line-xlabel");
    label.textContent = tickPoint.row.week_label || tickPoint.row.week_start || "";
    svg.appendChild(label);
  }

  const maxLabel = createSvgEl("text");
  maxLabel.setAttribute("x", String(margin.left + 6));
  maxLabel.setAttribute("y", String(margin.top + 12));
  maxLabel.setAttribute("class", "kpi-line-ylabel");
  maxLabel.textContent = `${fmtInt(maxY)} total`;
  svg.appendChild(maxLabel);

  const lastValueLabel = createSvgEl("text");
  lastValueLabel.setAttribute("x", String(lastPoint.x));
  lastValueLabel.setAttribute("y", String(Math.max(margin.top + 12, lastPoint.y - 10)));
  lastValueLabel.setAttribute("text-anchor", "end");
  lastValueLabel.setAttribute("class", "kpi-line-lastvalue");
  lastValueLabel.textContent = fmtInt(lastPoint.row.cumulative);
  svg.appendChild(lastValueLabel);

  cumulativeWrapEl.appendChild(svg);
}

function setActiveRange(nextRange) {
  activeRange = nextRange || "all";
  const buttons = rangeGroupEl ? rangeGroupEl.querySelectorAll(".kpi-range-chip") : [];
  for (const btn of buttons) {
    btn.classList.toggle("active", btn.dataset.range === activeRange);
  }
  const filtered = filterTimeline(timelineWeekly, activeRange);
  renderCumulativeLine(filtered);
  renderWeeklyBars(filtered);
}

function bindRangeControls() {
  if (!rangeGroupEl) return;
  rangeGroupEl.addEventListener("click", (event) => {
    const button = event.target instanceof Element
      ? event.target.closest(".kpi-range-chip")
      : null;
    if (!button) return;
    const nextRange = button.getAttribute("data-range") || "all";
    setActiveRange(nextRange);
  });
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
    timelineWeekly = Array.isArray(data.timeline_weekly) ? data.timeline_weekly : [];
    bindRangeControls();
    setActiveRange(activeRange);
    renderWorkload(data.workload_by_labeler || []);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    updatedAtEl.textContent = `Failed to load KPI: ${message}`;
    cumulativeWrapEl.innerHTML = "";
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
