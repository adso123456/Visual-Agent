const EXAMPLES = [
  {
    prompt: "只给穿红色衣服的人描边",
    plan: {target_object: "person", label: "穿红色衣服的人", constraints: [{text: "穿红色衣服", route: "attribute"}], action: {type: "outline"}, related_objects: []},
  },
  {
    prompt: "把拿雨伞的人单独抠出来",
    plan: {target_object: "person", label: "拿雨伞的人", constraints: [{text: "手持雨伞", route: "relation"}], action: {type: "cutout"}, related_objects: [{object: "umbrella", relation: "held_by_target"}]},
  },
  {
    prompt: "把正在钓鱼的人高亮",
    plan: {target_object: "person", label: "正在钓鱼的人", constraints: [{text: "正在钓鱼", route: "behavior"}], action: {type: "highlight"}, related_objects: []},
  },
];

const $ = (id) => document.getElementById(id);
let mode = "full_chain";
let selectedFile = null;
let selectedPlan = EXAMPLES[0].plan;
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

function selectExample(example) {
  selectedPlan = example.plan;
  $("promptInput").value = example.prompt;
  if (mode === "local_debug") {
    $("planInput").value = JSON.stringify(example.plan, null, 2);
  }
}

EXAMPLES.forEach((example) => {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "example";
  button.textContent = example.prompt;
  button.addEventListener("click", () => selectExample(example));
  $("examples").appendChild(button);
});

function setMode(nextMode) {
  mode = nextMode;
  $("modeSwitch").querySelectorAll("button").forEach((button) => button.classList.toggle("active", button.dataset.mode === mode));
  const local = mode === "local_debug";
  $("planInput").classList.toggle("visible", local);
  if (local && !$("planInput").value.trim()) $("planInput").value = JSON.stringify(selectedPlan, null, 2);
  const banner = $("modeBanner");
  banner.className = `mode-banner ${local ? "local-debug" : "full-chain"}`;
  banner.innerHTML = local
    ? "<strong>本地调试</strong><span>⚠ 预编译计划 · Detector → SAM2 → 动作执行</span><small>Agent：已跳过 · Qwen 语义验证：已跳过</small>"
    : "<strong>通用视觉链路</strong><span>自然语言 → Agent 规划 → 开放词汇定位 → 视觉证据路由 → 语义 / 关系验证 → 精确分割 → 动作执行</span>";
  $("modeHint").textContent = local
    ? "本地调试使用预编译计划，不代表完整的 Agent/VLM 链路。"
    : "通用视觉链路使用 Agent 规划与视觉证据路由完成语义 / 关系验证。";
}

$("modeSwitch").querySelectorAll("button").forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
setMode("full_chain");

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
  const plan = mode === "local_debug" ? $("planInput").value.trim() : "";
  if (mode === "local_debug" && !plan) return setRunStatus("error", "错误", "本地调试需要预编译计划。");

  const form = new FormData();
  form.append("image", selectedFile);
  form.append("prompt", prompt);
  if (plan) form.append("plan", plan);
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

function statusTag(status) {
  const known = ["satisfied", "not_satisfied", "uncertain", "skipped", "not_applicable"];
  const safe = known.includes(status) ? status : "uncertain";
  const labels = {satisfied: "满足", not_satisfied: "不满足", uncertain: "不确定", skipped: "已跳过", not_applicable: "N/A"};
  const label = labels[safe];
  return `<span class="tag ${safe}">${escapeHtml(label)}</span>`;
}

