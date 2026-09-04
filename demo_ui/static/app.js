const $ = (id) => document.getElementById(id);
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

const dropzone = $("dropzone");
dropzone.addEventListener("click", () => $("fileInput").click());
dropzone.addEventListener("dragover", (event) => { event.preventDefault(); dropzone.classList.add("drag"); });
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag"));
dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("drag");
  if (event.dataTransfer.files.length) setFiles(event.dataTransfer.files);
});
$("fileInput").addEventListener("change", (event) => { if (event.target.files.length) addFilesFromPicker(); });
$("clearButton").addEventListener("click", (event) => { event.stopPropagation(); clearFiles(); });

function setFiles(files) {
  // 追加模式：多次选择/拖拽都累积到列表，而不是替换上一张
  const added = Array.from(files);
  const seen = new Set(selectedFiles.map((file) => `${file.name}|${file.size}|${file.lastModified}`));
  for (const file of added) {
    const key = `${file.name}|${file.size}|${file.lastModified}`;
    if (!seen.has(key)) {
      selectedFiles.push(file);
      seen.add(key);
    }
  }
  updateDropzone();
}

async function addFilesFromPicker() {
  const input = $("fileInput");
  const picked = input.files;
  if (picked && picked.length) {
    setFiles(picked);
    input.value = "";
  }
}

function clearFiles() {
  selectedFiles = [];
  updateDropzone();
}

function updateDropzone() {
  const count = selectedFiles.length;
  if (count === 0) {
    $("preview").removeAttribute("src");
    $("preview").hidden = true;
    $("dropzoneText").textContent = "点击选择或将图片拖到此处";
    $("clearButton").hidden = true;
    return;
  }
  $("preview").src = URL.createObjectURL(selectedFiles[0]);
  $("preview").hidden = false;
  $("clearButton").hidden = false;
  $("dropzoneText").textContent = count === 1
    ? `${selectedFiles[0].name} · 点击继续添加`
    : `已选择 ${count} 张图片 · 点击继续添加`;
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
    activeJobs = data.jobs.filter((job) => job.job_id);
    if (!activeJobs.length) throw new Error("没有图片成功提交");
    activeJobs.forEach((job) => renderJobEntry(job));
    startPolling();
  } catch (error) {
    $("runButton").disabled = false;
    setRunStatus("error", "错误", error.message);
  }
}

function jobRowId(jobId) {
  return `job-${jobId}`;
}

function renderJobEntry(job) {
  const row = document.createElement("div");
  row.className = "job-row";
  row.id = jobRowId(job.job_id);
  row.innerHTML = `
    <div class="job-row-head"><strong>${escapeHtml(job.image)}</strong><span class="job-status">排队中</span></div>
    <div class="image-compare">
      <figure><figcaption>原始图片</figcaption><div class="image-frame"><img data-original="/api/job/${job.job_id}/original" class="interactive-image" alt="原始图片" title="点击放大"></div></figure>
      <figure><figcaption>结果图片</figcaption><div class="image-frame"><img data-result class="interactive-image" alt="结果图片" title="点击放大"></div></figure>
    </div>`;
  $("jobList").appendChild(row);
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
    let pending = 0;
    for (const job of activeJobs) {
      try {
        const response = await fetch(`/api/status/${job.job_id}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "状态查询失败");
        if (data.status === "queued") { pending++; continue; }
        if (data.status === "running") {
          pending++;
          const row = $(jobRowId(job.job_id));
          if (row) row.querySelector(".job-status").textContent = "运行中";
          continue;
        }
        renderJobResult(job.job_id, data);
      } catch (error) {
        pending++;
        const row = $(jobRowId(job.job_id));
        if (row) row.querySelector(".job-status").textContent = `查询失败：${error.message}`;
      }
    }
    if (pending === 0) {
      clearInterval(pollTimer);
      pollTimer = null;
      $("runButton").disabled = false;
      $("results").hidden = false;
      const failed = activeJobs.filter((job) => $(jobRowId(job.job_id))?.querySelector(".job-status-error"));
      const summary = failed.length
        ? `完成 ${activeJobs.length - failed.length} 张，失败 ${failed.length} 张。`
        : `全部完成，共 ${activeJobs.length} 张。`;
      setRunStatus("completed", "已完成", summary);
      $("results").scrollIntoView({behavior: "smooth", block: "start"});
    }
  };
  poll();
  pollTimer = setInterval(poll, 1500);
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