const state = {
  session: null,
  activeFilter: "unreviewed",
  currentRelativePath: null,
  toastTimer: null,
  uiSaveTimer: null,
  targetSaveTimer: null,
};

const folderPathInput = document.getElementById("folder-path-input");
const targetFolderPathInput = document.getElementById("target-folder-path-input");
const saveTargetFolderBtn = document.getElementById("save-target-folder-btn");
const chooseTargetFolderBtn = document.getElementById("choose-target-folder-btn");
const chooseFolderBtn = document.getElementById("choose-folder-btn");
const importFolderBtn = document.getElementById("import-folder-btn");
const browserFolderInput = document.getElementById("browser-folder-input");
const loadFolderBtn = document.getElementById("load-folder-btn");
const exportBtn = document.getElementById("export-btn");
const exportFilenamesBtn = document.getElementById("export-filenames-btn");
const progressCount = document.getElementById("progress-count");
const progressPercent = document.getElementById("progress-percent");
const selectedCount = document.getElementById("selected-count");
const correctCount = document.getElementById("correct-count");
const progressBar = document.getElementById("progress-bar");
const queueMeta = document.getElementById("queue-meta");
const queueList = document.getElementById("queue-list");
const viewerTitle = document.getElementById("viewer-title");
const viewerSubtitle = document.getElementById("viewer-subtitle");
const mainImage = document.getElementById("main-image");
const imageStage = document.getElementById("image-stage");
const currentStatus = document.getElementById("current-status");
const reviewedAt = document.getElementById("reviewed-at");
const prevBtn = document.getElementById("prev-btn");
const nextBtn = document.getElementById("next-btn");
const markCorrectBtn = document.getElementById("mark-correct-btn");
const markWrongBtn = document.getElementById("mark-wrong-btn");
const clearBtn = document.getElementById("clear-btn");
const toast = document.getElementById("toast");

