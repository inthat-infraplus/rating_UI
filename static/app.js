// ── State ────────────────────────────────────────────────────────────────────
const state = {
  session: null,
  activeFilter: "unreviewed",
  currentRelativePath: null,
  toastTimer: null,
  uiSaveTimer: null,
  targetSaveTimer: null,
  // annotation
  drawMode: false,
  currentPolygon: [],      // [{x, y}] canvas-pixel coords, in-progress
  finishedPolygons: [],    // [{id, class_label, points:[{x,y}]}] canvas-pixel coords
  annotationSaveTimer: null,
  mousePt: null,           // {x, y} canvas-pixel, for preview line
};

// ── DOM refs ─────────────────────────────────────────────────────────────────
const folderPathInput        = document.getElementById("folder-path-input");
const targetFolderPathInput  = document.getElementById("target-folder-path-input");
const saveTargetFolderBtn    = document.getElementById("save-target-folder-btn");
const chooseTargetFolderBtn  = document.getElementById("choose-target-folder-btn");
const chooseFolderBtn        = document.getElementById("choose-folder-btn");
const importFolderBtn        = document.getElementById("import-folder-btn");
const browserFolderInput     = document.getElementById("browser-folder-input");
const loadFolderBtn          = document.getElementById("load-folder-btn");
const exportBtn              = document.getElementById("export-btn");
const exportFilenamesBtn     = document.getElementById("export-filenames-btn");
const progressCount          = document.getElementById("progress-count");
const progressPercent        = document.getElementById("progress-percent");
const selectedCount          = document.getElementById("selected-count");
const correctCount           = document.getElementById("correct-count");
const annotatedCount         = document.getElementById("annotated-count");
const progressBar            = document.getElementById("progress-bar");
const queueMeta              = document.getElementById("queue-meta");
const queueList              = document.getElementById("queue-list");
const viewerTitle            = document.getElementById("viewer-title");
const viewerSubtitle         = document.getElementById("viewer-subtitle");
const mainImage              = document.getElementById("main-image");
const imageStage             = document.getElementById("image-stage");
const imageCanvasWrap        = document.getElementById("image-canvas-wrap");
const bboxOverlay            = document.getElementById("bbox-overlay");
const annotationCanvas       = document.getElementById("annotation-canvas");
const emptyStage             = document.getElementById("empty-stage");
const currentStatus          = document.getElementById("current-status");
const reviewedAt             = document.getElementById("reviewed-at");
const prevBtn                = document.getElementById("prev-btn");
const nextBtn                = document.getElementById("next-btn");
const markCorrectBtn         = document.getElementById("mark-correct-btn");
const markWrongBtn           = document.getElementById("mark-wrong-btn");
const clearBtn               = document.getElementById("clear-btn");
const toast                  = document.getElementById("toast");
// annotation toolbar
const annotationToolbar      = document.getElementById("annotation-toolbar");
const classSelect            = document.getElementById("class-select");
const drawPolygonBtn         = document.getElementById("draw-polygon-btn");
const undoPolygonBtn         = document.getElementById("undo-polygon-btn");
const clearPolygonsBtn       = document.getElementById("clear-polygons-btn");
const polygonCountLabel      = document.getElementById("polygon-count");
const annotHint              = document.getElementById("annot-hint");
// bbox controls
const bboxToggleRow          = document.getElementById("bbox-toggle-row");
const bboxToggle             = document.getElementById("bbox-toggle");
const bboxLegend             = document.getElementById("bbox-legend");
// CSV controls
const csvPathInput           = document.getElementById("csv-path-input");
const loadCsvPathBtn         = document.getElementById("load-csv-path-btn");
const browseCsvBtn           = document.getElementById("browse-csv-btn");
const csvFileInput           = document.getElementById("csv-file-input");
const csvStatusText          = document.getElementById("csv-status-text");
const exportCsvBtn           = document.getElementById("export-csv-btn");
// Scale profile controls
const scaleProfilePathInput   = document.getElementById("scale-profile-path-input");
const loadScaleProfileBtn     = document.getElementById("load-scale-profile-btn");
const browseScaleProfileBtn   = document.getElementById("browse-scale-profile-btn");
const scaleProfileFileInput   = document.getElementById("scale-profile-file-input");
const scaleStatusText         = document.getElementById("scale-status-text");

const ctx = annotationCanvas.getContext("2d");

// ── Utilities ─────────────────────────────────────────────────────────────────
async function api(url, options = {}) {
  const isFormData = options.body instanceof FormData;
  const headers = { ...(options.headers || {}) };
  if (!isFormData && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(url, { headers, ...options });
  if (!response.ok) {
    let message = "Request failed.";
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {
      message = `${message} (${response.status})`;
    }
    throw new Error(message);
  }
  return response;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(state.toastTimer);
  state.toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 2600);
}

