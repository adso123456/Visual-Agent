const $ = (id) => document.getElementById(id);
const MAX_IMAGES = 32;
let selectedFiles = [];
let activeJobs = [];
let pollTimer = null;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[char]));
}

function setRunStatus(state, label, message) {
  const node = $("runStatus");
  node.dataset.state = state;
  node.innerHTML = `<span class="status-dot"></span><strong>${escapeHtml(label)}</strong><span>${escapeHtml(message)}</span>`;
}

$("addButton").addEventListener("click", () => $("fileInput").click());
$("clearButton").addEventListener("click", clearFiles);
$("batchTray").addEventListener("click", (event) => {
  if (event.target.closest("button")) return;
  $("fileInput").click();
});
$("batchTray").addEventListener("dragover", (event) => { event.preventDefault(); $("dropzone").classList.add("drag"); });
$("batchTray").addEventListener("dragleave", () => $("dropzone").classList.remove("drag"));
$("batchTray").addEventListener("drop", (event) => {
  event.preventDefault();
  $("dropzone").classList.remove("drag");
  if (event.dataTransfer.files.length) addFiles(event.dataTransfer.files);
});
$("fileInput").addEventListener("change", (event) => {
  if (event.target.files.length) addFiles(event.target.files);
  event.target.value = "";
});
$("trayGrid").addEventListener("click", (event) => {
  const remove = event.target.closest(".thumb-remove");
  if (remove) {
    removeFileAt(Number(remove.dataset.index));
    return;
  }
  if (event.target.closest("img")) openViewer({
    src: event.target.src,
    alt: "上传图片预览",
  });
});

function addFiles(files) {
  // 追加模式，去重（文件名+大小+修改时间），并限制 32 张上限
  const added = Array.from(files);
  const seen = new Set(selectedFiles.map((file) => `${file.name}|${file.size}|${file.lastModified}`));
  let overflow = 0;
  for (const file of added) {
    if (selectedFiles.length >= MAX_IMAGES) { overflow++; continue; }
    const key = `${file.name}|${file.size}|${file.lastModified}`;
    if (!seen.has(key)) {
      selectedFiles.push(file);
      seen.add(key);
    }
  }
  renderTray();
  if (overflow > 0 || selectedFiles.length === MAX_IMAGES) {
    setRunStatus("queued", "提示", `一次最多上传 ${MAX_IMAGES} 张图片。`);
  }
}

function removeFileAt(index) {
  selectedFiles.splice(index, 1);
  renderTray();
}

function clearFiles() {
  selectedFiles = [];
  renderTray();
}

function renderTray() {
  const count = selectedFiles.length;
  $("trayCount").textContent = `已选择 ${count} / ${MAX_IMAGES} 张`;
  $("clearButton").hidden = count === 0;
  $("dropzone").hidden = count > 0;
  $("trayGrid").hidden = count === 0;
  $("trayGrid").innerHTML = selectedFiles.map((file, index) => {
    const url = URL.createObjectURL(file);
    return `
      <div class="tray-thumb tray-queued">
        <img src="${url}" alt="缩略图 ${index + 1}" title="${escapeHtml(file.name)}">
        <span class="thumb-index">${String(index + 1).padStart(2, "0")}</span>
        <span class="thumb-status">○</span>
        <button type="button" class="thumb-remove" data-index="${index}" aria-label="移除第 ${index + 1} 张">×</button>
      </div>`;
  }).join("");
}

async function run() {
  const prompt = $("promptInput").value.trim();
  if (!selectedFiles.length) return setRunStatus("error", "错误", "请选择一张或多张图片。");
  if (!prompt) return setRunStatus("error", "错误", "请输入任务指令。");

  const form = new FormData();
  selectedFiles.forEach((file) => form.append("image", file));
  form.append("prompt", prompt);
  $("runButton").disabled = true;
  $("results").hidden = true;
  $("jobList").innerHTML = "";
  setRunStatus("queued", "已排队", "正在提交任务……");
  try {
    const response = await fetch("/api/run_batch", {method: "POST", body: form});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "请求失败");
    activeJobs = [];
    data.jobs.forEach((job, index) => {
      if (!job.job_id) return;
      activeJobs.push({index, job_id: job.job_id, image: job.image, status: "queued"});
    });
    if (!activeJobs.length) throw new Error("没有图片成功提交");
    markTrayQueued();
    renderJobEntries();
    startPolling();
  } catch (error) {
    $("runButton").disabled = false;
    setRunStatus("error", "错误", error.message);
  }
}

