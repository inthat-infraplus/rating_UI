// ── State ────────────────────────────────────────────────────────────────────
const state = {
  session: null,
  activeFilter: "unreviewed",
  currentRelativePath: null,
  reviewMode: "decision",
  autoAdvance: true,
  theme: "dark",
  queueCollapsed: true,
  correctionMode: "patch",
  predictionActions: {},
  activePredictionId: null,
  toastTimer: null,
  uiSaveTimer: null,
  targetSaveTimer: null,
  targetSavePending: false,
  taskActionsBound: false,
  taskInitPending: false,
  viewerZoom: 1,
  baseImageWidth: 0,
  baseImageHeight: 0,
  // annotation
  drawMode: false,
  brushMode: false,
  eraserMode: false,
  brushSize: 20,
  brushStrokeActive: false,
  brushStrokePoints: [],
  brushLastPoint: null,
  currentPolygon: [],      // [{x, y}] canvas-pixel coords, in-progress
  finishedPolygons: [],    // [{id, class_label, points:[{x,y}]}] canvas-pixel coords
  activeMaskId: null,
  hoverMaskId: null,
  maskUiByImage: {},       // { [relativePath]: { [maskId]: { visible: bool } } }
  annotationSaveTimer: null,
  mousePt: null,           // {x, y} canvas-pixel, for preview line
  // SAM2 AI-assist
  sam2Mode: false,         // true while user is in click-to-segment mode
  sam2Available: false,    // updated from /api/sam2/status on page load
  sam2Pending: false,      // throttle: ignore clicks while a request is in flight
  sam2PromptType: "positive",
  sam2PromptSource: "point",
  sam2Points: [],          // [{x, y, label}] normalized 0..1 coords
  sam2Box: null,           // {x1,y1,x2,y2} normalized 0..1 coords
  sam2PreviewPolygons: [], // [{points:[{x,y}]}] normalized 0..1 coords, not yet committed
  sam2InferenceTimer: null,
  sam2NeedsRerun: false,
  sam2DraggingIndex: -1,
  sam2SuppressClick: false,
  sam2BoxDraftStart: null,
  sam2BoxDraftCurrent: null,
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
const queueCollapseBtn       = document.getElementById("queue-collapse-btn");
const queueProgressInline    = document.getElementById("queue-progress-inline");
const batchAcceptBtn         = document.getElementById("batch-accept-btn");
const viewerTitle            = document.getElementById("viewer-title");
const viewerSubtitle         = document.getElementById("viewer-subtitle");
const zoomOutBtn             = document.getElementById("zoom-out-btn");
const zoomResetBtn           = document.getElementById("zoom-reset-btn");
const zoomInBtn              = document.getElementById("zoom-in-btn");
const zoomValueLabel         = document.getElementById("zoom-value");
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
const decisionDeleteBtn      = document.getElementById("decision-delete-btn");
const clearBtn               = document.getElementById("clear-btn");
const undoActionBtn          = document.getElementById("undo-action-btn");
const toast                  = document.getElementById("toast");
const reviewLayout           = document.querySelector(".review-layout");
const viewerWorkspace        = document.querySelector(".viewer-workspace");
const toggleQuickReviewBtn   = document.getElementById("toggle-quick-review-btn");
const toggleThemeBtn         = document.getElementById("toggle-theme-btn");
const toggleThemeNavBtn      = document.getElementById("toggle-theme-nav-btn");
const toggleAutoAdvanceBtn   = document.getElementById("toggle-auto-advance-btn");
const batchAcceptModal       = document.getElementById("batch-accept-modal");
const batchAcceptClose       = document.getElementById("batch-accept-close");
const batchAcceptCancel      = document.getElementById("batch-accept-cancel");
const batchAcceptForm        = document.getElementById("batch-accept-form");
const batchAcceptThreshold   = document.getElementById("batch-accept-threshold");
const batchAcceptPreview     = document.getElementById("batch-accept-preview");
const batchAcceptError       = document.getElementById("batch-accept-error");
// annotation toolbar
const annotationToolbar      = document.getElementById("annotation-toolbar");
const classSelect            = document.getElementById("class-select");
const drawPolygonBtn         = document.getElementById("draw-polygon-btn");
const brushToolBtn           = document.getElementById("brush-tool-btn");
const eraserToolBtn          = document.getElementById("eraser-tool-btn");
const brushSizeInput         = document.getElementById("brush-size-input");
const brushSizeValue         = document.getElementById("brush-size-value");
const sam2ToolBtn            = document.getElementById("sam2-tool-btn");
const sam2Controls           = document.getElementById("sam2-controls");
const sam2PointModeBtn       = document.getElementById("sam2-point-mode-btn");
const sam2BoxModeBtn         = document.getElementById("sam2-box-mode-btn");
const sam2PositiveBtn        = document.getElementById("sam2-positive-btn");
const sam2NegativeBtn        = document.getElementById("sam2-negative-btn");
const sam2UndoBtn            = document.getElementById("sam2-undo-btn");
const sam2ClearBtn           = document.getElementById("sam2-clear-btn");
const sam2ConfirmBtn         = document.getElementById("sam2-confirm-btn");
const undoPolygonBtn         = document.getElementById("undo-polygon-btn");
const clearPolygonsBtn       = document.getElementById("clear-polygons-btn");
const deleteSelectedMaskBtn  = document.getElementById("delete-selected-mask-btn");
const polygonCountLabel      = document.getElementById("polygon-count");
const annotHint              = document.getElementById("annot-hint");
const annotHintSam2          = document.getElementById("annot-hint-sam2");
const annotHintSam2Live      = document.getElementById("annot-hint-sam2-live");
const sam2PromptCountLabel   = document.getElementById("sam2-prompt-count");
const maskSidebar            = document.getElementById("mask-sidebar");
const maskSidebarCount       = document.getElementById("mask-sidebar-count");
const maskSidebarMeta        = document.getElementById("mask-sidebar-meta");
const maskList               = document.getElementById("mask-list");
const correctionModePatchBtn = document.getElementById("correction-mode-patch-btn");
const correctionModeRedrawBtn = document.getElementById("correction-mode-redraw-btn");
const predictionSidebar      = document.getElementById("prediction-sidebar");
const predictionSidebarMeta  = document.getElementById("prediction-sidebar-meta");
const predictionList         = document.getElementById("prediction-list");
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
if (brushSizeInput) state.brushSize = Math.max(2, Number(brushSizeInput.value || 20));

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

function currentMaskUiMap() {
  const key = state.currentRelativePath || "__none__";
  if (!state.maskUiByImage[key]) state.maskUiByImage[key] = {};
  return state.maskUiByImage[key];
}

function computePolygonBBox(points) {
  if (!points.length) return { minX: 0, minY: 0, maxX: 0, maxY: 0 };
  let minX = points[0].x;
  let minY = points[0].y;
  let maxX = points[0].x;
  let maxY = points[0].y;
  for (let i = 1; i < points.length; i++) {
    const point = points[i];
    if (point.x < minX) minX = point.x;
    if (point.y < minY) minY = point.y;
    if (point.x > maxX) maxX = point.x;
    if (point.y > maxY) maxY = point.y;
  }
  return { minX, minY, maxX, maxY };
}

function pointInPolygon(pt, points) {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const xi = points[i].x, yi = points[i].y;
    const xj = points[j].x, yj = points[j].y;
    const intersect = ((yi > pt.y) !== (yj > pt.y))
      && (pt.x < ((xj - xi) * (pt.y - yi)) / ((yj - yi) || 1e-9) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

// ── Filter helpers ───────────────────────────────────────────────────────────
function filterImages(images, filterMode) {
  if (filterMode === "reviewed" || filterMode === "completed") return images.filter((i) => i.reviewed);
  if (filterMode === "unreviewed") return images.filter((i) => !i.reviewed);
  if (filterMode === "selected" || filterMode === "wrong") return images.filter((i) => i.selected);
  return images;
}

function normalizeFilterMode(filterMode) {
  if (filterMode === "reviewed") return "completed";
  if (filterMode === "selected") return "wrong";
  if (filterMode === "completed" || filterMode === "wrong") return filterMode;
  return "unreviewed";
}

function applyTheme() {
  document.body.classList.toggle("task-theme-dark", state.theme === "dark");
  const label = `Theme: ${state.theme === "dark" ? "Dark" : "Light"}`;
  if (toggleThemeBtn) toggleThemeBtn.textContent = label;
  if (toggleThemeNavBtn) toggleThemeNavBtn.textContent = label;
}

function applyReviewMode() {
  const isQuick = state.reviewMode === "quick_review";
  document.body.classList.toggle("quick-review-mode", isQuick);
  if (viewerWorkspace) viewerWorkspace.classList.toggle("quick-review", isQuick);
  if (toggleQuickReviewBtn) toggleQuickReviewBtn.textContent = `Quick Review: ${isQuick ? "On" : "Off"}`;
}

function applyQueueCollapse() {
  if (reviewLayout) reviewLayout.classList.toggle("queue-collapsed", state.queueCollapsed);
  if (queueCollapseBtn) queueCollapseBtn.textContent = state.queueCollapsed ? "Expand" : "Collapse";
}

function updateTopBarControls() {
  if (toggleAutoAdvanceBtn) toggleAutoAdvanceBtn.textContent = `Auto-Advance: ${state.autoAdvance ? "On" : "Off"}`;
}

function currentImage() {
  if (!state.session) return null;
  const images = filterImages(state.session.images, state.activeFilter);
  if (!images.length) return null;
  return images.find((i) => i.relative_path === state.currentRelativePath) || images[0];
}

function syncImageCorrectionState() {
  const image = currentImage();
  if (!image) {
    state.correctionMode = "patch";
    state.predictionActions = {};
    state.activePredictionId = null;
    return;
  }
  state.correctionMode = image.correction_mode === "redraw_all" ? "redraw_all" : "patch";
  const actions = {};
  for (const box of image.prediction_boxes || []) {
    actions[String(box.object_id)] = box.action || "keep";
  }
  state.predictionActions = actions;
  if (state.activePredictionId && !(String(state.activePredictionId) in actions)) {
    state.activePredictionId = null;
  }
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

function normalizedCanvasPoint(point) {
  return normToCanvas(point.x, point.y);
}

function clamp01(value) {
  return Math.max(0, Math.min(1, value));
}

function clampZoom(value) {
  return Math.max(1, Math.min(4, Number(value) || 1));
}

function updateZoomLabel() {
  if (zoomValueLabel) zoomValueLabel.textContent = `${Math.round(state.viewerZoom * 100)}%`;
}

function applyViewerZoom() {
  if (!mainImage.naturalWidth || !mainImage.naturalHeight) return;
  const availableWidth = Math.max(240, imageStage.clientWidth - 32);
  const availableHeight = Math.max(240, imageStage.clientHeight - 32);
  const fitScale = Math.min(
    availableWidth / mainImage.naturalWidth,
    availableHeight / mainImage.naturalHeight,
  );
  const safeScale = Number.isFinite(fitScale) && fitScale > 0 ? fitScale : 1;
  state.baseImageWidth = Math.max(1, Math.round(mainImage.naturalWidth * safeScale));
  state.baseImageHeight = Math.max(1, Math.round(mainImage.naturalHeight * safeScale));
  imageCanvasWrap.style.width = `${Math.round(state.baseImageWidth * state.viewerZoom)}px`;
  imageCanvasWrap.style.height = `${Math.round(state.baseImageHeight * state.viewerZoom)}px`;
  syncOverlaySize();
  updateZoomLabel();
}

function setViewerZoom(nextZoom) {
  state.viewerZoom = clampZoom(nextZoom);
  applyViewerZoom();
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
      bbox: computePolygonBBox(poly.points.map((p) => normToCanvas(p.x, p.y))),
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

function classOptions() {
  if (!classSelect) return [];
  return Array.from(classSelect.options).map((option) => ({
    value: option.value,
    label: option.textContent || option.value,
  }));
}

function classOptionsMarkup(selectedValue) {
  return classOptions().map((option) => {
    const selected = option.value === selectedValue ? "selected" : "";
    return `<option value="${escapeHtml(option.value)}" ${selected}>${escapeHtml(option.label)}</option>`;
  }).join("");
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

function hasPendingSam2Draft() {
  return state.sam2Points.length > 0 || state.sam2PreviewPolygons.length > 0 || state.sam2Pending;
}

function resetSam2Draft() {
  window.clearTimeout(state.sam2InferenceTimer);
  state.sam2Points = [];
  state.sam2Box = null;
  state.sam2PreviewPolygons = [];
  state.sam2NeedsRerun = false;
  state.sam2DraggingIndex = -1;
  state.sam2SuppressClick = false;
  state.sam2BoxDraftStart = null;
  state.sam2BoxDraftCurrent = null;
}

function ensureNoPendingSam2Draft(actionLabel = "continue") {
  if (!hasPendingSam2Draft()) return true;
  const ok = window.confirm(
    `You have an unconfirmed SAM3 preview. Discard it and ${actionLabel}?`
  );
  if (!ok) return false;
  resetSam2Draft();
  redrawCanvas();
  updateAnnotationToolbar();
  return true;
}

function drawSam2PromptMarker(point, index) {
  const canvasPt = normalizedCanvasPoint(point);
  const isPositive = point.label === 1;
  const fill = isPositive ? "#16a34a" : "#dc2626";

  ctx.save();
  ctx.beginPath();
  ctx.arc(canvasPt.x, canvasPt.y, 9, 0, Math.PI * 2);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "#ffffff";
  ctx.stroke();

  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 2.25;
  ctx.beginPath();
  ctx.moveTo(canvasPt.x - 4, canvasPt.y);
  ctx.lineTo(canvasPt.x + 4, canvasPt.y);
  if (isPositive) {
    ctx.moveTo(canvasPt.x, canvasPt.y - 4);
    ctx.lineTo(canvasPt.x, canvasPt.y + 4);
  }
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(canvasPt.x, canvasPt.y, 14, 0, Math.PI * 2);
  ctx.strokeStyle = "rgba(255,255,255,0.55)";
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.font = "600 10px 'Segoe UI', sans-serif";
  ctx.fillStyle = "rgba(15,20,28,0.86)";
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";
  ctx.fillText(String(index + 1), canvasPt.x, canvasPt.y - 16);
  ctx.restore();
}

function currentSam2BoxDraft() {
  if (!state.sam2BoxDraftStart || !state.sam2BoxDraftCurrent) return null;
  const start = state.sam2BoxDraftStart;
  const end = state.sam2BoxDraftCurrent;
  return {
    x1: Math.min(start.x, end.x),
    y1: Math.min(start.y, end.y),
    x2: Math.max(start.x, end.x),
    y2: Math.max(start.y, end.y),
  };
}

function polygonUi(poly) {
  return currentMaskUiMap()[poly.id] || { visible: true };
}

function isPolygonVisible(poly) {
  return polygonUi(poly).visible !== false;
}

function selectMask(maskId) {
  state.activeMaskId = maskId;
  state.hoverMaskId = maskId;
  if (maskId) {
    const activeMask = state.finishedPolygons.find((poly) => poly.id === maskId);
    if (activeMask && classSelect) classSelect.value = activeMask.class_label;
  }
  updateAnnotationToolbar();
  redrawCanvas();
  renderMaskSidebar();
}

async function setMaskClass(maskId, nextClassLabel) {
  const poly = state.finishedPolygons.find((item) => item.id === maskId);
  if (!poly) return;
  if (!nextClassLabel || poly.class_label === nextClassLabel) return;

  poly.class_label = nextClassLabel;
  // Class switch invalidates cached metric until recomputed.
  poly.value = null;
  poly.unit = "";
  if (classSelect) classSelect.value = nextClassLabel;

  redrawCanvas();
  renderMaskSidebar();
  queueAnnotationSave();
  await calculatePolygonArea(poly);
}

function hitTestFinishedMask(canvasPt) {
  for (let i = state.finishedPolygons.length - 1; i >= 0; i--) {
    const poly = state.finishedPolygons[i];
    if (!isPolygonVisible(poly) || !poly.points || poly.points.length < 3) continue;
    const bbox = poly.bbox || computePolygonBBox(poly.points);
    if (
      canvasPt.x < bbox.minX || canvasPt.x > bbox.maxX ||
      canvasPt.y < bbox.minY || canvasPt.y > bbox.maxY
    ) {
      continue;
    }
    if (pointInPolygon(canvasPt, poly.points)) return poly.id;
  }
  return null;
}

function deleteSelectedMask() {
  if (!state.activeMaskId) return;
  const targetId = state.activeMaskId;
  const targetPoly = state.finishedPolygons.find((poly) => poly.id === targetId);
  if (targetPoly && targetPoly.merge_action === "replace" && targetPoly.source_object_id !== null) {
    state.predictionActions[String(targetPoly.source_object_id)] = "keep";
  }
  state.finishedPolygons = state.finishedPolygons.filter((poly) => poly.id !== targetId);
  const uiMap = currentMaskUiMap();
  delete uiMap[targetId];
  state.activeMaskId = null;
  updateAnnotationToolbar();
  redrawCanvas();
  renderMaskSidebar();
  queueAnnotationSave();
}

function toggleMaskVisibility(maskId) {
  const uiMap = currentMaskUiMap();
  const current = uiMap[maskId] || { visible: true };
  uiMap[maskId] = { ...current, visible: current.visible === false };
  if (state.activeMaskId === maskId && uiMap[maskId].visible === false) {
    state.activeMaskId = null;
  }
  updateAnnotationToolbar();
  redrawCanvas();
  renderMaskSidebar();
}

function predictionActionFor(objectId) {
  return state.predictionActions[String(objectId)] || "keep";
}

function linkedMaskForPrediction(objectId) {
  return state.finishedPolygons.find(
    (poly) => poly.merge_action === "replace" && String(poly.source_object_id) === String(objectId),
  ) || null;
}

function setCorrectionMode(mode) {
  state.correctionMode = mode === "redraw_all" ? "redraw_all" : "patch";
  if (state.correctionMode === "redraw_all") {
    state.activePredictionId = null;
  }
  updateAnnotationToolbar();
  redrawCanvas();
  renderMaskSidebar();
  queueAnnotationSave();
}

function removeReplacementMask(objectId) {
  const objectKey = String(objectId);
  const removedIds = new Set();
  state.finishedPolygons = state.finishedPolygons.filter((poly) => {
    const isMatch = poly.merge_action === "replace" && String(poly.source_object_id) === objectKey;
    if (isMatch) removedIds.add(poly.id);
    return !isMatch;
  });
  if (state.activeMaskId && removedIds.has(state.activeMaskId)) {
    state.activeMaskId = null;
  }
}

function setPredictionAction(objectId, action) {
  const objectKey = String(objectId);
  const nextAction = action === "replace" ? "replace" : action === "delete" ? "delete" : "keep";
  state.predictionActions[objectKey] = nextAction;
  if (nextAction !== "replace") {
    removeReplacementMask(objectId);
  } else {
    state.activePredictionId = objectKey;
  }
  updateAnnotationToolbar();
  redrawCanvas();
  renderMaskSidebar();
  queueAnnotationSave();
}

function renderMaskSidebar() {
  if (!maskSidebar || !maskList || !maskSidebarMeta || !maskSidebarCount) return;
  const image = currentImage();
  const show = Boolean(image && image.decision === "wrong");
  maskSidebar.style.display = show ? "flex" : "none";
  if (!show) return;

  const masks = state.finishedPolygons;
  const predictionBoxes = image.prediction_boxes || [];
  const visibleCount = masks.filter((poly) => isPolygonVisible(poly)).length;
  maskSidebarCount.textContent = String(masks.length);
  maskSidebarMeta.textContent = state.correctionMode === "redraw_all"
    ? "All original detections for this image will be replaced."
    : `${visibleCount} visible · click a row or the canvas to select`;
  correctionModePatchBtn?.classList.toggle("active", state.correctionMode === "patch");
  correctionModeRedrawBtn?.classList.toggle("active", state.correctionMode === "redraw_all");

  if (predictionSidebar && predictionList && predictionSidebarMeta) {
    const locked = state.correctionMode === "redraw_all";
    predictionSidebar.classList.toggle("locked", locked);
    if (!predictionBoxes.length) {
      predictionSidebarMeta.textContent = locked
        ? "No original detections are available. New masks will define the full image."
        : "No original detections are available. New masks will be exported as additions.";
      predictionList.innerHTML = "";
    } else {
      predictionSidebarMeta.textContent = locked
        ? "All original detections are ignored during export."
        : "Choose Keep, Replace, or Delete for each original detection.";
      predictionList.innerHTML = predictionBoxes.map((box) => {
        const objectKey = String(box.object_id);
        const action = predictionActionFor(box.object_id);
        const active = !locked && state.activePredictionId === objectKey;
        const linkedMask = linkedMaskForPrediction(box.object_id);
        return `
          <div class="prediction-item ${active ? "active" : ""} ${locked ? "locked" : ""}" data-prediction-id="${objectKey}">
            <div class="prediction-main">
              <div class="prediction-title">${escapeHtml(box.class_label)} ${box.object_id}</div>
              <div class="prediction-subtitle">conf ${Number(box.confidence || 0).toFixed(2)} · ${action}${linkedMask ? " · mask linked" : ""}</div>
            </div>
            <div class="prediction-actions">
              <button class="prediction-action-btn ${action === "keep" ? "active" : ""}" type="button" data-prediction-action="keep" data-prediction-id="${objectKey}" ${locked ? "disabled" : ""}>Keep</button>
              <button class="prediction-action-btn ${action === "replace" ? "active" : ""}" type="button" data-prediction-action="replace" data-prediction-id="${objectKey}" ${locked ? "disabled" : ""}>Replace</button>
              <button class="prediction-action-btn ${action === "delete" ? "active" : ""}" type="button" data-prediction-action="delete" data-prediction-id="${objectKey}" ${locked ? "disabled" : ""}>Delete</button>
            </div>
          </div>
        `;
      }).join("");

      predictionList.querySelectorAll(".prediction-item").forEach((row) => {
        row.addEventListener("click", (event) => {
          if (state.correctionMode === "redraw_all") return;
          if (event.target.closest("[data-prediction-action]")) return;
          state.activePredictionId = row.dataset.predictionId || null;
          renderMaskSidebar();
        });
      });
      predictionList.querySelectorAll("[data-prediction-action]").forEach((btn) => {
        btn.addEventListener("click", (event) => {
          event.stopPropagation();
          setPredictionAction(btn.dataset.predictionId, btn.dataset.predictionAction);
        });
      });
    }
  }

  if (!masks.length) {
    maskList.innerHTML = "";
    return;
  }

  maskList.innerHTML = masks.map((poly, index) => {
    const active = poly.id === state.activeMaskId;
    const visible = isPolygonVisible(poly);
    const color = polyColor(index);
    const bbox = poly.bbox || computePolygonBBox(poly.points);
    const size = `${Math.round(bbox.maxX - bbox.minX)}×${Math.round(bbox.maxY - bbox.minY)}`;
    const mergeLabel = poly.merge_action === "replace" && poly.source_object_id !== null
      ? `Replace ${poly.source_object_id}`
      : "Add";
    return `
      <div class="mask-list-item ${active ? "active" : ""} ${visible ? "" : "hidden"}" data-mask-id="${escapeHtml(poly.id)}">
        <div class="mask-list-main">
          <div class="mask-list-title">
            <span class="mask-color-dot" style="background:${color}"></span>
            <span>${escapeHtml(poly.class_label)} ${index + 1}</span>
          </div>
          <div class="mask-list-subtitle">${escapeHtml(poly.id)} · ${size} · ${mergeLabel}</div>
        </div>
                <div class="mask-list-actions">
          <select class="form-select form-select-sm mask-class-select" data-mask-class-id="${escapeHtml(poly.id)}" title="Change class">
            ${classOptionsMarkup(poly.class_label)}
          </select>
          <button class="mask-icon-btn mask-visibility" type="button" data-mask-action="toggle" data-mask-id="${escapeHtml(poly.id)}" title="${visible ? "Hide mask" : "Show mask"}">${visible ? "👁" : "🙈"}</button>
          <button class="mask-icon-btn mask-delete" type="button" data-mask-action="delete" data-mask-id="${escapeHtml(poly.id)}" title="Delete mask">🗑</button>
        </div>
      </div>
    `;
  }).join("");

  maskList.querySelectorAll(".mask-list-item").forEach((row) => {
    row.addEventListener("click", (event) => {
      const action = event.target.closest("[data-mask-action]");
      const maskId = row.dataset.maskId;
      if (!maskId) return;
      if (action) return;
      selectMask(maskId);
    });
  });
  maskList.querySelectorAll("[data-mask-action='toggle']").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleMaskVisibility(btn.dataset.maskId);
    });
  });
  maskList.querySelectorAll("[data-mask-action='delete']").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.stopPropagation();
      selectMask(btn.dataset.maskId);
      deleteSelectedMask();
    });
  });
  maskList.querySelectorAll("[data-mask-class-id]").forEach((selectEl) => {
    selectEl.addEventListener("mousedown", (event) => event.stopPropagation());
    selectEl.addEventListener("click", (event) => event.stopPropagation());
    selectEl.addEventListener("change", async (event) => {
      event.stopPropagation();
      try {
        await setMaskClass(selectEl.dataset.maskClassId, selectEl.value);
      } catch (err) {
        showToast(err.message);
      }
    });
  });
}

