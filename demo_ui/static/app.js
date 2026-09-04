const $ = (id) => document.getElementById(id);
let selectedFile = null;
let jobId = null;
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
  if (event.dataTransfer.files.length) setFile(event.dataTransfer.files[0]);
});
$("fileInput").addEventListener("change", (event) => { if (event.target.files.length) setFile(event.target.files[0]); });

function setFile(file) {
  selectedFile = file;
  $("preview").src = URL.createObjectURL(file);
  $("preview").hidden = false;
  $("dropzoneText").textContent = `${file.name} · 点击替换`;
}

async function run() {
  const prompt = $("promptInput").value.trim();
  if (!selectedFile) return setRunStatus("error", "错误", "请选择一张图片。");
  if (!prompt) return setRunStatus("error", "错误", "请输入任务指令。");

  const form = new FormData();
  form.append("image", selectedFile);
  form.append("prompt", prompt);
  $("runButton").disabled = true;
  $("results").hidden = true;
  setRunStatus("queued", "已排队", "正在等待 Visual Agent 执行进程。");
  try {
    const response = await fetch("/api/run", {method: "POST", body: form});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "请求失败");
    jobId = data.job_id;
    startPolling();
  } catch (error) {
    $("runButton").disabled = false;
    setRunStatus("error", "错误", error.message);
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  const poll = async () => {
    try {
      const response = await fetch(`/api/status/${jobId}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "状态查询失败");
      if (data.status === "queued") return setRunStatus("queued", "已排队", "正在等待 Visual Agent 执行进程。");
      if (data.status === "running") return setRunStatus("running", "运行中", "Visual Agent 正在执行任务……");
      clearInterval(pollTimer);
      $("runButton").disabled = false;
      if (data.status === "error") return setRunStatus("error", "错误", data.error || "未知错误");
      if (data.status === "done") {
        setRunStatus("completed", "已完成", `共得到 ${data.summary.targets_count} 个最终目标。`);
        renderResult(data);
      }
    } catch (error) {
      clearInterval(pollTimer);
      $("runButton").disabled = false;
      setRunStatus("error", "错误", error.message);
    }
  };
  poll();
  pollTimer = setInterval(poll, 1200);
}

function renderResult(data) {
  $("results").hidden = false;
  $("originalImage").src = `/api/job/${data.id}/original`;
  $("resultImage").src = `/api/job/${data.id}/${data.result_image}`;
  $("results").scrollIntoView({behavior: "smooth", block: "start"});
}

$("runButton").addEventListener("click", run);

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

document.querySelectorAll(".interactive-image").forEach((image) => {
  image.addEventListener("click", () => openViewer(image));
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