function markTrayQueued() {
  // 把缩略图标记为等待（按上传顺序对应 job 序号）
  const thumbs = document.querySelectorAll(".tray-thumb");
  thumbs.forEach((thumb) => {
    thumb.classList.remove("tray-running", "tray-done", "tray-failed");
    thumb.classList.add("tray-queued");
  });
  const count = activeJobs.length;
  if (count > 1) {
    $("progressBlock").hidden = false;
  } else {
    $("progressBlock").hidden = true; // 单图保持简单状态机，不做百分比
  }
}

function renderJobEntries() {
  $("jobList").innerHTML = "";
  activeJobs.forEach((job) => renderJobEntry(job));
}

function jobRowId(jobId) {
  return `job-${jobId}`;
}

function renderJobEntry(job) {
  const row = document.createElement("div");
  row.className = "job-row";
  row.id = jobRowId(job.job_id);
  row.innerHTML = `
    <div class="job-row-head"><strong>${String(job.index + 1).padStart(2, "0")} · ${escapeHtml(job.image)}</strong><span class="job-status">排队中</span></div>
    <div class="image-compare">
      <figure><figcaption>原始图片</figcaption><div class="image-frame"><img data-original="/api/job/${job.job_id}/original" class="interactive-image" alt="原始图片" title="点击放大"></div></figure>
      <figure><figcaption>结果图片</figcaption><div class="image-frame"><img data-result class="interactive-image" alt="结果图片" title="点击放大"></div></figure>
    </div>`;
  $("jobList").appendChild(row);
}

function updateTrayStatus(index, status) {
  const thumb = document.querySelectorAll(".tray-thumb")[index];
  if (!thumb) return;
  thumb.classList.remove("tray-queued", "tray-running", "tray-done", "tray-failed");
  thumb.classList.add(`tray-${status}`);
  const badge = thumb.querySelector(".thumb-status");
  if (badge) badge.textContent = status === "done" ? "✓" : (status === "failed" ? "✕" : (status === "running" ? "●" : "○"));
}