function redrawCanvas() {
  ctx.clearRect(0, 0, annotationCanvas.width, annotationCanvas.height);

  // Draw finished polygons
  for (let i = 0; i < state.finishedPolygons.length; i++) {
    const poly = state.finishedPolygons[i];
    if (!poly.points.length || !isPolygonVisible(poly)) continue;
    const color = polyColor(i);
    const isActive = poly.id === state.activeMaskId;

    ctx.beginPath();
    ctx.moveTo(poly.points[0].x, poly.points[0].y);
    for (let j = 1; j < poly.points.length; j++) {
      ctx.lineTo(poly.points[j].x, poly.points[j].y);
    }
    ctx.closePath();
    ctx.strokeStyle = isActive ? "#1d4ed8" : color;
    ctx.lineWidth = isActive ? 4 : 2.5;
    ctx.setLineDash([]);
    ctx.stroke();
    ctx.fillStyle = isActive ? "rgba(29, 78, 216, 0.18)" : color + "33"; // ~20% opacity fill
    ctx.fill();

    // Class label + real-world value — pill badge at polygon centroid
    const cx = poly.points.reduce((s, p) => s + p.x, 0) / poly.points.length;
    const cy = poly.points.reduce((s, p) => s + p.y, 0) / poly.points.length;
    drawPolygonBadge(cx, cy, poly.class_label, poly.value, poly.unit, isActive ? "#1d4ed8" : color);
  }

  if ((state.brushMode || state.eraserMode) && state.brushStrokePoints.length) {
    const strokeColor = state.eraserMode ? "rgba(239, 68, 68, 0.38)" : "rgba(37, 99, 235, 0.24)";
    const lineColor = state.eraserMode ? "rgba(239, 68, 68, 0.85)" : "rgba(37, 99, 235, 0.92)";
    const radius = Math.max(2, state.brushSize / 2);
    ctx.save();
    ctx.fillStyle = strokeColor;
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 1.2;
    for (const p of state.brushStrokePoints) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
    ctx.restore();
  }

  // Draw SAM2 preview polygons before prompt markers so the control points
  // stay readable while the mask updates live.
  for (const poly of state.sam2PreviewPolygons) {
    if (!poly.points || poly.points.length < 3) continue;
    const canvasPoints = poly.points.map((pt) => normalizedCanvasPoint(pt));
    ctx.beginPath();
    ctx.moveTo(canvasPoints[0].x, canvasPoints[0].y);
    for (let i = 1; i < canvasPoints.length; i++) {
      ctx.lineTo(canvasPoints[i].x, canvasPoints[i].y);
    }
    ctx.closePath();
    ctx.fillStyle = "rgba(91, 33, 182, 0.22)";
    ctx.strokeStyle = "rgba(91, 33, 182, 0.92)";
    ctx.lineWidth = 2;
    ctx.setLineDash([10, 6]);
    ctx.fill();
    ctx.stroke();
    ctx.setLineDash([]);

    const cx = canvasPoints.reduce((sum, pt) => sum + pt.x, 0) / canvasPoints.length;
    const cy = canvasPoints.reduce((sum, pt) => sum + pt.y, 0) / canvasPoints.length;
    drawPolygonBadge(cx, cy, "SAM3 Preview", null, "", "#7c3aed");
  }

  const committedBox = state.sam2Box
    ? {
        x1: state.sam2Box.x1 * annotationCanvas.width,
        y1: state.sam2Box.y1 * annotationCanvas.height,
        x2: state.sam2Box.x2 * annotationCanvas.width,
        y2: state.sam2Box.y2 * annotationCanvas.height,
      }
    : null;
  const draftingBox = currentSam2BoxDraft();
  const previewBox = draftingBox || committedBox;
  if (previewBox) {
    ctx.save();
    ctx.strokeStyle = "rgba(37, 99, 235, 0.95)";
    ctx.lineWidth = 2;
    ctx.setLineDash([8, 4]);
    ctx.strokeRect(
      previewBox.x1,
      previewBox.y1,
      Math.max(1, previewBox.x2 - previewBox.x1),
      Math.max(1, previewBox.y2 - previewBox.y1),
    );
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(37, 99, 235, 0.08)";
    ctx.fillRect(
      previewBox.x1,
      previewBox.y1,
      Math.max(1, previewBox.x2 - previewBox.x1),
      Math.max(1, previewBox.y2 - previewBox.y1),
    );
    ctx.restore();
  }

  state.sam2Points.forEach((point, index) => drawSam2PromptMarker(point, index));

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
  exitBrushTools();
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
  if (!state.sam2Mode && currentImage()?.decision !== "wrong") {
    annotationCanvas.style.pointerEvents = "none";
  } else {
    annotationCanvas.style.pointerEvents = "auto";
  }
  drawPolygonBtn.classList.remove("active");
  annotHint.style.display = "none";
  redrawCanvas();
}

