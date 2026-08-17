const EXAMPLES = [
  {
    prompt: "只给穿红色衣服的人描边",
    plan: {target_object: "person", label: "穿红色衣服的人", constraints: ["穿红色衣服"], action: {type: "outline"}, related_objects: []},
  },
  {
    prompt: "把拿雨伞的人单独抠出来",
    plan: {target_object: "person", label: "拿雨伞的人", constraints: ["手持雨伞"], action: {type: "cutout"}, related_objects: [{object: "umbrella", relation: "held_by_target"}]},
  },
  {
    prompt: "把正在钓鱼的人高亮",
    plan: {target_object: "person", label: "正在钓鱼的人", constraints: ["正在钓鱼"], action: {type: "highlight"}, related_objects: []},
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
    ? "<strong>LOCAL DEBUG</strong><span>⚠ Precompiled Plan · Detector → SAM2 → Action</span><small>Agent: SKIPPED · Qwen Semantic Verification: SKIPPED</small>"
    : "<strong>FULL CHAIN</strong><span>Natural Language → Agent → Detector → Qwen → Relation → SAM2 → Action</span><small>Requires DEEPSEEK_API_KEY and DASHSCOPE_API_KEY</small>";
  $("modeHint").textContent = local
    ? "Local Debug uses a precompiled plan and does not represent the complete Agent/VLM chain."
    : "Full Chain uses the natural-language planner and frozen Qwen semantic verification.";
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
  $("dropzoneText").textContent = `${file.name} · click to replace`;
}

async function run() {
  const prompt = $("promptInput").value.trim();
  if (!selectedFile) return setRunStatus("error", "Error", "Please select an image.");
  if (!prompt) return setRunStatus("error", "Error", "Please enter a prompt.");
  const plan = mode === "local_debug" ? $("planInput").value.trim() : "";
  if (mode === "local_debug" && !plan) return setRunStatus("error", "Error", "Local Debug requires a precompiled plan.");

  const form = new FormData();
  form.append("image", selectedFile);
  form.append("prompt", prompt);
  if (plan) form.append("plan", plan);
  $("runButton").disabled = true;
  $("results").hidden = true;
  setRunStatus("queued", "Queued", "Waiting for the Visual Agent worker.");
  try {
    const response = await fetch("/api/run", {method: "POST", body: form});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed");
    jobId = data.job_id;
    startPolling();
  } catch (error) {
    $("runButton").disabled = false;
    setRunStatus("error", "Error", error.message);
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  const poll = async () => {
    try {
      const response = await fetch(`/api/status/${jobId}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Status request failed");
      if (data.status === "queued") return setRunStatus("queued", "Queued", "Waiting for the Visual Agent worker.");
      if (data.status === "running") return setRunStatus("running", "Running", "Visual Agent is running...");
      clearInterval(pollTimer);
      $("runButton").disabled = false;
      if (data.status === "error") return setRunStatus("error", "Error", data.error || "Unknown error");
      if (data.status === "done") {
        setRunStatus("completed", "Completed", `${data.summary.targets_count} final target(s).`);
        renderResult(data);
      }
    } catch (error) {
      clearInterval(pollTimer);
      $("runButton").disabled = false;
      setRunStatus("error", "Error", error.message);
    }
  };
  poll();
  pollTimer = setInterval(poll, 1200);
}

function statusTag(status) {
  const known = ["satisfied", "not_satisfied", "uncertain", "skipped", "not_applicable"];
  const safe = known.includes(status) ? status : "uncertain";
  const label = safe === "not_applicable" ? "N/A" : safe;
  return `<span class="tag ${safe}">${escapeHtml(label)}</span>`;
}

function renderResult(data) {
  const summary = data.summary;
  $("results").hidden = false;
  $("originalImage").src = `/api/job/${data.id}/original`;
  $("resultImage").src = `/api/job/${data.id}/${data.result_image}`;
  $("candidateOverlay").src = `/api/job/${data.id}/candidates.png`;
  $("artifactLinks").innerHTML = `<a href="/api/job/${data.id}/candidates.png" target="_blank">Open candidates.png</a><a href="/api/job/${data.id}/${escapeHtml(data.result_json)}" target="_blank">Open result JSON</a>`;

  const plan = summary.plan;
  const planItems = [
    ["Target Object", plan.target_object],
    ["Constraints", plan.constraints?.length ? plan.constraints.join("\n") : "N/A"],
    ["Related Objects", plan.related_objects?.length ? JSON.stringify(plan.related_objects) : "N/A"],
    ["Action", plan.action?.type || "N/A"],
  ];
  $("planSummary").innerHTML = planItems.map(([key, value]) => `<div class="datum"><small>${escapeHtml(key)}</small><code>${escapeHtml(value)}</code></div>`).join("");
  $("agentResponse").hidden = !summary.agent_response;
  $("agentResponse").textContent = summary.agent_response || "";

  $("candidateCount").textContent = `${summary.candidates_count} raw candidate(s)`;
  $("candidateRows").innerHTML = summary.candidates.length
    ? summary.candidates.map((candidate) => `<tr><td><code>${escapeHtml(candidate.id)}</code></td><td>${escapeHtml(candidate.label ?? "N/A")}</td><td><code>${candidate.confidence == null ? "N/A" : escapeHtml(candidate.confidence)}</code></td><td>${statusTag(candidate.verification_status)}</td></tr>`).join("")
    : '<tr><td colspan="4" class="empty">0 detector candidates</td></tr>';

  const localDebug = data.mode === "local_debug";
  $("semanticNotice").textContent = localDebug
    ? "SKIPPED — Local Debug does not call Qwen Semantic Verification."
    : "Statuses and evidence below are read directly from the pipeline result.";
  const semanticRows = [];
  summary.candidates.forEach((candidate) => {
    if (candidate.verification_checks.length) {
      candidate.verification_checks.forEach((check) => semanticRows.push(`<tr><td><code>${escapeHtml(candidate.id)}</code></td><td>${escapeHtml(check.constraint ?? "N/A")}</td><td>${statusTag(check.status)}</td><td>${escapeHtml(check.evidence ?? "N/A")}</td></tr>`));
    } else {
      semanticRows.push(`<tr><td><code>${escapeHtml(candidate.id)}</code></td><td>N/A</td><td>${statusTag(localDebug ? "skipped" : candidate.verification_status)}</td><td>${escapeHtml(candidate.verification_reason || "N/A")}</td></tr>`);
    }
  });
  $("semanticRows").innerHTML = semanticRows.length ? semanticRows.join("") : '<tr><td colspan="4" class="empty">No candidates to verify</td></tr>';
  renderRelations(summary.relation_bindings);

  $("targetCount").textContent = `${summary.targets_count} final target(s)`;
  $("targetRows").innerHTML = summary.targets.length
    ? summary.targets.map((target) => {
      const relation = target.relation ? `${target.relation.related_id} · ${target.relation.status}` : "N/A";
      return `<tr><td><code>${escapeHtml(target.id)}</code></td><td>${escapeHtml(target.label)}</td><td>${escapeHtml(target.verification_reason || "N/A")}</td><td>${escapeHtml(relation)}</td><td><code>${target.mask_score ?? "N/A"}</code></td><td><code>${target.mask_area_pixels ?? "N/A"}</code></td></tr>`;
    }).join("")
    : '<tr><td colspan="6" class="empty">0 final targets — valid negative result, not a system error.</td></tr>';
  renderTimings(summary.timings);
  $("results").scrollIntoView({behavior: "smooth", block: "start"});
}

function renderRelations(bindings) {
  if (!bindings.length) {
    $("relationBlock").innerHTML = "";
    return;
  }
  const rows = bindings.map((binding) => `<tr><td>${escapeHtml(binding.subject_id)}</td><td>${escapeHtml(binding.related_id)}</td><td>${statusTag(binding.status)}</td><td>${escapeHtml(binding.evidence)}</td></tr>`).join("");
  $("relationBlock").innerHTML = `<div class="relation"><h3>Relation Verification</h3><div class="table-wrap"><table><thead><tr><th>Subject</th><th>Related</th><th>Status</th><th>Evidence</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}

function renderTimings(timings) {
  const items = [];
  Object.entries(timings || {}).forEach(([key, value]) => {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      Object.entries(value).forEach(([child, childValue]) => items.push([`${key}.${child}`, childValue]));
    } else {
      items.push([key, value]);
    }
  });
  $("timingGrid").innerHTML = items.length
    ? items.map(([key, value]) => `<div class="timing-item"><span>${escapeHtml(key)}</span><code>${escapeHtml(value ?? "N/A")}</code></div>`).join("")
    : '<div class="empty">No timing fields in this result.</div>';
}

$("runButton").addEventListener("click", run);