function renderResult(data) {
  const summary = data.summary;
  $("results").hidden = false;
  $("originalImage").src = `/api/job/${data.id}/original`;
  $("resultImage").src = `/api/job/${data.id}/${data.result_image}`;
  $("candidateOverlay").src = `/api/job/${data.id}/candidates.png`;
  $("artifactLinks").innerHTML = `<a href="/api/job/${data.id}/candidates.png" target="_blank">打开 candidates.png</a><a href="/api/job/${data.id}/${escapeHtml(data.result_json)}" target="_blank">打开结果 JSON</a>`;

  const plan = summary.plan;
  const planItems = [
    ["目标对象", plan.target_object],
    ["语义约束", plan.constraints?.length ? plan.constraints.map((item) => `${item.text} · ${item.route}`).join("\n") : "N/A"],
    ["关联对象", plan.related_objects?.length ? JSON.stringify(plan.related_objects) : "N/A"],
    ["执行动作", plan.action?.type ? `${plan.action.type}${plan.action.color ? ` · ${plan.action.color}` : ""}` : "N/A"],
  ];
  $("planSummary").innerHTML = planItems.map(([key, value]) => `<div class="datum"><small>${escapeHtml(key)}</small><code>${escapeHtml(value)}</code></div>`).join("");
  $("agentResponse").hidden = !summary.agent_response;
  $("agentResponse").textContent = summary.agent_response || "";

  $("candidateCount").textContent = `${summary.candidates_count} 个原始候选目标`;
  $("candidateRows").innerHTML = summary.candidates.length
    ? summary.candidates.map((candidate) => `<tr><td><code>${escapeHtml(candidate.id)}</code></td><td>${escapeHtml(candidate.label ?? "N/A")}</td><td><code>${candidate.confidence == null ? "N/A" : escapeHtml(candidate.confidence)}</code></td><td>${statusTag(candidate.verification_status)}</td></tr>`).join("")
    : '<tr><td colspan="4" class="empty">Detector 未返回候选目标</td></tr>';

  const localDebug = data.mode === "local_debug";
  $("semanticNotice").textContent = localDebug
    ? "已跳过——本地调试不执行语义 / 关系验证。"
    : "下方状态和证据直接读取自 Pipeline 结果。";
  const semanticRows = [];
  summary.candidates.forEach((candidate) => {
    if (candidate.verification_checks.length) {
      candidate.verification_checks.forEach((check) => semanticRows.push(`<tr><td><code>${escapeHtml(candidate.id)}</code></td><td>${escapeHtml(check.constraint ?? "N/A")}</td><td>${statusTag(check.status)}</td><td>${escapeHtml(check.evidence ?? "N/A")}</td></tr>`));
    } else {
      semanticRows.push(`<tr><td><code>${escapeHtml(candidate.id)}</code></td><td>N/A</td><td>${statusTag(localDebug ? "skipped" : candidate.verification_status)}</td><td>${escapeHtml(candidate.verification_reason || "N/A")}</td></tr>`);
    }
  });
  $("semanticRows").innerHTML = semanticRows.length ? semanticRows.join("") : '<tr><td colspan="4" class="empty">没有需要验证的候选目标</td></tr>';
  renderRelations(summary.relation_bindings);

  $("targetCount").textContent = `${summary.targets_count} 个最终目标`;
  $("targetRows").innerHTML = summary.targets.length
    ? summary.targets.map((target) => {
      const relation = target.relation ? `${target.relation.related_id} · ${target.relation.status}` : "N/A";
      return `<tr><td><code>${escapeHtml(target.id)}</code></td><td>${escapeHtml(target.label)}</td><td>${escapeHtml(target.verification_reason || "N/A")}</td><td>${escapeHtml(relation)}</td><td><code>${target.mask_score ?? "N/A"}</code></td><td><code>${target.mask_area_pixels ?? "N/A"}</code></td></tr>`;
    }).join("")
    : '<tr><td colspan="6" class="empty">最终目标为 0——这是有效的负向结果，并非系统错误。</td></tr>';
  renderTimings(summary.timings);
  $("results").scrollIntoView({behavior: "smooth", block: "start"});
}

function renderRelations(bindings) {
  if (!bindings.length) {
    $("relationBlock").innerHTML = "";
    return;
  }
  const rows = bindings.map((binding) => `<tr><td>${escapeHtml(binding.subject_id)}</td><td>${escapeHtml(binding.related_id)}</td><td>${statusTag(binding.status)}</td><td>${escapeHtml(binding.evidence)}</td></tr>`).join("");
  $("relationBlock").innerHTML = `<div class="relation"><h3>关系验证</h3><div class="table-wrap"><table class="relation-table"><thead><tr><th>主体</th><th>关联对象</th><th>状态</th><th>证据</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}

function renderTimings(timings) {
  const labels = {
    deepseek_plan_seconds: "Agent 规划",
    "detector.model": "Detector 模型",
    "detector.device": "运行设备",
    "detector.load_seconds": "Detector 加载",
    "detector.cached": "Detector 缓存",
    "detector.memory_after_load_mb": "Detector 内存",
    grounding_dino_seconds: "目标检测",
    group_verification_seconds: "语义验证",
    relation_grounding_seconds: "关系目标检测",
    relation_verification_seconds: "关系验证",
    sam2: "SAM2",
    deepseek_final_response_seconds: "最终回答",
    total_seconds: "总耗时",
  };
  const items = [];
  Object.entries(timings || {}).forEach(([key, value]) => {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      Object.entries(value).forEach(([child, childValue]) => items.push([`${key}.${child}`, childValue]));
    } else {
      items.push([key, value]);
    }
  });
  $("timingGrid").innerHTML = items.length
    ? items.map(([key, value]) => {
      let displayValue = value ?? "N/A";
      if (typeof value === "number" && key.endsWith("_seconds")) displayValue = `${value.toFixed(3)} 秒`;
      if (typeof value === "number" && key.endsWith("_mb")) displayValue = `${value.toFixed(1)} MB`;
      if (typeof value === "boolean") displayValue = value ? "是" : "否";
      return `<div class="timing-item"><span>${escapeHtml(labels[key] || key)}</span><code>${escapeHtml(displayValue)}</code></div>`;
    }).join("")
    : '<div class="empty">结果中没有耗时字段。</div>';
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