function enterBrushMode() {
  if (state.sam2Mode) {
    if (!ensureNoPendingSam2Draft("switch to brush tool")) return;
    exitSam2Mode();
  }
  if (state.drawMode) exitDrawMode();
  state.brushMode = true;
  state.eraserMode = false;
  state.brushStrokeActive = false;
  state.brushStrokePoints = [];
  state.brushLastPoint = null;
  annotationCanvas.style.pointerEvents = "auto";
  updateAnnotationToolbar();
  redrawCanvas();
}

function enterEraserMode() {
  if (state.sam2Mode) {
    if (!ensureNoPendingSam2Draft("switch to eraser tool")) return;
    exitSam2Mode();
  }
  if (state.drawMode) exitDrawMode();
  state.eraserMode = true;
  state.brushMode = false;
  state.brushStrokeActive = false;
  state.brushStrokePoints = [];
  state.brushLastPoint = null;
  annotationCanvas.style.pointerEvents = "auto";
  updateAnnotationToolbar();
  redrawCanvas();
}

function exitBrushTools() {
  state.brushMode = false;
  state.eraserMode = false;
  state.brushStrokeActive = false;
  state.brushStrokePoints = [];
  state.brushLastPoint = null;
}

function clampToCanvasPoint(pt) {
  return {
    x: Math.max(0, Math.min(annotationCanvas.width, pt.x)),
    y: Math.max(0, Math.min(annotationCanvas.height, pt.y)),
  };
}