async function api(url, options = {}) {
  const isFormData = options.body instanceof FormData;
  const headers = { ...(options.headers || {}) };
  if (!isFormData && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(url, {
    headers,
    ...options,
  });

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
  state.toastTimer = window.setTimeout(() => {
    toast.classList.remove("visible");
  }, 2600);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function filterImages(images, filterMode) {
  if (filterMode === "reviewed") {
    return images.filter((item) => item.reviewed);
  }
  if (filterMode === "unreviewed") {
    return images.filter((item) => !item.reviewed);
  }
  if (filterMode === "selected") {
    return images.filter((item) => item.selected);
  }
  return images;
}

function normalizeFilterMode(filterMode) {
  if (filterMode === "reviewed" || filterMode === "selected") {
    return filterMode;
  }
  return "unreviewed";
}

function currentImage() {
  if (!state.session) {
    return null;
  }

  const images = filterImages(state.session.images, state.activeFilter);
  if (!images.length) {
    return null;
  }

  return images.find((item) => item.relative_path === state.currentRelativePath) || images[0];
}

function updateFilterButtons() {
  document.querySelectorAll("[data-filter]").forEach((button) => {
    button.classList.toggle("active", button.dataset.filter === state.activeFilter);
  });
}

function statusLabel(decision) {
  if (decision === "correct") {
    return "Correct";
  }
  if (decision === "wrong") {
    return "Wrong / Selected";
  }
  return "Unreviewed";
}

function statusClass(decision) {
  if (decision === "correct") {
    return "status-correct";
  }
  if (decision === "wrong") {
    return "status-wrong";
  }
  return "status-unreviewed";
}

function queueBadge(decision) {
  if (decision === "correct") {
    return '<span class="badge-soft badge-correct">Correct</span>';
  }
  if (decision === "wrong") {
    return '<span class="badge-soft badge-wrong">Selected</span>';
  }
  return '<span class="badge-soft badge-unreviewed">Unreviewed</span>';
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

  queueList.innerHTML = filtered
    .map((item, index) => {
      const isActive = item.relative_path === state.currentRelativePath;
      return `
        <button class="queue-item ${isActive ? "active" : ""}" data-relative-path="${encodeURIComponent(item.relative_path)}" type="button">
          <span class="queue-title">${index + 1}. ${escapeHtml(item.filename)}</span>
          <span class="queue-path">${escapeHtml(item.relative_path)}</span>
          <div class="queue-badges">${queueBadge(item.decision)}</div>
        </button>
      `;
    })
    .join("");

  queueList.querySelectorAll(".queue-item").forEach((button) => {
    button.addEventListener("click", () => {
      state.currentRelativePath = decodeURIComponent(button.dataset.relativePath);
      render();
      persistUiState();
    });
  });
}

function renderViewer() {
  const image = currentImage();
  const filtered = state.session ? filterImages(state.session.images, state.activeFilter) : [];
  const currentIndex = filtered.findIndex((item) => item.relative_path === state.currentRelativePath);
  const hasImage = Boolean(image);

  viewerTitle.textContent = hasImage ? image.filename : "No image in current filter";
  viewerSubtitle.textContent = state.session
    ? `${state.session.folder_path} | ${filtered.length} items in ${state.activeFilter} view`
    : "Keyboard shortcuts: A/D navigate, C correct, W wrong, U reset.";

  prevBtn.disabled = !hasImage || currentIndex <= 0;
  nextBtn.disabled = !hasImage || currentIndex === -1 || currentIndex >= filtered.length - 1;
  markCorrectBtn.disabled = !hasImage;
  markWrongBtn.disabled = !hasImage;
  clearBtn.disabled = !hasImage;

  if (!hasImage) {
    imageStage.classList.remove("ready");
    mainImage.removeAttribute("src");
    currentStatus.textContent = "Unreviewed";
    currentStatus.className = "status-pill status-unreviewed";
    reviewedAt.textContent = "No review timestamp";
    return;
  }

  imageStage.classList.add("ready");
  mainImage.src = image.image_url;
  mainImage.alt = image.relative_path;
  currentStatus.textContent = statusLabel(image.decision);
  currentStatus.className = `status-pill ${statusClass(image.decision)}`;
  reviewedAt.textContent = image.reviewed_at ? `Reviewed at ${image.reviewed_at}` : "No review timestamp";
}

function renderSummary() {
  if (!state.session) {
    progressCount.textContent = "0 / 0";
    progressPercent.textContent = "0%";
    selectedCount.textContent = "0";
    correctCount.textContent = "0";
    progressBar.style.width = "0%";
    exportBtn.disabled = true;
    exportFilenamesBtn.disabled = true;
    chooseTargetFolderBtn.disabled = true;
    saveTargetFolderBtn.disabled = true;
    targetFolderPathInput.disabled = true;
    return;
  }

  const { summary } = state.session;
  progressCount.textContent = `${summary.reviewed_count} / ${summary.total_count}`;
  progressPercent.textContent = `${summary.percent_reviewed}%`;
  selectedCount.textContent = summary.selected_count;
  correctCount.textContent = summary.correct_count;
  progressBar.style.width = `${summary.percent_reviewed}%`;
  exportBtn.disabled = summary.selected_count === 0;
  exportFilenamesBtn.disabled = summary.selected_count === 0;
  chooseTargetFolderBtn.disabled = false;
  saveTargetFolderBtn.disabled = false;
  targetFolderPathInput.disabled = false;
}

function render() {
  updateFilterButtons();
  syncCurrentImage();
  renderSummary();
  renderQueue();
  renderViewer();
  if (state.session) {
    folderPathInput.value = state.session.folder_path;
    targetFolderPathInput.value = state.session.target_folder_path || "";
  } else {
    targetFolderPathInput.value = "";
  }
}

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
  const response = await api("/api/select-folder", {
    method: "POST",
    body: "{}",
  });
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
  if (!files.length) {
    throw new Error("No folder was selected.");
  }

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

  const response = await api("/api/import-folder", {
    method: "POST",
    body: formData,
  });
  const payload = await response.json();
  state.session = payload.session;
  state.activeFilter = normalizeFilterMode(state.session.ui_state.filter_mode);
  state.currentRelativePath = state.session.ui_state.current_relative_path;
  localStorage.setItem("rating-ui:last-folder", state.session.folder_path);
  render();
  showToast(`Imported ${payload.imported_count} image(s) from ${rootName}.`);
}

async function updateDecision(decision) {
  const image = currentImage();
  if (!state.session || !image) {
    return;
  }

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

async function saveTargetFolderPath() {
  if (!state.session) {
    throw new Error("Load a prediction folder first.");
  }

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
  if (!state.session) {
    return;
  }

  window.clearTimeout(state.targetSaveTimer);
  state.targetSaveTimer = window.setTimeout(async () => {
    try {
      await saveTargetFolderPath();
    } catch (error) {
      showToast(error.message);
    }
  }, 500);
}

async function chooseTargetFolder() {
  if (!state.session) {
    throw new Error("Load a prediction folder first.");
  }

  const response = await api("/api/select-target-folder", {
    method: "POST",
    body: JSON.stringify({
      folder_path: state.session.folder_path,
    }),
  });
  const payload = await response.json();
  state.session = payload.session;
  render();
}

function navigate(step) {
  if (!state.session) {
    return;
  }
  const filtered = filterImages(state.session.images, state.activeFilter);
  if (!filtered.length) {
    return;
  }

  const currentIndex = Math.max(
    filtered.findIndex((item) => item.relative_path === state.currentRelativePath),
    0,
  );
  const nextIndex = Math.min(Math.max(currentIndex + step, 0), filtered.length - 1);
  state.currentRelativePath = filtered[nextIndex].relative_path;
  render();
  persistUiState();
}

function persistUiState() {
  if (!state.session) {
    return;
  }
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
    } catch (error) {
      showToast(error.message);
    }
  }, 250);
}