// Normalize a user-typed file/folder path:
//   • strips surrounding whitespace and quotes
//   • turns forward slashes to backslashes on Windows-style paths
//   • fixes missing colon after drive letter  e.g.  "C\foo" → "C:\foo"
function normalizePath(raw) {
  let p = (raw || "").trim();
  // Strip surrounding single or double quotes
  p = p.replace(/^["']|["']$/g, "");
  // Fix "C\..." → "C:\..." (colon omitted after drive letter)
  p = p.replace(/^([A-Za-z])\\(?!\\)/, "$1:\\");
  // Normalize any mix of forward/backward slashes inside the path to backslashes
  // (Windows paths only — detect by drive letter or UNC prefix)
  if (/^[A-Za-z]:[\\\/]/.test(p) || p.startsWith("\\\\")) {
    p = p.replace(/\//g, "\\");
  }
  return p;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function genId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

// ── Filter helpers ───────────────────────────────────────────────────────────
function filterImages(images, filterMode) {
  if (filterMode === "reviewed")   return images.filter((i) => i.reviewed);
  if (filterMode === "unreviewed") return images.filter((i) => !i.reviewed);
  if (filterMode === "selected")   return images.filter((i) => i.selected);
  return images;
}

function normalizeFilterMode(filterMode) {
  if (filterMode === "reviewed" || filterMode === "selected") return filterMode;
  return "unreviewed";
}

function currentImage() {
  if (!state.session) return null;
  const images = filterImages(state.session.images, state.activeFilter);
  if (!images.length) return null;
  return images.find((i) => i.relative_path === state.currentRelativePath) || images[0];
}

// ── Coordinate helpers ───────────────────────────────────────────────────────
function canvasToNorm(cx, cy) {
  return { x: cx / annotationCanvas.width, y: cy / annotationCanvas.height };
}

function normToCanvas(nx, ny) {
  return { x: nx * annotationCanvas.width, y: ny * annotationCanvas.height };
}

function getCanvasPos(e) {
  const rect = annotationCanvas.getBoundingClientRect();
  return {
    x: (e.clientX - rect.left) * (annotationCanvas.width / rect.width),
    y: (e.clientY - rect.top) * (annotationCanvas.height / rect.height),
  };
}

// ── Overlay sizing ───────────────────────────────────────────────────────────
function syncOverlaySize() {
  const rect = mainImage.getBoundingClientRect();
  if (!rect.width || !rect.height) return;

  annotationCanvas.width  = rect.width;
  annotationCanvas.height = rect.height;
  bboxOverlay.setAttribute("viewBox", `0 0 ${rect.width} ${rect.height}`);
  bboxOverlay.setAttribute("width",  rect.width);
  bboxOverlay.setAttribute("height", rect.height);

  // Re-project stored finished polygons (normalized → canvas px), preserving value/unit
  const image = currentImage();
  if (image && image.polygons && image.polygons.length) {
    state.finishedPolygons = image.polygons.map((poly) => ({
      id: poly.id,
      class_label: poly.class_label,
      points: poly.points.map((p) => normToCanvas(p.x, p.y)),
      value: poly.value ?? null,
      unit: poly.unit || "",
    }));
  }

  renderBboxOverlay();
  redrawCanvas();
}

// ── Bbox (SVG) rendering ─────────────────────────────────────────────────────
const CLASS_COLORS = {
  "alligator crack": "#e63946",
  "crack":           "#f4a261",
  "patching":        "#2a9d8f",
  "pothole":         "#e9c46a",
  "pavement":        "#457b9d",
};

function classColor(label) {
  return CLASS_COLORS[label.toLowerCase()] || "#ffffff";
}

function renderBboxOverlay() {
  bboxOverlay.innerHTML = "";
  const image = currentImage();
  if (!image || !image.prediction_boxes || !image.prediction_boxes.length) return;
  if (!bboxToggle.checked) return;
  if (!mainImage.naturalWidth) return;

  const scaleX = annotationCanvas.width  / mainImage.naturalWidth;
  const scaleY = annotationCanvas.height / mainImage.naturalHeight;

  const ns = "http://www.w3.org/2000/svg";
  for (const box of image.prediction_boxes) {
    const color = classColor(box.class_label);
    const g = document.createElementNS(ns, "g");

    const rect = document.createElementNS(ns, "rect");
    rect.setAttribute("x",      box.x1 * scaleX);
    rect.setAttribute("y",      box.y1 * scaleY);
    rect.setAttribute("width",  (box.x2 - box.x1) * scaleX);
    rect.setAttribute("height", (box.y2 - box.y1) * scaleY);
    rect.setAttribute("fill",   "none");
    rect.setAttribute("stroke", color);
    rect.setAttribute("stroke-width", "2");
    rect.setAttribute("stroke-dasharray", "8 4");
    rect.setAttribute("opacity", "0.9");

    const title = document.createElementNS(ns, "title");
    title.textContent = `${box.class_label} (conf: ${box.confidence.toFixed(2)})`;

    // Label background + text
    const labelY  = Math.max(box.y1 * scaleY - 4, 14);
    const labelX  = box.x1 * scaleX;
    const labelTxt = `${box.class_label} ${box.confidence.toFixed(2)}`;

    const bg = document.createElementNS(ns, "rect");
    bg.setAttribute("x",      labelX);
    bg.setAttribute("y",      labelY - 13);
    bg.setAttribute("width",  labelTxt.length * 6.5 + 8);
    bg.setAttribute("height", 16);
    bg.setAttribute("fill",   color);
    bg.setAttribute("rx",     "3");
    bg.setAttribute("opacity","0.85");

    const text = document.createElementNS(ns, "text");
    text.setAttribute("x", labelX + 4);
    text.setAttribute("y", labelY);
    text.setAttribute("fill", "#fff");
    text.setAttribute("font-size", "11");
    text.setAttribute("font-family", "Segoe UI, sans-serif");
    text.setAttribute("font-weight", "600");
    text.textContent = labelTxt;

    g.appendChild(rect);
    g.appendChild(title);
    g.appendChild(bg);
    g.appendChild(text);
    bboxOverlay.appendChild(g);
  }
}

// ── Polygon canvas drawing ───────────────────────────────────────────────────
const SNAP_RADIUS = 12;
const POLYGON_COLORS = [
  "#06d6a0", "#118ab2", "#ffd166", "#ef476f",
  "#a8dadc", "#f8961e", "#90be6d", "#c77dff",
];

function polyColor(index) {
  return POLYGON_COLORS[index % POLYGON_COLORS.length];
}

// Draw a readable pill badge (dark background, white text + color accent dot)
function drawPolygonBadge(cx, cy, classLabel, value, unit, accentColor) {
  const hasValue = value !== null && value !== undefined;
  const line1 = classLabel;
  // Display m^2 as m² on canvas (prettier); the stored/exported string stays m^2
  const displayUnit = (unit || "").replace("m^2", "m²");
  const line2 = hasValue ? `${value} ${displayUnit}` : null;

  const FONT_BOLD = "bold 12px 'Segoe UI', sans-serif";
  const FONT_REG  = "11px 'Segoe UI', sans-serif";
  const PAD_X = 9, PAD_Y = 5, LINE_GAP = 3, DOT_R = 4;

  ctx.font = FONT_BOLD;
  const w1 = ctx.measureText(line1).width;
  ctx.font = FONT_REG;
  const w2 = line2 ? ctx.measureText(line2).width : 0;

  const textW = Math.max(w1, w2);
  const badgeW = DOT_R * 2 + 6 + textW + PAD_X * 2;
  const lineH  = 14;
  const badgeH = PAD_Y * 2 + lineH + (line2 ? LINE_GAP + lineH : 0);
  const bx = cx - badgeW / 2;
  const by = cy - badgeH / 2;

  // Shadow
  ctx.shadowColor = "rgba(0,0,0,0.35)";
  ctx.shadowBlur = 6;

  // Background pill
  ctx.beginPath();
  if (ctx.roundRect) {
    ctx.roundRect(bx, by, badgeW, badgeH, 6);
  } else {
    ctx.rect(bx, by, badgeW, badgeH);
  }
  ctx.fillStyle = "rgba(15, 20, 28, 0.82)";
  ctx.fill();
  ctx.shadowBlur = 0;

  // Accent colour dot
  const dotX = bx + PAD_X + DOT_R;
  const dotY  = by + PAD_Y + lineH / 2;
  ctx.beginPath();
  ctx.arc(dotX, dotY, DOT_R, 0, Math.PI * 2);
  ctx.fillStyle = accentColor;
  ctx.fill();

  // Line 1 — class label (bold white)
  const textX = dotX + DOT_R + 5;
  ctx.font = FONT_BOLD;
  ctx.fillStyle = "#ffffff";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillText(line1, textX, dotY);

  // Line 2 — value (muted, smaller)
  if (line2) {
    const y2 = dotY + lineH + LINE_GAP;
    ctx.font = FONT_REG;
    ctx.fillStyle = "rgba(255,255,255,0.72)";
    ctx.fillText(line2, textX, y2);
  }

  // Reset canvas state
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
}

function redrawCanvas() {
  ctx.clearRect(0, 0, annotationCanvas.width, annotationCanvas.height);

  // Draw finished polygons
  for (let i = 0; i < state.finishedPolygons.length; i++) {
    const poly = state.finishedPolygons[i];
    if (!poly.points.length) continue;
    const color = polyColor(i);

    ctx.beginPath();
    ctx.moveTo(poly.points[0].x, poly.points[0].y);
    for (let j = 1; j < poly.points.length; j++) {
      ctx.lineTo(poly.points[j].x, poly.points[j].y);
    }
    ctx.closePath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.setLineDash([]);
    ctx.stroke();
    ctx.fillStyle = color + "33"; // ~20% opacity fill
    ctx.fill();

    // Class label + real-world value — pill badge at polygon centroid
    const cx = poly.points.reduce((s, p) => s + p.x, 0) / poly.points.length;
    const cy = poly.points.reduce((s, p) => s + p.y, 0) / poly.points.length;
    drawPolygonBadge(cx, cy, poly.class_label, poly.value, poly.unit, color);
  }

  // Draw in-progress polygon
  if (state.drawMode && state.currentPolygon.length > 0) {
    const pts  = state.currentPolygon;
    const color = polyColor(state.finishedPolygons.length);

    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);

    // Preview line to mouse cursor
    if (state.mousePt) {
      ctx.lineTo(state.mousePt.x, state.mousePt.y);
    }

    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 3]);
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw vertex dots
    for (let i = 0; i < pts.length; i++) {
      const isFirst = i === 0;
      ctx.beginPath();
      ctx.arc(pts[i].x, pts[i].y, isFirst ? SNAP_RADIUS / 2 : 4, 0, Math.PI * 2);
      ctx.fillStyle = isFirst ? "#ffffff" : color;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.fill();
      ctx.stroke();
    }

    // Snap indicator on first vertex
    if (pts.length >= 3 && state.mousePt) {
      const dx = state.mousePt.x - pts[0].x;
      const dy = state.mousePt.y - pts[0].y;
      if (Math.sqrt(dx * dx + dy * dy) <= SNAP_RADIUS) {
        ctx.beginPath();
        ctx.arc(pts[0].x, pts[0].y, SNAP_RADIUS, 0, Math.PI * 2);
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2;
        ctx.setLineDash([3, 2]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }
  }

  ctx.textAlign = "left"; // reset
}

// ── Polygon drawing logic ────────────────────────────────────────────────────
function enterDrawMode() {
  state.drawMode = true;
  state.currentPolygon = [];
  state.mousePt = null;
  annotationCanvas.classList.add("draw-mode");
  annotationCanvas.style.pointerEvents = "auto";
  drawPolygonBtn.classList.add("active");
  annotHint.style.display = "";
  redrawCanvas();
}

function exitDrawMode() {
  state.drawMode = false;
  state.currentPolygon = [];
  state.mousePt = null;
  annotationCanvas.classList.remove("draw-mode");
  annotationCanvas.style.pointerEvents = "none";
  drawPolygonBtn.classList.remove("active");
  annotHint.style.display = "none";
  redrawCanvas();
}

function closeCurrentPolygon() {
  if (state.currentPolygon.length < 3) {
    showToast("Need at least 3 points to close a polygon.");
    return;
  }
  const newPoly = {
    id: genId(),
    class_label: classSelect.value,
    points: [...state.currentPolygon],
    value: null,
    unit: "",
  };
  state.finishedPolygons.push(newPoly);
  state.currentPolygon = [];
  state.mousePt = null;
  updateAnnotationToolbar();
  redrawCanvas();
  queueAnnotationSave();
  // Auto-calculate real-world area/length if scale profile is linked
  calculatePolygonArea(newPoly);
}

async function calculatePolygonArea(poly) {
  if (!state.session || !state.session.scale_profile_path) return;
  const image = currentImage();
  if (!image) return;

  const normPoints = poly.points.map((pt) => canvasToNorm(pt.x, pt.y));

  try {
    const response = await api("/api/calculate-area", {
      method: "POST",
      body: JSON.stringify({
        folder_path: state.session.folder_path,
        class_label: poly.class_label,
        points: normPoints,
        image_natural_width: mainImage.naturalWidth || 1,
        image_natural_height: mainImage.naturalHeight || 1,
      }),
    });
    const result = await response.json();
    // Update the polygon in-place with real-world value
    poly.value = result.value;
    poly.unit  = result.unit;
    redrawCanvas();
    queueAnnotationSave();
  } catch (err) {
    // Non-fatal: area calculation failed but polygon is still saved
    console.warn("Area calculation failed:", err.message);
  }
}

// Click disambiguation: 220 ms timer so dblclick doesn't add spurious vertices
let _clickTimer = null;

annotationCanvas.addEventListener("click", (e) => {
  if (!state.drawMode) return;

  const pt = getCanvasPos(e);

  // Snap-to-first-point if 3+ vertices placed
  if (state.currentPolygon.length >= 3) {
    const first = state.currentPolygon[0];
    const dx = pt.x - first.x;
    const dy = pt.y - first.y;
    if (Math.sqrt(dx * dx + dy * dy) <= SNAP_RADIUS) {
      if (_clickTimer !== null) { clearTimeout(_clickTimer); _clickTimer = null; }
      closeCurrentPolygon();
      return;
    }
  }

  if (_clickTimer !== null) {
    // Second click quickly — treat as double-click → close
    clearTimeout(_clickTimer);
    _clickTimer = null;
    closeCurrentPolygon();
    return;
  }

  _clickTimer = setTimeout(() => {
    _clickTimer = null;
    state.currentPolygon.push(pt);
    redrawCanvas();
  }, 220);
});

annotationCanvas.addEventListener("dblclick", (e) => {
  e.preventDefault();
  // The click handler's timer logic already handles this.
  // Just ensure any pending timer doesn't add extra vertex.
  if (_clickTimer !== null) { clearTimeout(_clickTimer); _clickTimer = null; }
  closeCurrentPolygon();
});

annotationCanvas.addEventListener("mousemove", (e) => {
  if (!state.drawMode) return;
  state.mousePt = getCanvasPos(e);
  redrawCanvas();
});

annotationCanvas.addEventListener("mouseleave", () => {
  state.mousePt = null;
  redrawCanvas();
});

// ── Annotation toolbar UI ────────────────────────────────────────────────────
function updateAnnotationToolbar() {
  const count = state.finishedPolygons.length;
  polygonCountLabel.textContent = `${count} polygon${count !== 1 ? "s" : ""}`;
}

function showAnnotationToolbar(show) {
  annotationToolbar.style.display = show ? "flex" : "none";
  if (!show) exitDrawMode();
}

// ── Annotation save (debounced) ──────────────────────────────────────────────
function queueAnnotationSave() {
  if (!state.session) return;
  window.clearTimeout(state.annotationSaveTimer);
  state.annotationSaveTimer = window.setTimeout(async () => {
    try {
      await saveAnnotations();
    } catch (err) {
      showToast(err.message);
    }
  }, 400);
}

async function saveAnnotations() {
  const image = currentImage();
  if (!state.session || !image) return;

  const polygons = state.finishedPolygons.map((poly) => ({
    id: poly.id,
    class_label: poly.class_label,
    points: poly.points.map((pt) => canvasToNorm(pt.x, pt.y)),
    value: poly.value ?? null,
    unit: poly.unit || "",
  }));

  const response = await api("/api/annotations", {
    method: "POST",
    body: JSON.stringify({
      folder_path: state.session.folder_path,
      relative_path: image.relative_path,
      polygons,
      image_natural_width: mainImage.naturalWidth || 1,
      image_natural_height: mainImage.naturalHeight || 1,
    }),
  });
  const payload = await response.json();
  state.session = payload.session;
  // Update stats and queue badge without full re-render to avoid canvas disruption
  renderSummary();
  updateQueueItemBadge(image.relative_path);
}

function updateQueueItemBadge(relativePath) {
  if (!state.session) return;
  const image = state.session.images.find((i) => i.relative_path === relativePath);
  if (!image) return;
  const btn = queueList.querySelector(`[data-relative-path="${encodeURIComponent(relativePath)}"]`);
  if (btn) {
    btn.querySelector(".queue-badges").innerHTML = queueBadge(image);
  }
}

// ── Render helpers ───────────────────────────────────────────────────────────
function updateFilterButtons() {
  document.querySelectorAll("[data-filter]").forEach((button) => {
    button.classList.toggle("active", button.dataset.filter === state.activeFilter);
  });
}

function statusLabel(decision) {
  if (decision === "correct") return "Correct";
  if (decision === "wrong")   return "Wrong";
  return "Unreviewed";
}

function statusClass(decision) {
  if (decision === "correct") return "status-correct";
  if (decision === "wrong")   return "status-wrong";
  return "status-unreviewed";
}

function queueBadge(item) {
  let html = "";
  if (item.decision === "correct") {
    html += '<span class="badge-soft badge-correct">Correct</span>';
  } else if (item.decision === "wrong") {
    html += '<span class="badge-soft badge-wrong">Wrong</span>';
  } else {
    html += '<span class="badge-soft badge-unreviewed">Unreviewed</span>';
  }
  if (item.annotation_count > 0) {
    html += `<span class="badge-soft badge-annotated">${item.annotation_count} polygon${item.annotation_count !== 1 ? "s" : ""}</span>`;
  }
  return html;
}

function syncCurrentImage() {
  const image = currentImage();
  state.currentRelativePath = image ? image.relative_path : null;
}

function renderQueue() {
  if (!state.session) {
    queueList.innerHTML = "";
    queueMeta.textContent = "No folder loaded.";
    return;
  }

  const filtered = filterImages(state.session.images, state.activeFilter);
  queueMeta.textContent = `${filtered.length} images in ${state.activeFilter} view`;

  if (!filtered.length) {
    queueList.innerHTML = '<div class="text-muted">No images match this filter.</div>';
    return;
  }

  queueList.innerHTML = filtered.map((item, index) => {
    const isActive = item.relative_path === state.currentRelativePath;
    return `
      <button class="queue-item ${isActive ? "active" : ""}" data-relative-path="${encodeURIComponent(item.relative_path)}" type="button">
        <span class="queue-title">${index + 1}. ${escapeHtml(item.filename)}</span>
        <span class="queue-path">${escapeHtml(item.relative_path)}</span>
        <div class="queue-badges">${queueBadge(item)}</div>
      </button>
    `;
  }).join("");

  queueList.querySelectorAll(".queue-item").forEach((button) => {
    button.addEventListener("click", () => {
      state.currentRelativePath = decodeURIComponent(button.dataset.relativePath);
      render();
      persistUiState();
    });
  });
}

function loadPolygonsForCurrentImage() {
  const image = currentImage();
  if (image && image.polygons && image.polygons.length) {
    state.finishedPolygons = image.polygons.map((poly) => ({
      id: poly.id,
      class_label: poly.class_label,
      points: poly.points.map((p) => normToCanvas(p.x, p.y)),
      value: poly.value ?? null,
      unit: poly.unit || "",
    }));
  } else {
    state.finishedPolygons = [];
  }
  state.currentPolygon = [];
}

function renderViewer() {
  const image = currentImage();
  const filtered = state.session ? filterImages(state.session.images, state.activeFilter) : [];
  const currentIndex = filtered.findIndex((i) => i.relative_path === state.currentRelativePath);
  const hasImage = Boolean(image);

  viewerTitle.textContent = hasImage ? image.filename : "No image in current filter";
  viewerSubtitle.textContent = state.session
    ? `${state.session.folder_path} | ${filtered.length} items in ${state.activeFilter} view`
    : "Keyboard shortcuts: A/D navigate, C correct, W wrong, U reset, P draw polygon, Esc cancel.";

  prevBtn.disabled = !hasImage || currentIndex <= 0;
  nextBtn.disabled = !hasImage || currentIndex === -1 || currentIndex >= filtered.length - 1;
  markCorrectBtn.disabled = !hasImage;
  markWrongBtn.disabled   = !hasImage;
  clearBtn.disabled       = !hasImage;

  if (!hasImage) {
    imageStage.classList.remove("ready");
    imageCanvasWrap.style.display = "none";
    emptyStage.style.display = "";
    mainImage.removeAttribute("src");
    currentStatus.textContent = "Unreviewed";
    currentStatus.className   = "status-pill status-unreviewed";
    reviewedAt.textContent    = "No review timestamp";
    showAnnotationToolbar(false);
    bboxToggleRow.style.display = "none";
    return;
  }

  imageStage.classList.add("ready");
  imageCanvasWrap.style.display = "";
  emptyStage.style.display = "none";
  mainImage.alt = image.relative_path;

  const isWrong = image.decision === "wrong";
  showAnnotationToolbar(isWrong);

  // Only update src if changed (avoids flicker)
  if (mainImage.src !== image.image_url &&
      !mainImage.src.endsWith(image.image_url.replace(/^\//, ""))) {
    exitDrawMode();
    loadPolygonsForCurrentImage();
    mainImage.src = image.image_url;
  } else if (!isWrong) {
    exitDrawMode();
  } else {
    // Same image, still wrong — reload polygons if annotation_count differs from drawn
    const drawnCount = state.finishedPolygons.length;
    if (image.annotation_count !== drawnCount) {
      loadPolygonsForCurrentImage();
      syncOverlaySize();
    }
    updateAnnotationToolbar();
    redrawCanvas();
  }

  currentStatus.textContent = statusLabel(image.decision);
  currentStatus.className   = `status-pill ${statusClass(image.decision)}`;
  reviewedAt.textContent    = image.reviewed_at ? `Reviewed at ${image.reviewed_at}` : "No review timestamp";

  // Bbox toggle row visibility
  const hasCsv = Boolean(state.session && state.session.csv_path);
  bboxToggleRow.style.display = (hasCsv && hasImage) ? "" : "none";
}

function renderSummary() {
  if (!state.session) {
    progressCount.textContent = "0 / 0";
    progressPercent.textContent = "0%";
    selectedCount.textContent = "0";
    correctCount.textContent = "0";
    annotatedCount.textContent = "0";
    progressBar.style.width = "0%";
    exportBtn.disabled = true;
    exportFilenamesBtn.disabled = true;
    chooseTargetFolderBtn.disabled = true;
    saveTargetFolderBtn.disabled = true;
    targetFolderPathInput.disabled = true;
    exportCsvBtn.disabled = true;
    csvStatusText.textContent = "No CSV linked";
    csvStatusText.classList.remove("csv-status-linked");
    scaleStatusText.textContent = "No scale profile linked";
    scaleStatusText.classList.remove("scale-status-linked");
    return;
  }

  const { summary, csv_path } = state.session;
  progressCount.textContent   = `${summary.reviewed_count} / ${summary.total_count}`;
  progressPercent.textContent = `${summary.percent_reviewed}%`;
  selectedCount.textContent   = summary.selected_count;
  correctCount.textContent    = summary.correct_count;
  annotatedCount.textContent  = summary.annotated_count;
  progressBar.style.width     = `${summary.percent_reviewed}%`;
  exportBtn.disabled          = summary.selected_count === 0;
  exportFilenamesBtn.disabled = summary.selected_count === 0;
  chooseTargetFolderBtn.disabled = false;
  saveTargetFolderBtn.disabled   = false;
  targetFolderPathInput.disabled = false;
  exportCsvBtn.disabled          = !csv_path;

  // CSV status label
  if (csv_path) {
    const name = csv_path.replace(/\\/g, "/").split("/").pop();
    csvStatusText.textContent = `Linked: ${name}`;
    csvStatusText.classList.add("csv-status-linked");
  } else {
    csvStatusText.textContent = "No CSV linked";
    csvStatusText.classList.remove("csv-status-linked");
  }

  // Scale profile status label
  const scale_profile_path = state.session ? state.session.scale_profile_path : null;
  if (scale_profile_path) {
    const name = scale_profile_path.replace(/\\/g, "/").split("/").pop();
    scaleStatusText.textContent = `✓ ${name}`;
    scaleStatusText.classList.add("scale-status-linked");
  } else {
    scaleStatusText.textContent = "No scale profile linked";
    scaleStatusText.classList.remove("scale-status-linked");
  }

  // Workflow steps bar + step number badges
  const hasFolder  = Boolean(state.session);
  const hasCsvLink = Boolean(state.session && state.session.csv_path);
  const hasScale   = Boolean(state.session && state.session.scale_profile_path);
  const reviewing  = hasFolder && (state.session.summary.reviewed_count > 0);
  const canExport  = hasFolder && (state.session.summary.selected_count > 0);

  setWfStep("wf1", hasFolder);
  setWfStep("wf2", hasCsvLink);
  setWfStep("wf3", hasScale);
  setWfStep("wf4", reviewing);
  setWfStep("wf5", canExport);

  // Lines light up when the step to their LEFT is done
  setDone("wf-line-1", hasFolder);
  setDone("wf-line-2", hasCsvLink);
  setDone("wf-line-3", hasScale);
  setDone("wf-line-4", reviewing);

  setStepBadge("step-num-1", hasFolder);
  setStepBadge("step-num-2", hasCsvLink);
  setStepBadge("step-num-3", hasScale);
  setStepBadge("step-num-4", reviewing);
  setStepBadge("step-num-5", canExport);
}

function setDone(id, done) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle("done", done);
}

function setWfStep(id, done) { setDone(id, done); }

function setStepBadge(id, done) { setDone(id, done); }

function render() {
  updateFilterButtons();
  syncCurrentImage();
  renderSummary();
  renderQueue();
  renderViewer();
  if (state.session) {
    folderPathInput.value = state.session.folder_path;
    targetFolderPathInput.value = state.session.target_folder_path || "";
    csvPathInput.value = state.session.csv_path || "";
    scaleProfilePathInput.value = state.session.scale_profile_path || "";
  } else {
    targetFolderPathInput.value = "";
    csvPathInput.value = "";
    scaleProfilePathInput.value = "";
  }
}

// ── Folder actions ───────────────────────────────────────────────────────────
async function loadFolder(folderPath) {
  const response = await api("/api/load-folder", {
    method: "POST",
    body: JSON.stringify({ folder_path: folderPath }),
  });
  const payload = await response.json();
  state.session = payload.session;
  state.activeFilter = normalizeFilterMode(state.session.ui_state.filter_mode);
  state.currentRelativePath = state.session.ui_state.current_relative_path;
  localStorage.setItem("rating-ui:last-folder", state.session.folder_path);
  render();
  showToast(`Loaded ${state.session.summary.total_count} image(s).`);
}

async function chooseFolder() {
  const response = await api("/api/select-folder", { method: "POST", body: "{}" });
  const payload = await response.json();
  state.session = payload.session;
  state.activeFilter = normalizeFilterMode(state.session.ui_state.filter_mode);
  state.currentRelativePath = state.session.ui_state.current_relative_path;
  localStorage.setItem("rating-ui:last-folder", state.session.folder_path);
  render();
  showToast(`Loaded ${state.session.summary.total_count} image(s).`);
}

async function importBrowserFolder(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) throw new Error("No folder was selected.");

  const firstRelativePath = files[0].webkitRelativePath || files[0].name;
  const rootName = firstRelativePath.includes("/")
    ? firstRelativePath.split("/")[0]
    : "browser-import";

  const formData = new FormData();
  formData.append("root_name", rootName);
  for (const file of files) {
    const relativePath = file.webkitRelativePath
      ? file.webkitRelativePath.split("/").slice(1).join("/")
      : file.name;
    formData.append("files", file, relativePath || file.name);
  }

  const response = await api("/api/import-folder", { method: "POST", body: formData });
  const payload = await response.json();
  state.session = payload.session;
  state.activeFilter = normalizeFilterMode(state.session.ui_state.filter_mode);
  state.currentRelativePath = state.session.ui_state.current_relative_path;
  localStorage.setItem("rating-ui:last-folder", state.session.folder_path);
  render();
  showToast(`Imported ${payload.imported_count} image(s) from ${rootName}.`);
}

// ── Review actions ───────────────────────────────────────────────────────────
async function updateDecision(decision) {
  const image = currentImage();
  if (!state.session || !image) return;

  const response = await api("/api/review", {
    method: "POST",
    body: JSON.stringify({
      folder_path: state.session.folder_path,
      relative_path: image.relative_path,
      decision,
    }),
  });
  const payload = await response.json();
  state.session = payload.session;
  state.currentRelativePath = image.relative_path;
  render();
  persistUiState();
}

// ── Target folder ────────────────────────────────────────────────────────────
async function saveTargetFolderPath() {
  if (!state.session) throw new Error("Load a prediction folder first.");
  const response = await api("/api/session-config", {
    method: "POST",
    body: JSON.stringify({
      folder_path: state.session.folder_path,
      target_folder_path: targetFolderPathInput.value.trim() || null,
    }),
  });
  const payload = await response.json();
  state.session = payload.session;
  render();
}

function queueTargetFolderAutosave() {
  if (!state.session) return;
  window.clearTimeout(state.targetSaveTimer);
  state.targetSaveTimer = window.setTimeout(async () => {
    try { await saveTargetFolderPath(); } catch (err) { showToast(err.message); }
  }, 500);
}

async function chooseTargetFolder() {
  if (!state.session) throw new Error("Load a prediction folder first.");
  const response = await api("/api/select-target-folder", {
    method: "POST",
    body: JSON.stringify({ folder_path: state.session.folder_path }),
  });
  const payload = await response.json();
  state.session = payload.session;
  render();
}

// ── CSV actions ──────────────────────────────────────────────────────────────
async function linkCsvByPath(csvPath) {
  if (!state.session) throw new Error("Load a prediction folder first (Step 1).");
  const response = await api("/api/link-csv", {
    method: "POST",
    body: JSON.stringify({
      folder_path: state.session.folder_path,
      csv_path: csvPath,
    }),
  });
  const payload = await response.json();
  state.session = payload.session;
  render();
}

async function importCsvFile(file) {
  if (!state.session) throw new Error("Load a prediction folder first (Step 1).");
  const formData = new FormData();
  formData.append("folder_path", state.session.folder_path);
  formData.append("csv_file", file, file.name);
  const response = await api("/api/import-csv", { method: "POST", body: formData });
  const payload = await response.json();
  state.session = payload.session;
  render();
}

async function linkScaleProfile(scaleProfilePath) {
  if (!state.session) throw new Error("Load a prediction folder first (Step 1).");
  const response = await api("/api/link-scale-profile", {
    method: "POST",
    body: JSON.stringify({
      folder_path: state.session.folder_path,
      scale_profile_path: scaleProfilePath,
    }),
  });
  const payload = await response.json();
  state.session = payload.session;
  render();
}

async function importScaleProfileFile(file) {
  if (!state.session) throw new Error("Load a prediction folder first (Step 1).");
  const formData = new FormData();
  formData.append("folder_path", state.session.folder_path);
  formData.append("scale_file", file, file.name);
  const response = await api("/api/import-scale-profile", { method: "POST", body: formData });
  const payload = await response.json();
  state.session = payload.session;
  render();
}

async function exportUpdatedCsv() {
  if (!state.session) return;
  const response = await api("/api/export-updated-csv", {
    method: "POST",
    body: JSON.stringify({ folder_path: state.session.folder_path }),
  });
  const blob = await response.blob();
  const url  = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  link.href = url;
  link.download = match ? match[1] : "updated_results.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  showToast("Updated CSV exported.");
}

// ── Navigation & persistence ─────────────────────────────────────────────────
function navigate(step) {
  if (!state.session) return;
  const filtered = filterImages(state.session.images, state.activeFilter);
  if (!filtered.length) return;
  const currentIndex = Math.max(
    filtered.findIndex((i) => i.relative_path === state.currentRelativePath), 0,
  );
  const nextIndex = Math.min(Math.max(currentIndex + step, 0), filtered.length - 1);
  state.currentRelativePath = filtered[nextIndex].relative_path;
  render();
  persistUiState();
}

function persistUiState() {
  if (!state.session) return;
  window.clearTimeout(state.uiSaveTimer);
  state.uiSaveTimer = window.setTimeout(async () => {
    try {
      const response = await api("/api/ui-state", {
        method: "POST",
        body: JSON.stringify({
          folder_path: state.session.folder_path,
          current_relative_path: state.currentRelativePath,
          filter_mode: state.activeFilter,
        }),
      });
      const payload = await response.json();
      state.session = payload.session;
      render();
    } catch (err) {
      showToast(err.message);
    }
  }, 250);
}

// ── Export (zip / txt) ───────────────────────────────────────────────────────
async function exportSelection() {
  if (!state.session) return;
  const response = await api("/api/export", {
    method: "POST",
    body: JSON.stringify({ folder_path: state.session.folder_path }),
  });
  const blob = await response.blob();
  const url  = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  link.href = url;
  link.download = match ? match[1] : "rating_export.zip";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  showToast("Export complete.");
}

async function exportSelectionTxt() {
  if (!state.session) return;
  const response = await api("/api/export-filenames", {
    method: "POST",
    body: JSON.stringify({ folder_path: state.session.folder_path }),
  });
  const blob = await response.blob();
  const url  = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  link.href = url;
  link.download = match ? match[1] : "selected_filenames.txt";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  showToast("TXT export complete.");
}

// ── Image onload → sync overlays ─────────────────────────────────────────────
mainImage.addEventListener("load", () => {
  loadPolygonsForCurrentImage();
  syncOverlaySize();
  updateAnnotationToolbar();
});

// Resize observer: reproject polygons and redraw when panel size changes
const resizeObserver = new ResizeObserver(() => {
  if (mainImage.naturalWidth) syncOverlaySize();
});
resizeObserver.observe(imageCanvasWrap);

// ── Event listeners ──────────────────────────────────────────────────────────
chooseFolderBtn.addEventListener("click", async () => {
  try { await chooseFolder(); } catch (err) { showToast(err.message); }
});

importFolderBtn.addEventListener("click", () => browserFolderInput.click());

browserFolderInput.addEventListener("change", async () => {
  try { await importBrowserFolder(browserFolderInput.files); }
  catch (err) { showToast(err.message); }
  finally { browserFolderInput.value = ""; }
});

loadFolderBtn.addEventListener("click", async () => {
  try {
    const folderPath = normalizePath(folderPathInput.value);
    if (!folderPath) throw new Error("Enter a folder path.");
    folderPathInput.value = folderPath;
    await loadFolder(folderPath);
  } catch (err) { showToast(err.message); }
});

saveTargetFolderBtn.addEventListener("click", async () => {
  try {
    targetFolderPathInput.value = normalizePath(targetFolderPathInput.value);
    window.clearTimeout(state.targetSaveTimer);
    await saveTargetFolderPath();
    showToast("Saved target image path.");
  } catch (err) { showToast(err.message); }
});

chooseTargetFolderBtn.addEventListener("click", async () => {
  try { await chooseTargetFolder(); showToast("Selected target image path."); }
  catch (err) { showToast(err.message); }
});

targetFolderPathInput.addEventListener("input", () => queueTargetFolderAutosave());
targetFolderPathInput.addEventListener("blur", async () => {
  if (!state.session) return;
  window.clearTimeout(state.targetSaveTimer);
  try { await saveTargetFolderPath(); } catch (err) { showToast(err.message); }
});

exportBtn.addEventListener("click", async () => {
  try { await exportSelection(); } catch (err) { showToast(err.message); }
});

exportFilenamesBtn.addEventListener("click", async () => {
  try { await exportSelectionTxt(); } catch (err) { showToast(err.message); }
});

markCorrectBtn.addEventListener("click", async () => {
  try { await updateDecision("correct"); showToast("Marked correct."); }
  catch (err) { showToast(err.message); }
});

markWrongBtn.addEventListener("click", async () => {
  try { await updateDecision("wrong"); showToast("Marked wrong — draw polygon corrections below."); }
  catch (err) { showToast(err.message); }
});

clearBtn.addEventListener("click", async () => {
  try { await updateDecision("unreviewed"); showToast("Cleared review state."); }
  catch (err) { showToast(err.message); }
});

prevBtn.addEventListener("click", () => navigate(-1));
nextBtn.addEventListener("click", () => navigate(1));

document.getElementById("filter-group").addEventListener("click", (event) => {
  const target = event.target.closest("[data-filter]");
  if (!target) return;
  state.activeFilter = target.dataset.filter;
  render();
  persistUiState();
});

// Annotation toolbar
drawPolygonBtn.addEventListener("click", () => {
  if (state.drawMode) { exitDrawMode(); } else { enterDrawMode(); }
});

undoPolygonBtn.addEventListener("click", () => {
  if (state.drawMode && state.currentPolygon.length > 0) {
    state.currentPolygon.pop();
    redrawCanvas();
  } else if (state.finishedPolygons.length > 0) {
    state.finishedPolygons.pop();
    updateAnnotationToolbar();
    redrawCanvas();
    queueAnnotationSave();
  }
});

clearPolygonsBtn.addEventListener("click", () => {
  exitDrawMode();
  state.finishedPolygons = [];
  updateAnnotationToolbar();
  redrawCanvas();
  queueAnnotationSave();
});

// CSV controls
loadCsvPathBtn.addEventListener("click", async () => {
  try {
    const csvPath = normalizePath(csvPathInput.value);
    if (!csvPath) throw new Error("Enter a CSV file path.");
    csvPathInput.value = csvPath;
    await linkCsvByPath(csvPath);
    showToast("CSV linked successfully.");
  } catch (err) { showToast(err.message); }
});

browseCsvBtn.addEventListener("click", () => csvFileInput.click());

csvFileInput.addEventListener("change", async () => {
  if (!csvFileInput.files || !csvFileInput.files[0]) return;
  try {
    await importCsvFile(csvFileInput.files[0]);
    showToast("CSV linked successfully.");
  } catch (err) { showToast(err.message); }
  finally { csvFileInput.value = ""; }
});

exportCsvBtn.addEventListener("click", async () => {
  try { await exportUpdatedCsv(); } catch (err) { showToast(err.message); }
});

loadScaleProfileBtn.addEventListener("click", async () => {
  try {
    const path = normalizePath(scaleProfilePathInput.value);
    if (!path) throw new Error("Enter a scale profile CSV path, or use Browse…");
    scaleProfilePathInput.value = path;
    await linkScaleProfile(path);
    showToast("Scale profile linked — area/length will be calculated automatically on polygon close.");
  } catch (err) { showToast(err.message); }
});

browseScaleProfileBtn.addEventListener("click", () => scaleProfileFileInput.click());

scaleProfileFileInput.addEventListener("change", async () => {
  if (!scaleProfileFileInput.files || !scaleProfileFileInput.files[0]) return;
  try {
    await importScaleProfileFile(scaleProfileFileInput.files[0]);
    showToast("Scale profile linked — area/length will be calculated automatically on polygon close.");
  } catch (err) { showToast(err.message); }
  finally { scaleProfileFileInput.value = ""; }
});

bboxToggle.addEventListener("change", () => renderBboxOverlay());

// Keyboard shortcuts
window.addEventListener("keydown", async (event) => {
  const activeElement = document.activeElement;
  if (activeElement && ["INPUT", "TEXTAREA", "SELECT"].includes(activeElement.tagName)) return;

  try {
    if (event.key === "Escape") {
      exitDrawMode();
      return;
    }
    // Block nav/review shortcuts while actively drawing
    if (state.drawMode) return;

    if (event.key.toLowerCase() === "p") {
      const image = currentImage();
      if (image && image.decision === "wrong") {
        if (state.drawMode) { exitDrawMode(); } else { enterDrawMode(); }
      }
    } else if (event.key.toLowerCase() === "a" || event.key === "ArrowLeft") {
      navigate(-1);
    } else if (event.key.toLowerCase() === "d" || event.key === "ArrowRight") {
      navigate(1);
    } else if (event.key.toLowerCase() === "c") {
      await updateDecision("correct"); showToast("Marked correct.");
    } else if (event.key.toLowerCase() === "w") {
      await updateDecision("wrong"); showToast("Marked wrong — draw polygon corrections below.");
    } else if (event.key.toLowerCase() === "u") {
      await updateDecision("unreviewed"); showToast("Cleared review state.");
    }
  } catch (err) {
    showToast(err.message);
  }
});

// ── Bootstrap ────────────────────────────────────────────────────────────────
(async function bootstrap() {
  // Annotation canvas: pointer-events off until draw mode activated
  annotationCanvas.style.pointerEvents = "none";
  imageCanvasWrap.style.display = "none";

  const savedFolder = localStorage.getItem("rating-ui:last-folder");
  if (!savedFolder) { render(); return; }

  try {
    await loadFolder(savedFolder);
  } catch {
    localStorage.removeItem("rating-ui:last-folder");
    render();
  }
})();