function pushBrushSample(point) {
  const p = clampToCanvasPoint(point);
  if (!state.brushStrokePoints.length) {
    state.brushStrokePoints.push(p);
    state.brushLastPoint = p;
    return;
  }
  const last = state.brushLastPoint || state.brushStrokePoints[state.brushStrokePoints.length - 1];
  const dx = p.x - last.x;
  const dy = p.y - last.y;
  const dist = Math.hypot(dx, dy);
  const spacing = Math.max(1.5, state.brushSize * 0.22);
  const steps = Math.max(1, Math.ceil(dist / spacing));
  for (let i = 1; i <= steps; i++) {
    const t = i / steps;
    state.brushStrokePoints.push({
      x: last.x + dx * t,
      y: last.y + dy * t,
    });
  }
  state.brushLastPoint = p;
}

function circlePolygon(center, radius, segments = 40) {
  const points = [];
  for (let i = 0; i < segments; i++) {
    const a = (Math.PI * 2 * i) / segments;
    points.push(
      clampToCanvasPoint({
        x: center.x + Math.cos(a) * radius,
        y: center.y + Math.sin(a) * radius,
      }),
    );
  }
  return points;
}

function buildBrushPolygon(points, radius) {
  if (!points.length) return [];
  if (points.length < 2) return circlePolygon(points[0], radius);

  const left = [];
  const right = [];
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    const prev = points[Math.max(0, i - 1)];
    const next = points[Math.min(points.length - 1, i + 1)];
    const dx = next.x - prev.x;
    const dy = next.y - prev.y;
    const len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len;
    const ny = dx / len;
    left.push(clampToCanvasPoint({ x: p.x + nx * radius, y: p.y + ny * radius }));
    right.push(clampToCanvasPoint({ x: p.x - nx * radius, y: p.y - ny * radius }));
  }
  return left.concat(right.reverse());
}

function commitBrushStrokeAsPolygon() {
  if (!state.brushStrokePoints.length) return null;
  const radius = Math.max(2, state.brushSize / 2);
  const points = buildBrushPolygon(state.brushStrokePoints, radius);
  if (points.length < 3) return null;
  const poly = prepareCommittedPolygon(points);
  poly.brush_generated = true;
  state.finishedPolygons.push(poly);
  return poly;
}

function maybeEraseBrushPolygons(point) {
  const radius = Math.max(2, state.brushSize / 2);
  const cx = point.x;
  const cy = point.y;
  const kept = [];
  let changed = false;
  for (const poly of state.finishedPolygons) {
    if (!poly.brush_generated) {
      kept.push(poly);
      continue;
    }
    const bbox = poly.bbox || computePolygonBBox(poly.points);
    if (
      cx + radius < bbox.minX || cx - radius > bbox.maxX ||
      cy + radius < bbox.minY || cy - radius > bbox.maxY
    ) {
      kept.push(poly);
      continue;
    }
    let hit = false;
    if (pointInPolygon(point, poly.points)) {
      hit = true;
    } else {
      for (const vertex of poly.points) {
        if (Math.hypot(vertex.x - cx, vertex.y - cy) <= radius) {
          hit = true;
          break;
        }
      }
    }
    if (hit) {
      changed = true;
      if (state.activeMaskId === poly.id) state.activeMaskId = null;
      continue;
    }
    kept.push(poly);
  }
  if (changed) {
    state.finishedPolygons = kept;
    queueAnnotationSave();
  }
}

// ── SAM2 AI-assist: click anywhere on an object → server returns polygon ─────
function setSam2PromptType(kind) {
  state.sam2PromptType = kind === "negative" ? "negative" : "positive";
  sam2PositiveBtn?.classList.toggle("active", state.sam2PromptType === "positive");
  sam2NegativeBtn?.classList.toggle("active", state.sam2PromptType === "negative");
}

function setSam2PromptSource(kind, { resetDraft = true } = {}) {
  const nextSource = kind === "box" ? "box" : "point";
  if (resetDraft && state.sam2PromptSource !== nextSource) {
    state.sam2PreviewPolygons = [];
    if (nextSource === "box") {
      state.sam2Points = [];
      state.sam2DraggingIndex = -1;
      state.sam2SuppressClick = false;
    } else {
      state.sam2Box = null;
      state.sam2BoxDraftStart = null;
      state.sam2BoxDraftCurrent = null;
    }
  }
  state.sam2PromptSource = nextSource;
  sam2PointModeBtn?.classList.toggle("active", state.sam2PromptSource === "point");
  sam2BoxModeBtn?.classList.toggle("active", state.sam2PromptSource === "box");
  sam2PositiveBtn?.toggleAttribute("disabled", state.sam2PromptSource !== "point");
  sam2NegativeBtn?.toggleAttribute("disabled", state.sam2PromptSource !== "point");
  updateAnnotationToolbar();
  redrawCanvas();
}

function enterSam2Mode() {
  if (!state.sam2Available) {
    showToast("SAM3 isn't ready on the server. See /api/sam3/status.");
    return;
  }
  if (state.drawMode) {
    if (!ensureNoPendingSam2Draft("switch to SAM3 point prompts")) return;
    exitDrawMode();
  }
  if (state.brushMode || state.eraserMode) exitBrushTools();
  state.sam2Mode = true;
  annotationCanvas.classList.add("sam2-mode");
  annotationCanvas.style.pointerEvents = "auto";
  if (sam2ToolBtn) sam2ToolBtn.classList.add("active");
  setSam2PromptType(state.sam2PromptType);
  setSam2PromptSource(state.sam2PromptSource, { resetDraft: false });
  updateAnnotationToolbar();
  redrawCanvas();
}

function exitSam2Mode() {
  state.sam2Mode = false;
  annotationCanvas.classList.remove("sam2-mode");
  if (!state.drawMode && currentImage()?.decision !== "wrong") {
    annotationCanvas.style.pointerEvents = "none";
  } else {
    annotationCanvas.style.pointerEvents = "auto";
  }
  if (sam2ToolBtn) sam2ToolBtn.classList.remove("active");
  state.sam2DraggingIndex = -1;
  updateAnnotationToolbar();
}

function hitTestSam2Point(canvasPt) {
  for (let i = state.sam2Points.length - 1; i >= 0; i--) {
    const point = normalizedCanvasPoint(state.sam2Points[i]);
    const dx = canvasPt.x - point.x;
    const dy = canvasPt.y - point.y;
    if (Math.sqrt(dx * dx + dy * dy) <= 12) return i;
  }
  return -1;
}

function queueSam2Inference(delay = 140) {
  window.clearTimeout(state.sam2InferenceTimer);
  if (state.sam2Points.length === 0 && !state.sam2Box) {
    state.sam2PreviewPolygons = [];
    state.sam2NeedsRerun = false;
    redrawCanvas();
    updateAnnotationToolbar();
    return;
  }
  state.sam2InferenceTimer = window.setTimeout(() => {
    runSam2PreviewInference();
  }, delay);
}

async function runSam2PreviewInference() {
  const image = currentImage();
  if (!state.session || !image) return;
  if (state.sam2Points.length === 0 && !state.sam2Box) return;
  if (state.sam2Pending) {
    state.sam2NeedsRerun = true;
    return;
  }

  state.sam2Pending = true;
  state.sam2NeedsRerun = false;
  if (sam2ToolBtn) sam2ToolBtn.classList.add("loading");
  updateAnnotationToolbar();

  try {
    const response = await api("/api/sam3/segment", {
      method: "POST",
      body: JSON.stringify({
        folder_path: state.session.folder_path,
        relative_path: image.relative_path,
        points: state.sam2Points.map((pt) => ({ x: pt.x, y: pt.y })),
        labels: state.sam2Points.map((pt) => pt.label),
        box: state.sam2Box ? {
          x1: state.sam2Box.x1,
          y1: state.sam2Box.y1,
          x2: state.sam2Box.x2,
          y2: state.sam2Box.y2,
        } : null,
        image_natural_width: mainImage.naturalWidth || 1,
        image_natural_height: mainImage.naturalHeight || 1,
      }),
    });
    const result = await response.json();
    state.sam2PreviewPolygons = (result.polygons || [])
      .filter((poly) => Array.isArray(poly.points) && poly.points.length >= 3)
      .map((poly) => ({
        points: poly.points.map((pt) => ({
          x: clamp01(pt.x),
          y: clamp01(pt.y),
        })),
      }));
    redrawCanvas();
    updateAnnotationToolbar();
  } catch (err) {
    state.sam2PreviewPolygons = [];
    if (err.status === 503) {
      state.sam2Available = false;
      updateSam2Button();
      showToast(err.message || "SAM3 is not installed on the server.");
    } else {
      showToast(`SAM3 failed: ${err.message || "unknown error"}`);
    }
  } finally {
    state.sam2Pending = false;
    if (sam2ToolBtn) sam2ToolBtn.classList.remove("loading");
    updateAnnotationToolbar();
    if (state.sam2NeedsRerun) {
      state.sam2NeedsRerun = false;
      queueSam2Inference(0);
    }
  }
}

function addSam2Prompt(canvasPt) {
  const norm = canvasToNorm(canvasPt.x, canvasPt.y);
  state.sam2Points.push({
    x: clamp01(norm.x),
    y: clamp01(norm.y),
    label: state.sam2PromptType === "negative" ? 0 : 1,
  });
  updateAnnotationToolbar();
  redrawCanvas();
  queueSam2Inference();
}