async function exportSelection() {
  if (!state.session) {
    return;
  }

  const response = await api("/api/export", {
    method: "POST",
    body: JSON.stringify({ folder_path: state.session.folder_path }),
  });
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
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
  if (!state.session) {
    return;
  }

  const response = await api("/api/export-filenames", {
    method: "POST",
    body: JSON.stringify({ folder_path: state.session.folder_path }),
  });
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
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

chooseFolderBtn.addEventListener("click", async () => {
  try {
    await chooseFolder();
  } catch (error) {
    showToast(error.message);
  }
});

importFolderBtn.addEventListener("click", () => {
  browserFolderInput.click();
});

browserFolderInput.addEventListener("change", async () => {
  try {
    await importBrowserFolder(browserFolderInput.files);
  } catch (error) {
    showToast(error.message);
  } finally {
    browserFolderInput.value = "";
  }
});

loadFolderBtn.addEventListener("click", async () => {
  try {
    const folderPath = folderPathInput.value.trim();
    if (!folderPath) {
      throw new Error("Enter a folder path.");
    }
    await loadFolder(folderPath);
  } catch (error) {
    showToast(error.message);
  }
});

saveTargetFolderBtn.addEventListener("click", async () => {
  try {
    window.clearTimeout(state.targetSaveTimer);
    await saveTargetFolderPath();
    showToast("Saved target image path.");
  } catch (error) {
    showToast(error.message);
  }
});

chooseTargetFolderBtn.addEventListener("click", async () => {
  try {
    await chooseTargetFolder();
    showToast("Selected target image path.");
  } catch (error) {
    showToast(error.message);
  }
});

targetFolderPathInput.addEventListener("input", () => {
  queueTargetFolderAutosave();
});

targetFolderPathInput.addEventListener("blur", async () => {
  if (!state.session) {
    return;
  }

  window.clearTimeout(state.targetSaveTimer);
  try {
    await saveTargetFolderPath();
  } catch (error) {
    showToast(error.message);
  }
});

exportBtn.addEventListener("click", async () => {
  try {
    await exportSelection();
  } catch (error) {
    showToast(error.message);
  }
});

exportFilenamesBtn.addEventListener("click", async () => {
  try {
    await exportSelectionTxt();
  } catch (error) {
    showToast(error.message);
  }
});

markCorrectBtn.addEventListener("click", async () => {
  try {
    await updateDecision("correct");
    showToast("Marked correct.");
  } catch (error) {
    showToast(error.message);
  }
});

markWrongBtn.addEventListener("click", async () => {
  try {
    await updateDecision("wrong");
    showToast("Marked wrong and queued for export.");
  } catch (error) {
    showToast(error.message);
  }
});

clearBtn.addEventListener("click", async () => {
  try {
    await updateDecision("unreviewed");
    showToast("Cleared review state.");
  } catch (error) {
    showToast(error.message);
  }
});

prevBtn.addEventListener("click", () => navigate(-1));
nextBtn.addEventListener("click", () => navigate(1));

document.getElementById("filter-group").addEventListener("click", (event) => {
  const target = event.target.closest("[data-filter]");
  if (!target) {
    return;
  }
  state.activeFilter = target.dataset.filter;
  render();
  persistUiState();
});

window.addEventListener("keydown", async (event) => {
  const activeElement = document.activeElement;
  if (activeElement && ["INPUT", "TEXTAREA"].includes(activeElement.tagName)) {
    return;
  }

  try {
    if (event.key.toLowerCase() === "a" || event.key === "ArrowLeft") {
      navigate(-1);
    } else if (event.key.toLowerCase() === "d" || event.key === "ArrowRight") {
      navigate(1);
    } else if (event.key.toLowerCase() === "c") {
      await updateDecision("correct");
      showToast("Marked correct.");
    } else if (event.key.toLowerCase() === "w") {
      await updateDecision("wrong");
      showToast("Marked wrong and queued for export.");
    } else if (event.key.toLowerCase() === "u") {
      await updateDecision("unreviewed");
      showToast("Cleared review state.");
    }
  } catch (error) {
    showToast(error.message);
  }
});

(async function bootstrap() {
  const savedFolder = localStorage.getItem("rating-ui:last-folder");
  if (!savedFolder) {
    render();
    return;
  }

  try {
    await loadFolder(savedFolder);
  } catch {
    localStorage.removeItem("rating-ui:last-folder");
    render();
  }
})();