function renderJobResult(jobId, data) {
  const row = $(jobRowId(jobId));
  if (!row) return;
  const original = row.querySelector("img[data-original]");
  original.src = data.result_image
    ? `/api/job/${jobId}/original`
    : "";
  const result = row.querySelector("img[data-result]");
  if (data.status === "done") {
    result.src = `/api/job/${jobId}/${data.result_image}`;
    row.querySelector(".job-status").textContent = `已完成 · ${data.summary?.targets_count ?? 0} 个目标`;
  } else if (data.status === "error") {
    row.querySelector(".job-status").textContent = `失败：${data.error || "未知错误"}`;
    row.querySelector(".job-status").classList.add("job-status-error");
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  const poll = async () => {
    for (const job of activeJobs) {
      try {
        const response = await fetch(`/api/status/${job.job_id}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "状态查询失败");
        job.status = data.status;
        if (data.status === "queued") { updateTrayStatus(job.index, "queued"); continue; }
        if (data.status === "running") {
          updateTrayStatus(job.index, "running");
          $(jobRowId(job.job_id))?.querySelector(".job-status")?.replaceChildren(document.createTextNode("运行中"));
          continue;
        }
        updateTrayStatus(job.index, data.status === "done" ? "done" : "failed");
        renderJobResult(job.job_id, data);
      } catch (error) {
        job.status = "failed";
        updateTrayStatus(job.index, "failed");
        const row = $(jobRowId(job.job_id));
        if (row) row.querySelector(".job-status").textContent = `查询失败：${error.message}`;
      }
    }
    updateProgress();
    if (activeJobs.every((job) => job.status === "done" || job.status === "failed")) {
      clearInterval(pollTimer);
      pollTimer = null;
      $("runButton").disabled = false;
      $("results").hidden = false;
      const failed = activeJobs.filter((job) => job.status === "failed").length;
      const summary = failed
        ? `完成 ${activeJobs.length - failed} 张，失败 ${failed} 张。`
        : `全部完成，共 ${activeJobs.length} 张。`;
      setRunStatus("completed", "已完成", summary);
      $("results").scrollIntoView({behavior: "smooth", block: "start"});
      if (activeJobs.length > 1) {
        $("progressLabel").textContent = `已完成 ${activeJobs.length} / ${activeJobs.length}`;
        $("progressPercent").textContent = "100%";
        $("progressFill").style.width = "100%";
        $("progressMeta").textContent = `已完成 ${activeJobs.filter((j) => j.status === "done").length}    处理中 0    等待 0    失败 ${failed}`;
      }
    }
  };
  poll();
  pollTimer = setInterval(poll, 1500);
}

function updateProgress() {
  if (activeJobs.length <= 1 || $("progressBlock").hidden) return;
  const total = activeJobs.length;
  const failed = activeJobs.filter((job) => job.status === "failed").length;
  const done = activeJobs.filter((job) => job.status === "done").length;
  const running = activeJobs.filter((job) => job.status === "running").length;
  const queued = activeJobs.filter((job) => job.status === "queued").length;
  const completed = done + failed; // 已完成 = success + failed（都终止了）
  const progress = Math.round((completed / total) * 100);
  const current = activeJobs.find((job) => job.status === "running") || activeJobs.find((job) => job.status === "queued");
  $("progressLabel").textContent = running ? `正在处理 ${completed + 1} / ${total}` : `已完成 ${completed} / ${total}`;
  $("progressPercent").textContent = `${Math.min(progress, 99)}%`;
  $("progressFill").style.width = `${Math.min(progress, 99)}%`;
  $("progressMeta").textContent = `已完成 ${done}    处理中 ${running}    等待 ${queued}    失败 ${failed}`;
  $("progressCurrent").textContent = current ? `当前：${current.image}` : "";
}

$("runButton").addEventListener("click", run);
$("promptInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) run();
});

const viewer = {
  scale: 1,
  x: 0,
  y: 0,
  dragging: false,
  pointerId: null,
  lastX: 0,
  lastY: 0,
};

function updateViewerTransform() {
  $("viewerImage").style.transform = `translate(${viewer.x}px, ${viewer.y}px) scale(${viewer.scale})`;
  $("viewerStage").style.cursor = viewer.dragging ? "grabbing" : (viewer.scale > 1 ? "grab" : "default");
}

function resetViewer() {
  viewer.scale = 1;
  viewer.x = 0;
  viewer.y = 0;
  viewer.dragging = false;
  viewer.pointerId = null;
  $("viewerStage").classList.remove("dragging");
  updateViewerTransform();
}

function openViewer(image) {
  $("viewerImage").src = image.src;
  $("viewerImage").alt = `${image.alt}放大预览`;
  $("imageViewer").hidden = false;
  document.body.classList.add("viewer-open");
  resetViewer();
  $("viewerClose").focus();
}

function closeViewer() {
  $("imageViewer").hidden = true;
  document.body.classList.remove("viewer-open");
  $("viewerImage").removeAttribute("src");
  resetViewer();
}

document.addEventListener("click", (event) => {
  if (event.target.classList.contains("interactive-image") && event.target.src) {
    openViewer(event.target);
  }
});

$("viewerClose").addEventListener("click", closeViewer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("imageViewer").hidden) closeViewer();
});

$("viewerStage").addEventListener("wheel", (event) => {
  event.preventDefault();
  const nextScale = Math.min(8, Math.max(1, viewer.scale * (event.deltaY < 0 ? 1.15 : 1 / 1.15)));
  if (nextScale === viewer.scale) return;
  const rect = $("viewerStage").getBoundingClientRect();
  const pointerX = event.clientX - (rect.left + rect.width / 2);
  const pointerY = event.clientY - (rect.top + rect.height / 2);
  const ratio = nextScale / viewer.scale;
  viewer.x = pointerX - (pointerX - viewer.x) * ratio;
  viewer.y = pointerY - (pointerY - viewer.y) * ratio;
  viewer.scale = nextScale;
  if (viewer.scale === 1) {
    viewer.x = 0;
    viewer.y = 0;
  }
  updateViewerTransform();
}, {passive: false});

$("viewerStage").addEventListener("pointerdown", (event) => {
  if (viewer.scale <= 1) return;
  viewer.dragging = true;
  viewer.pointerId = event.pointerId;
  viewer.lastX = event.clientX;
  viewer.lastY = event.clientY;
  $("viewerStage").setPointerCapture(event.pointerId);
  $("viewerStage").classList.add("dragging");
});

$("viewerStage").addEventListener("pointermove", (event) => {
  if (!viewer.dragging || event.pointerId !== viewer.pointerId) return;
  viewer.x += event.clientX - viewer.lastX;
  viewer.y += event.clientY - viewer.lastY;
  viewer.lastX = event.clientX;
  viewer.lastY = event.clientY;
  updateViewerTransform();
});

function stopViewerDrag(event) {
  if (!viewer.dragging || event.pointerId !== viewer.pointerId) return;
  viewer.dragging = false;
  viewer.pointerId = null;
  $("viewerStage").classList.remove("dragging");
  updateViewerTransform();
}

$("viewerStage").addEventListener("pointerup", stopViewerDrag);
$("viewerStage").addEventListener("pointercancel", stopViewerDrag);
$("viewerStage").addEventListener("dblclick", resetViewer);