function commitSam2BoxDraft() {
  const draft = currentSam2BoxDraft();
  state.sam2BoxDraftStart = null;
  state.sam2BoxDraftCurrent = null;
  if (!draft) {
    redrawCanvas();
    return;
  }
  const width = draft.x2 - draft.x1;
  const height = draft.y2 - draft.y1;
  if (width < 8 || height < 8) {
    showToast("Box prompt is too small. Drag a larger area.");
    redrawCanvas();
    return;
  }
  state.sam2Box = {
    x1: clamp01(draft.x1 / annotationCanvas.width),
    y1: clamp01(draft.y1 / annotationCanvas.height),
    x2: clamp01(draft.x2 / annotationCanvas.width),
    y2: clamp01(draft.y2 / annotationCanvas.height),
  };
  redrawCanvas();
  queueSam2Inference(0);
}

function undoSam2Prompt() {
  if (state.sam2PromptSource === "box") {
    state.sam2Box = null;
  } else if (state.sam2Points.length) {
    state.sam2Points.pop();
  } else if (state.sam2Box) {
    state.sam2Box = null;
  } else {
    return;
  }
  state.sam2PreviewPolygons = [];
  updateAnnotationToolbar();
  redrawCanvas();
  queueSam2Inference(0);
}

function clearSam2Prompts() {
  resetSam2Draft();
  updateAnnotationToolbar();
  redrawCanvas();
}

function prepareCommittedPolygon(canvasPoints) {
  const replacementObjectId = state.correctionMode === "patch" && state.activePredictionId
    && predictionActionFor(state.activePredictionId) === "replace"
      ? Number(state.activePredictionId)
      : null;
  if (replacementObjectId !== null) {
    removeReplacementMask(replacementObjectId);
  }
  return {
    id: genId(),
    class_label: classSelect.value,
    points: canvasPoints,
    value: null,
    unit: "",
    source_object_id: replacementObjectId,
    merge_action: replacementObjectId !== null ? "replace" : "add",
    bbox: computePolygonBBox(canvasPoints),
  };
}

function confirmSam2Mask() {
  if (!state.sam2PreviewPolygons.length) {
    showToast("Add point prompts until SAM3 produces a preview, then confirm it.");
    return;
  }

  const committed = [];
  for (const poly of state.sam2PreviewPolygons) {
    const canvasPoints = poly.points.map((pt) => normalizedCanvasPoint(pt));
    if (canvasPoints.length < 3) continue;
    const newPoly = prepareCommittedPolygon(canvasPoints);
    state.finishedPolygons.push(newPoly);
    committed.push(newPoly);
  }

  if (!committed.length) {
    showToast("SAM3 preview did not produce a valid polygon to commit.");
    return;
  }

  resetSam2Draft();
  updateAnnotationToolbar();
  redrawCanvas();
  queueAnnotationSave();
  for (const poly of committed) calculatePolygonArea(poly);
  showToast(`Confirmed ${committed.length} SAM3 polygon${committed.length === 1 ? "" : "s"}.`);
}

function updateSam2Button() {
  if (!sam2ToolBtn) return;
  sam2ToolBtn.disabled = !state.sam2Available;
  sam2ToolBtn.title = state.sam2Available
    ? "SAM3 assist: add inclusion/exclusion point prompts or a box prompt, preview the mask, then confirm it"
    : "SAM3 is not configured on the server. Click for details.";
}

async function probeSam2Availability() {
  try {
    const response = await api("/api/sam3/status");
    const data = await response.json();
    state.sam2Available = !!data.available;
    if (!data.available && data.reason) {
      // Stash the reason on the button so a click can surface it.
      if (sam2ToolBtn) sam2ToolBtn.dataset.unavailableReason = data.reason;
    }
  } catch (err) {
    state.sam2Available = false;
  }
  updateSam2Button();
}

function closeCurrentPolygon() {
  if (state.currentPolygon.length < 3) {
    showToast("Need at least 3 points to close a polygon.");
    return;
  }
  const newPoly = prepareCommittedPolygon([...state.currentPolygon]);
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

annotationCanvas.addEventListener("mousedown", (e) => {
  if (state.brushMode || state.eraserMode) {
    state.brushStrokeActive = true;
    state.brushStrokePoints = [];
    state.brushLastPoint = null;
    pushBrushSample(getCanvasPos(e));
    if (state.eraserMode) maybeEraseBrushPolygons(getCanvasPos(e));
    redrawCanvas();
    return;
  }
  if (!state.sam2Mode) return;
  if (state.sam2PromptSource === "box") {
    const canvasPt = getCanvasPos(e);
    state.sam2BoxDraftStart = canvasPt;
    state.sam2BoxDraftCurrent = canvasPt;
    redrawCanvas();
    return;
  }
  const hitIndex = hitTestSam2Point(getCanvasPos(e));
  if (hitIndex === -1) return;
  state.sam2DraggingIndex = hitIndex;
  state.sam2SuppressClick = false;
});

annotationCanvas.addEventListener("click", (e) => {
  if (state.brushMode || state.eraserMode) return;
  if (state.sam2Mode) {
    if (state.sam2PromptSource === "box") return;
    if (state.sam2SuppressClick) {
      state.sam2SuppressClick = false;
      return;
    }
    addSam2Prompt(getCanvasPos(e));
    return;
  }

  if (!state.drawMode) {
    const hitId = hitTestFinishedMask(getCanvasPos(e));
    selectMask(hitId);
    return;
  }

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
  if ((state.brushMode || state.eraserMode) && state.brushStrokeActive) {
    const point = getCanvasPos(e);
    pushBrushSample(point);
    if (state.eraserMode) maybeEraseBrushPolygons(point);
    redrawCanvas();
    return;
  }
  if (state.sam2Mode && state.sam2PromptSource === "box" && state.sam2BoxDraftStart) {
    state.sam2BoxDraftCurrent = getCanvasPos(e);
    redrawCanvas();
    return;
  }
  if (state.sam2Mode && state.sam2DraggingIndex !== -1) {
    const canvasPt = getCanvasPos(e);
    const norm = canvasToNorm(canvasPt.x, canvasPt.y);
    state.sam2Points[state.sam2DraggingIndex] = {
      ...state.sam2Points[state.sam2DraggingIndex],
      x: clamp01(norm.x),
      y: clamp01(norm.y),
    };
    state.sam2SuppressClick = true;
    redrawCanvas();
    queueSam2Inference();
    return;
  }
  if (!state.drawMode) return;
  state.mousePt = getCanvasPos(e);
  redrawCanvas();
});

annotationCanvas.addEventListener("mouseup", () => {
  if (state.brushStrokeActive && (state.brushMode || state.eraserMode)) {
    state.brushStrokeActive = false;
    if (state.brushMode) {
      const committed = commitBrushStrokeAsPolygon();
      if (committed) {
        queueAnnotationSave();
        calculatePolygonArea(committed);
      }
    }
    state.brushStrokePoints = [];
    state.brushLastPoint = null;
    redrawCanvas();
    renderMaskSidebar();
    return;
  }
  if (!state.sam2Mode) return;
  if (state.sam2PromptSource === "box" && state.sam2BoxDraftStart) {
    commitSam2BoxDraft();
    return;
  }
  if (state.sam2DraggingIndex !== -1) {
    state.sam2DraggingIndex = -1;
    queueSam2Inference(0);
  }
});

window.addEventListener("mouseup", () => {
  if (state.brushStrokeActive && (state.brushMode || state.eraserMode)) {
    state.brushStrokeActive = false;
    if (state.brushMode) {
      const committed = commitBrushStrokeAsPolygon();
      if (committed) {
        queueAnnotationSave();
        calculatePolygonArea(committed);
      }
    }
    state.brushStrokePoints = [];
    state.brushLastPoint = null;
    redrawCanvas();
    renderMaskSidebar();
    return;
  }
  if (!state.sam2Mode) return;
  if (state.sam2PromptSource === "box" && state.sam2BoxDraftStart) {
    commitSam2BoxDraft();
    return;
  }
  if (state.sam2DraggingIndex !== -1) {
    state.sam2DraggingIndex = -1;
    queueSam2Inference(0);
  }
});

annotationCanvas.addEventListener("mouseleave", () => {
  if (state.brushStrokeActive && (state.brushMode || state.eraserMode)) {
    redrawCanvas();
    return;
  }
  if (state.sam2Mode && state.sam2PromptSource === "box" && state.sam2BoxDraftStart) {
    redrawCanvas();
    return;
  }
  if (state.sam2Mode && state.sam2DraggingIndex !== -1) {
    state.sam2DraggingIndex = -1;
    queueSam2Inference(0);
  }
  state.mousePt = null;
  redrawCanvas();
});

// ── Annotation toolbar UI ────────────────────────────────────────────────────
function updateAnnotationToolbar() {
  const count = state.finishedPolygons.length;
  polygonCountLabel.textContent = `${count} polygon${count !== 1 ? "s" : ""}`;
  if (brushSizeValue) brushSizeValue.textContent = `${state.brushSize} px`;
  brushToolBtn?.classList.toggle("active", state.brushMode);
  eraserToolBtn?.classList.toggle("active", state.eraserMode);

  const sam2DraftActive = state.sam2Mode || hasPendingSam2Draft();
  if (sam2Controls) sam2Controls.style.display = sam2DraftActive ? "inline-flex" : "none";
  if (annotHintSam2) annotHintSam2.style.display = state.sam2Mode ? "" : "none";
  if (annotHintSam2) {
    annotHintSam2.textContent = state.sam2PromptSource === "box"
      ? "Draw one box around the pavement — SAM3 will predict from the box prompt"
      : "Add green inclusion and red exclusion points — SAM3 updates the preview live";
  }
  if (annotHintSam2Live) {
    annotHintSam2Live.style.display = hasPendingSam2Draft() ? "" : "none";
  }
  if (sam2PromptCountLabel) {
    const pointCount = state.sam2Points.length;
    const boxCount = state.sam2Box ? 1 : 0;
    const promptCount = pointCount + boxCount;
    sam2PromptCountLabel.textContent = `${promptCount} prompt${promptCount !== 1 ? "s" : ""}`;
    sam2PromptCountLabel.style.display = sam2DraftActive ? "" : "none";
  }
  if (sam2UndoBtn) sam2UndoBtn.disabled = state.sam2Points.length === 0;
  if (sam2ClearBtn) sam2ClearBtn.disabled = !hasPendingSam2Draft();
  if (sam2ConfirmBtn) {
    sam2ConfirmBtn.disabled = state.sam2PreviewPolygons.length === 0 || state.sam2Pending;
    sam2ConfirmBtn.textContent = state.sam2Pending ? "Updating…" : "Confirm Mask";
  }
  if (deleteSelectedMaskBtn) {
    deleteSelectedMaskBtn.disabled = !state.activeMaskId;
    deleteSelectedMaskBtn.textContent = state.activeMaskId ? "Delete Selected" : "Delete Selected";
  }
  sam2PositiveBtn?.classList.toggle("active", state.sam2PromptType === "positive");
  sam2NegativeBtn?.classList.toggle("active", state.sam2PromptType === "negative");
  sam2PointModeBtn?.classList.toggle("active", state.sam2PromptSource === "point");
  sam2BoxModeBtn?.classList.toggle("active", state.sam2PromptSource === "box");
  sam2PositiveBtn?.toggleAttribute("disabled", state.sam2PromptSource !== "point");
  sam2NegativeBtn?.toggleAttribute("disabled", state.sam2PromptSource !== "point");
}

function showAnnotationToolbar(show) {
  annotationToolbar.style.display = show ? "flex" : "none";
  annotationCanvas.style.pointerEvents = show ? "auto" : "none";
  if (!show) {
    exitDrawMode();
    exitBrushTools();
    resetSam2Draft();
    exitSam2Mode();
    state.activeMaskId = null;
  }
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
    source_object_id: poly.source_object_id ?? null,
    merge_action: poly.merge_action === "replace" ? "replace" : "add",
  }));

  const response = await api("/api/annotations", {
    method: "POST",
    body: JSON.stringify({
      folder_path: state.session.folder_path,
      relative_path: image.relative_path,
      polygons,
      image_natural_width: mainImage.naturalWidth || 1,
      image_natural_height: mainImage.naturalHeight || 1,
      correction_mode: state.correctionMode,
      prediction_actions: state.predictionActions,
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
  if (decision === "correct") return "Accepted";
  if (decision === "wrong")   return "Needs Fix";
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
    html += '<span class="badge-soft badge-correct">Accepted</span>';
  } else if (item.decision === "wrong") {
    html += '<span class="badge-soft badge-wrong">Fix</span>';
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
    if (queueProgressInline) queueProgressInline.textContent = "0/0 completed (0%)";
    return;
  }

  const filtered = filterImages(state.session.images, state.activeFilter);
  queueMeta.textContent = `${filtered.length} images in ${state.activeFilter} view`;
  if (queueProgressInline) {
    const summary = state.session.summary;
    queueProgressInline.textContent = `${summary.reviewed_count}/${summary.total_count} completed (${summary.percent_reviewed}%)`;
  }

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
      if (!ensureNoPendingSam2Draft("switch images")) return;
      state.currentRelativePath = decodeURIComponent(button.dataset.relativePath);
      render();
      persistUiState();
    });
  });
}

function loadPolygonsForCurrentImage() {
  const image = currentImage();
  state.activeMaskId = null;
  state.hoverMaskId = null;
  state.activePredictionId = null;
  if (image && image.polygons && image.polygons.length) {
    state.finishedPolygons = image.polygons.map((poly) => ({
      id: poly.id,
      class_label: poly.class_label,
      points: poly.points.map((p) => normToCanvas(p.x, p.y)),
      value: poly.value ?? null,
      unit: poly.unit || "",
      source_object_id: poly.source_object_id ?? null,
      merge_action: poly.merge_action || "add",
      bbox: computePolygonBBox(poly.points.map((p) => normToCanvas(p.x, p.y))),
    }));
  } else {
    state.finishedPolygons = [];
  }
  state.currentPolygon = [];
  resetSam2Draft();
  syncImageCorrectionState();
}

function renderViewer() {
  const image = currentImage();
  const filtered = state.session ? filterImages(state.session.images, state.activeFilter) : [];
  const currentIndex = filtered.findIndex((i) => i.relative_path === state.currentRelativePath);
  const hasImage = Boolean(image);

  viewerTitle.textContent = hasImage ? image.filename : "No image in current filter";
  viewerSubtitle.textContent = state.session
    ? `${state.session.folder_path} | ${filtered.length} items in ${state.activeFilter} view`
    : "Keyboard shortcuts: A accept, F fix, D delete, arrows navigate, Z undo.";

  prevBtn.disabled = !hasImage || currentIndex <= 0;
  nextBtn.disabled = !hasImage || currentIndex === -1 || currentIndex >= filtered.length - 1;
  markCorrectBtn.disabled = !hasImage;
  markWrongBtn.disabled   = !hasImage;
  if (decisionDeleteBtn) decisionDeleteBtn.disabled = !hasImage;
  clearBtn.disabled       = !hasImage;

  if (!hasImage) {
    imageStage.classList.remove("ready");
    imageCanvasWrap.style.display = "none";
    imageCanvasWrap.style.width = "";
    imageCanvasWrap.style.height = "";
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
  showAnnotationToolbar(isWrong && state.reviewMode !== "quick_review");

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

  updateZoomLabel();

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
  applyTheme();
  applyReviewMode();
  applyQueueCollapse();
  updateTopBarControls();
  updateFilterButtons();
  syncCurrentImage();
  syncImageCorrectionState();
  renderSummary();
  renderQueue();
  renderViewer();
  renderMaskSidebar();
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
  if (!ensureNoPendingSam2Draft(`mark this image as ${decision}`)) return false;

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
  return true;
}

function nextUnreviewedPath() {
  if (!state.session) return null;
  const filtered = filterImages(state.session.images, state.activeFilter);
  if (!filtered.length) return null;
  const currentIndex = Math.max(
    filtered.findIndex((item) => item.relative_path === state.currentRelativePath), 0,
  );
  for (let i = currentIndex + 1; i < filtered.length; i++) {
    if (!filtered[i].reviewed) return filtered[i].relative_path;
  }
  for (let i = 0; i <= currentIndex; i++) {
    if (!filtered[i].reviewed) return filtered[i].relative_path;
  }
  return null;
}

function smartAdvanceAfterAccept() {
  if (!state.autoAdvance || !state.session) return;
  const nextPath = nextUnreviewedPath();
  if (!nextPath) return;
  state.currentRelativePath = nextPath;
  render();
  persistUiState();
}

function nextPredictionAfterDelete(deletedPredictionId) {
  const image = currentImage();
  if (!image || state.correctionMode === "redraw_all") return null;
  const boxes = image.prediction_boxes || [];
  const startIndex = boxes.findIndex((box) => String(box.object_id) === String(deletedPredictionId));
  for (let i = startIndex + 1; i < boxes.length; i++) {
    const objectKey = String(boxes[i].object_id);
    if (predictionActionFor(objectKey) !== "delete") return objectKey;
  }
  return null;
}

function smartAdvanceAfterDelete(deletedPredictionId) {
  if (!state.autoAdvance) return;
  const nextObjectId = nextPredictionAfterDelete(deletedPredictionId);
  if (nextObjectId) {
    state.activePredictionId = nextObjectId;
    renderMaskSidebar();
    return;
  }
  const nextPath = nextUnreviewedPath();
  if (!nextPath) return;
  state.currentRelativePath = nextPath;
  render();
  persistUiState();
}

function batchAcceptCandidates(threshold) {
  if (!state.session) return [];
  const filtered = filterImages(state.session.images, state.activeFilter);
  return filtered.filter((image) => {
    if (image.reviewed) return false;
    const boxes = image.prediction_boxes || [];
    if (!boxes.length) return false;
    const maxConfidence = Math.max(...boxes.map((box) => Number(box.confidence || 0)));
    return maxConfidence >= threshold;
  });
}

function closeBatchAcceptModal() {
  if (!batchAcceptModal) return;
  batchAcceptModal.classList.add("hidden");
  if (batchAcceptError) batchAcceptError.style.display = "none";
}

function refreshBatchAcceptPreview() {
  if (!batchAcceptPreview) return;
  const threshold = Math.max(0, Math.min(1, Number(batchAcceptThreshold?.value || 0.85)));
  const candidates = batchAcceptCandidates(threshold);
  batchAcceptPreview.textContent = `${candidates.length} images match in ${state.activeFilter} filter.`;
}

async function runBatchAccept() {
  if (!state.session) return;
  const threshold = Math.max(0, Math.min(1, Number(batchAcceptThreshold?.value || 0.85)));
  const candidates = batchAcceptCandidates(threshold);
  if (!candidates.length) {
    showToast("No images matched this threshold.");
    return;
  }
  const response = await api("/api/review/batch", {
    method: "POST",
    body: JSON.stringify({
      folder_path: state.session.folder_path,
      relative_paths: candidates.map((item) => item.relative_path),
      decision: "correct",
    }),
  });
  const payload = await response.json();
  state.session = payload.session;
  render();
  persistUiState();
  showToast(`Accepted ${candidates.length} images.`);
}

// ── Target folder ────────────────────────────────────────────────────────────
async function saveTargetFolderPath() {
  if (!state.session) throw new Error("Load a prediction folder first.");
  if (state.targetSavePending) return;
  state.targetSavePending = true;
  try {
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
  } finally {
    state.targetSavePending = false;
  }
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
  if (!ensureNoPendingSam2Draft("navigate away")) return;
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
  applyViewerZoom();
  updateAnnotationToolbar();
});

// Resize observer: reproject polygons and redraw when panel size changes
const resizeObserver = new ResizeObserver(() => {
  if (mainImage.naturalWidth) applyViewerZoom();
});
resizeObserver.observe(imageStage);

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
  try {
    const changed = await updateDecision("correct");
    if (changed) {
      state.reviewMode = "decision";
      showToast("Accepted.");
      smartAdvanceAfterAccept();
    }
  }
  catch (err) { showToast(err.message); }
});

markWrongBtn.addEventListener("click", async () => {
  try {
    const changed = await updateDecision("wrong");
    if (changed) {
      state.reviewMode = "fix";
      showToast("Fix mode enabled.");
      render();
    }
  }
  catch (err) { showToast(err.message); }
});

decisionDeleteBtn?.addEventListener("click", async () => {
  try {
    const image = currentImage();
    if (!image) return;
    if (image.decision !== "wrong") {
      await updateDecision("wrong");
      state.reviewMode = "fix";
    }
    const selectedId = state.activePredictionId || String(image.prediction_boxes?.[0]?.object_id || "");
    if (!selectedId) throw new Error("Select an object in the right panel before delete.");
    setPredictionAction(selectedId, "delete");
    await saveAnnotations();
    showToast("Marked object as delete.");
    smartAdvanceAfterDelete(selectedId);
  } catch (err) { showToast(err.message); }
});

undoActionBtn?.addEventListener("click", () => {
  undoPolygonBtn.click();
});

clearBtn.addEventListener("click", async () => {
  try {
    const changed = await updateDecision("unreviewed");
    if (changed) showToast("Cleared review state.");
  }
  catch (err) { showToast(err.message); }
});

prevBtn.addEventListener("click", () => navigate(-1));
nextBtn.addEventListener("click", () => navigate(1));
zoomOutBtn?.addEventListener("click", () => setViewerZoom(state.viewerZoom - 0.25));
zoomResetBtn?.addEventListener("click", () => setViewerZoom(1));
zoomInBtn?.addEventListener("click", () => setViewerZoom(state.viewerZoom + 0.25));

document.getElementById("filter-group").addEventListener("click", (event) => {
  const target = event.target.closest("[data-filter]");
  if (!target) return;
  if (!ensureNoPendingSam2Draft("change filters")) return;
  state.activeFilter = target.dataset.filter;
  render();
  persistUiState();
});

queueCollapseBtn?.addEventListener("click", () => {
  state.queueCollapsed = !state.queueCollapsed;
  render();
});

toggleQuickReviewBtn?.addEventListener("click", () => {
  state.reviewMode = state.reviewMode === "quick_review" ? "decision" : "quick_review";
  render();
});

toggleThemeBtn?.addEventListener("click", () => {
  state.theme = state.theme === "dark" ? "light" : "dark";
  render();
});
toggleThemeNavBtn?.addEventListener("click", () => {
  state.theme = state.theme === "dark" ? "light" : "dark";
  render();
});

toggleAutoAdvanceBtn?.addEventListener("click", () => {
  state.autoAdvance = !state.autoAdvance;
  render();
});

batchAcceptBtn?.addEventListener("click", () => {
  if (!batchAcceptModal) return;
  refreshBatchAcceptPreview();
  batchAcceptModal.classList.remove("hidden");
});

batchAcceptClose?.addEventListener("click", () => closeBatchAcceptModal());
batchAcceptCancel?.addEventListener("click", () => closeBatchAcceptModal());
batchAcceptModal?.addEventListener("click", (event) => {
  if (event.target === batchAcceptModal) closeBatchAcceptModal();
});
batchAcceptThreshold?.addEventListener("input", () => refreshBatchAcceptPreview());
batchAcceptForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (batchAcceptError) batchAcceptError.style.display = "none";
  try {
    await runBatchAccept();
    closeBatchAcceptModal();
  } catch (err) {
    if (batchAcceptError) {
      batchAcceptError.textContent = err.message || "Batch accept failed.";
      batchAcceptError.style.display = "block";
    } else {
      showToast(err.message);
    }
  }
});

// Annotation toolbar
drawPolygonBtn.addEventListener("click", () => {
  if (state.sam2Mode || hasPendingSam2Draft()) {
    if (!ensureNoPendingSam2Draft("switch to manual polygon drawing")) return;
    exitSam2Mode();
  }
  exitBrushTools();
  if (state.drawMode) { exitDrawMode(); } else { enterDrawMode(); }
});

brushToolBtn?.addEventListener("click", () => {
  if (state.brushMode) {
    exitBrushTools();
    redrawCanvas();
    updateAnnotationToolbar();
    return;
  }
  enterBrushMode();
});

eraserToolBtn?.addEventListener("click", () => {
  if (state.eraserMode) {
    exitBrushTools();
    redrawCanvas();
    updateAnnotationToolbar();
    return;
  }
  enterEraserMode();
});

brushSizeInput?.addEventListener("input", () => {
  state.brushSize = Math.max(2, Math.min(120, Number(brushSizeInput.value || 20)));
  updateAnnotationToolbar();
  redrawCanvas();
});

if (sam2ToolBtn) {
  sam2ToolBtn.addEventListener("click", () => {
    // Disabled state still receives clicks via JS — surface the hint.
    if (!state.sam2Available) {
      const reason = sam2ToolBtn.dataset.unavailableReason
        || "SAM3 is not configured on the server.";
      showToast(reason);
      return;
    }
    if (state.sam2Mode) {
      exitSam2Mode();
    } else {
      enterSam2Mode();
    }
  });
}

sam2PositiveBtn?.addEventListener("click", () => {
  if (!state.sam2Mode) enterSam2Mode();
  setSam2PromptSource("point");
  setSam2PromptType("positive");
  showToast("Point prompt: Include");
});
sam2NegativeBtn?.addEventListener("click", () => {
  if (!state.sam2Mode) enterSam2Mode();
  setSam2PromptSource("point");
  setSam2PromptType("negative");
  showToast("Point prompt: Exclude");
});
sam2PointModeBtn?.addEventListener("click", () => {
  if (!state.sam2Mode) enterSam2Mode();
  setSam2PromptSource("point");
  showToast("SAM3 point mode: click to add positive or negative points.");
});
sam2BoxModeBtn?.addEventListener("click", () => {
  if (!state.sam2Mode) enterSam2Mode();
  setSam2PromptSource("box");
  showToast("SAM3 box mode: drag one box over the pavement.");
});
sam2UndoBtn?.addEventListener("click", () => undoSam2Prompt());
sam2ClearBtn?.addEventListener("click", () => clearSam2Prompts());
sam2ConfirmBtn?.addEventListener("click", () => confirmSam2Mask());
correctionModePatchBtn?.addEventListener("click", () => setCorrectionMode("patch"));
correctionModeRedrawBtn?.addEventListener("click", () => setCorrectionMode("redraw_all"));

undoPolygonBtn.addEventListener("click", () => {
  if (state.sam2Mode || hasPendingSam2Draft()) {
    undoSam2Prompt();
  } else if (state.drawMode && state.currentPolygon.length > 0) {
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
  if (state.sam2Mode || hasPendingSam2Draft()) {
    clearSam2Prompts();
    return;
  }
  exitDrawMode();
  exitBrushTools();
  state.finishedPolygons = [];
  Object.keys(state.predictionActions).forEach((key) => {
    if (state.predictionActions[key] === "replace") state.predictionActions[key] = "keep";
  });
  state.activeMaskId = null;
  updateAnnotationToolbar();
  redrawCanvas();
  renderMaskSidebar();
  queueAnnotationSave();
});

deleteSelectedMaskBtn?.addEventListener("click", () => {
  deleteSelectedMask();
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
      selectMask(null);
      exitDrawMode();
      return;
    }
    if (state.sam2Mode) {
      if (event.key.toLowerCase() === "z") {
        setSam2PromptType("positive");
        showToast("SAM3 prompt mode: Include");
        return;
      }
      if (event.key.toLowerCase() === "x") {
        setSam2PromptType("negative");
        showToast("SAM3 prompt mode: Exclude");
        return;
      }
    }
    // Block nav/review shortcuts while actively drawing
    if (state.drawMode || state.brushStrokeActive) return;

    if (event.key.toLowerCase() === "p") {
      const image = currentImage();
      if (image && image.decision === "wrong") {
        if (state.drawMode) { exitDrawMode(); } else { enterDrawMode(); }
      }
    } else if (event.key === "ArrowLeft") {
      navigate(-1);
    } else if (event.key === "ArrowRight") {
      navigate(1);
    } else if (event.key.toLowerCase() === "a") {
      const changed = await updateDecision("correct");
      if (changed) {
        state.reviewMode = "decision";
        showToast("Accepted.");
        smartAdvanceAfterAccept();
      }
    } else if (event.key.toLowerCase() === "f") {
      const changed = await updateDecision("wrong");
      if (changed) {
        state.reviewMode = "fix";
        showToast("Fix mode enabled.");
        render();
      }
    } else if (event.key.toLowerCase() === "d") {
      decisionDeleteBtn?.click();
    } else if (event.key.toLowerCase() === "z") {
      undoPolygonBtn.click();
    } else if (event.key.toLowerCase() === "c") {
      const changed = await updateDecision("correct");
      if (changed) {
        state.reviewMode = "decision";
        showToast("Accepted.");
        smartAdvanceAfterAccept();
      }
    } else if (event.key.toLowerCase() === "w") {
      const changed = await updateDecision("wrong");
      if (changed) {
        state.reviewMode = "fix";
        showToast("Fix mode enabled.");
        render();
      }
    } else if (event.key.toLowerCase() === "u") {
      if (await updateDecision("unreviewed")) showToast("Cleared review state.");
    } else if (event.key === "Delete" || event.key === "Backspace") {
      if (state.sam2Mode || hasPendingSam2Draft()) {
        undoSam2Prompt();
      } else if (state.activeMaskId) {
        deleteSelectedMask();
      }
    }
  } catch (err) {
    showToast(err.message);
  }
});

// ── Task-detail mode init ────────────────────────────────────────────────────
// When the page is rendered as /tasks/{id}, an inline script in index.html
// stashes {task_id, user} on window.__rating_ui_task. We fetch the task,
// flip ASSIGNED→IN_PROGRESS for L2 assignees, and auto-load its paths.
const taskCtx = { task: null, user: null }; // populated by initFromTask

async function initFromTask(taskInfo) {
  if (state.taskInitPending) return;
  state.taskInitPending = true;
  const navTitle = document.getElementById("task-nav-title");
  taskCtx.user = taskInfo.user || {};

  let task;
  try {
    const res = await api(`/api/tasks/${taskInfo.task_id}`);
    task = (await res.json()).task;
  } catch (err) {
    if (navTitle) navTitle.textContent = "Task not found";
    showToast(err.message || "Task fetch failed.");
    state.taskInitPending = false;
    return;
  }

  // Mark started first — for L2 this flips assigned→in_progress before we render.
  try {
    const res = await api(`/api/tasks/${task.id}/start`, { method: "POST", body: "{}" });
    task = (await res.json()).task;
  } catch { /* non-fatal */ }

  taskCtx.task = task;
  renderTaskHeader();
  wireTaskActions();

  if (!task.folder_path) {
    showToast("This task has no image folder yet — ask the reviewer to set one.");
    state.taskInitPending = false;
    return;
  }

  try {
    await loadFolder(task.folder_path);
  } catch (err) {
    showToast(`Could not load folder: ${err.message}`);
    state.taskInitPending = false;
    return;
  }

  // Optional links — failures show a toast but don't block reviewing.
  if (task.csv_path) {
    if (state.session?.csv_path === task.csv_path) {
      csvPathInput.value = task.csv_path;
      renderSummary();
    } else {
      try { await linkCsvByPath(task.csv_path); }
      catch (err) { showToast(`CSV link failed: ${err.message}`); }
    }
  }

  if (task.scale_profile_path) {
    if (state.session?.scale_profile_path === task.scale_profile_path) {
      scaleProfilePathInput.value = task.scale_profile_path;
      renderSummary();
    } else {
      try { await linkScaleProfile(task.scale_profile_path); }
      catch (err) { showToast(`Scale profile link failed: ${err.message}`); }
    }
  }

  if (task.target_folder_path) {
    if (state.session) {
      state.session.target_folder_path = task.target_folder_path;
    }
    targetFolderPathInput.value = task.target_folder_path;
    renderSummary();
  }
  state.taskInitPending = false;
}

// ── Task header / action bar / comments ─────────────────────────────────────
function renderTaskHeader() {
  const task = taskCtx.task;
  const user = taskCtx.user;
  if (!task) return;

  const navTitle = document.getElementById("task-nav-title");
  const navStatus = document.getElementById("task-nav-status");
  if (navTitle) navTitle.textContent = task.title || `Task #${task.id}`;
  if (navStatus) {
    navStatus.textContent = (task.status || "").replace("_", " ");
    navStatus.className = `status-pill status-${task.status}`;
    navStatus.style.display = "inline-flex";
  }

  const bar = document.getElementById("task-action-bar");
  const desc = document.getElementById("task-action-desc");
  const meta = document.getElementById("task-action-meta");
  const btns = document.getElementById("task-action-buttons");
  if (!bar) return;

  bar.style.display = "flex";
  desc.textContent = task.description || "(no description)";
  const metaParts = [];
  if (task.assignee_username) metaParts.push(`Assigned to ${task.assignee_username}`);
  if (task.due_date) metaParts.push(`Due ${task.due_date}`);
  if (task.creator_username) metaParts.push(`Created by ${task.creator_username}`);
  meta.textContent = metaParts.join(" · ");

  // Role + status driven action buttons
  btns.innerHTML = "";
  const role = (user.role || "").toUpperCase();
  const isAssignee = task.assigned_to === user.id;
  const status = task.status;

  if (role === "L2" && isAssignee && ["in_progress","assigned","returned"].includes(status)) {
    btns.appendChild(makeActionBtn("Submit for QC", "btn-success", async () => {
      if (!ensureNoPendingSam2Draft("submit this task")) return;
      if (!confirm("Submit this task for QC? You won't be able to edit it after.")) return;
      const res = await api(`/api/tasks/${task.id}/submit`, { method: "POST", body: "{}" });
      taskCtx.task = (await res.json()).task;
      renderTaskHeader();
      showToast("Submitted for QC. Returning to dashboard…");
      // After submit, L2 has no more actions on this task — bounce to dashboard
      // so they see the updated grid + pick up their next assignment.
      setTimeout(() => { window.location.href = "/"; }, 900);
    }));
  }

  if (role === "L1" && ["submitted","in_qc"].includes(status)) {
    btns.appendChild(makeActionBtn("Approve", "btn-success", async () => {
      if (!confirm("Approve this task?")) return;
      const res = await api(`/api/tasks/${task.id}/approve`, { method: "POST", body: "{}" });
      taskCtx.task = (await res.json()).task;
      renderTaskHeader();
      showToast("Approved. Returning to dashboard…");
      // L1 can now export from dashboard; bounce back so they see the queue clear.
      setTimeout(() => { window.location.href = "/"; }, 900);
    }));
    btns.appendChild(makeActionBtn("Return with comment", "btn-warning", () => openReturnModal()));
  }

  // Refresh comment count badge
  refreshCommentCount();
}

function makeActionBtn(label, btnClass, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = `btn btn-sm ${btnClass}`;
  b.textContent = label;
  b.addEventListener("click", async () => {
    b.disabled = true;
    try { await onClick(); }
    catch (err) { showToast(err.message || "Action failed."); }
    finally { b.disabled = false; }
  });
  return b;
}

function wireTaskActions() {
  if (state.taskActionsBound) return;
  state.taskActionsBound = true;
  // Comments modal
  const commentsBtn = document.getElementById("task-comments-btn");
  const commentsModal = document.getElementById("comments-modal");
  const commentsClose = document.getElementById("comments-close");
  const commentForm = document.getElementById("comment-form");
  const commentInput = document.getElementById("comment-input");
  const commentsError = document.getElementById("comments-error");

  if (commentsBtn) {
    commentsBtn.addEventListener("click", async () => {
      commentsModal.classList.remove("hidden");
      await renderCommentsThread();
      commentInput.focus();
    });
  }
  if (commentsClose) {
    commentsClose.addEventListener("click", () => commentsModal.classList.add("hidden"));
  }
  if (commentsModal) {
    commentsModal.addEventListener("click", (e) => {
      if (e.target === commentsModal) commentsModal.classList.add("hidden");
    });
  }
  if (commentForm) {
    commentForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      commentsError.style.display = "none";
      const message = (commentInput.value || "").trim();
      if (!message) return;
      try {
        await api(`/api/tasks/${taskCtx.task.id}/events`, {
          method: "POST",
          body: JSON.stringify({ message }),
        });
        commentInput.value = "";
        await renderCommentsThread();
        refreshCommentCount();
      } catch (err) {
        commentsError.textContent = err.message || "Failed to post comment.";
        commentsError.style.display = "block";
      }
    });
  }

  // Return-with-message modal (L1)
  const returnModal = document.getElementById("return-modal");
  const returnClose = document.getElementById("return-close");
  const returnCancel = document.getElementById("return-cancel");
  const returnForm = document.getElementById("return-form");
  const returnMessage = document.getElementById("return-message");
  const returnError = document.getElementById("return-error");

  function closeReturnModal() {
    returnModal.classList.add("hidden");
    returnError.style.display = "none";
    returnMessage.value = "";
  }

  if (returnClose) returnClose.addEventListener("click", closeReturnModal);
  if (returnCancel) returnCancel.addEventListener("click", closeReturnModal);
  if (returnModal) {
    returnModal.addEventListener("click", (e) => {
      if (e.target === returnModal) closeReturnModal();
    });
  }
  if (returnForm) {
    returnForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      returnError.style.display = "none";
      const message = (returnMessage.value || "").trim();
      if (!message) {
        returnError.textContent = "Please explain what to fix.";
        returnError.style.display = "block";
        return;
      }
      try {
        const res = await api(`/api/tasks/${taskCtx.task.id}/return`, {
          method: "POST",
          body: JSON.stringify({ message }),
        });
        taskCtx.task = (await res.json()).task;
        closeReturnModal();
        renderTaskHeader();
        showToast("Returned to annotator. Returning to dashboard…");
        setTimeout(() => { window.location.href = "/"; }, 900);
      } catch (err) {
        returnError.textContent = err.message || "Return failed.";
        returnError.style.display = "block";
      }
    });
  }
}

function openReturnModal() {
  const m = document.getElementById("return-modal");
  if (m) {
    m.classList.remove("hidden");
    document.getElementById("return-message").focus();
  }
}

async function renderCommentsThread() {
  const thread = document.getElementById("comments-thread");
  if (!thread || !taskCtx.task) return;
  thread.innerHTML = '<div class="comments-empty">Loading…</div>';
  try {
    const res = await api(`/api/tasks/${taskCtx.task.id}/events`);
    const events = (await res.json()).events || [];
    if (!events.length) {
      thread.innerHTML = '<div class="comments-empty">No activity yet.</div>';
      return;
    }
    thread.innerHTML = "";
    for (const ev of events) {
      const row = document.createElement("div");
      const isComment = ev.event_type === "comment";
      row.className = "comment-row" + (isComment ? "" : " event-row");
      const head = document.createElement("div");
      head.className = "comment-head";
      const who = document.createElement("span");
      who.className = "comment-author";
      who.textContent = ev.actor_username || "system";
      const when = document.createElement("span");
      when.className = "comment-time";
      when.textContent = formatEventTime(ev.created_at);
      head.appendChild(who);
      head.appendChild(when);
      const body = document.createElement("div");
      body.className = "comment-body";
      body.textContent = isComment
        ? (ev.message || "")
        : `· ${ev.event_type}${ev.message ? ` — ${ev.message}` : ""}`;
      row.appendChild(head);
      row.appendChild(body);
      thread.appendChild(row);
    }
    thread.scrollTop = thread.scrollHeight;
  } catch (err) {
    thread.innerHTML = `<div class="comments-empty">Failed to load: ${escapeHtml(err.message || "")}</div>`;
  }
}

async function refreshCommentCount() {
  if (!taskCtx.task) return;
  const badge = document.getElementById("task-comment-count");
  if (!badge) return;
  try {
    const res = await api(`/api/tasks/${taskCtx.task.id}/events`);
    const events = (await res.json()).events || [];
    const n = events.filter((e) => e.event_type === "comment").length;
    badge.textContent = String(n);
    badge.classList.toggle("zero", n === 0);
  } catch { /* ignore */ }
}

function formatEventTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch { return iso; }
}

// ── Bootstrap ────────────────────────────────────────────────────────────────
(async function bootstrap() {
  // Annotation canvas: pointer-events off until draw mode activated
  annotationCanvas.style.pointerEvents = "none";
  imageCanvasWrap.style.display = "none";

  // Probe SAM2 availability in parallel with the rest of init so the
  // 🪄 button enables itself as soon as the server confirms it has the
  // model loaded. Errors here are non-fatal — the button just stays
  // disabled with the failure reason on hover.
  probeSam2Availability().catch(() => { /* already handled */ });

  // Task-detail mode (preferred): the page was rendered as /tasks/{id}.
  if (window.__rating_ui_task && window.__rating_ui_task.task_id) {
    try { await initFromTask(window.__rating_ui_task); }
    catch (err) { showToast(err.message || "Task init failed."); }
    return;
  }

  // Legacy standalone fallback (kept for any direct hits to / before P4).
  const savedFolder = localStorage.getItem("rating-ui:last-folder");
  if (!savedFolder) { render(); return; }

  try {
    await loadFolder(savedFolder);
  } catch {
    localStorage.removeItem("rating-ui:last-folder");
    render();
  }
})();




