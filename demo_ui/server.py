"""Visual Agent Demo UI 服务器（纯标准库，无第三方 Web 依赖）。

运行：
    python -m demo_ui.server [--host 127.0.0.1] [--port 8080]

API：
    GET  /                          UI 页面
    GET  /api/health                健康检查
    POST /api/run                   提交任务（multipart: image + prompt [+ plan]）
    GET  /api/status/<job_id>       轮询任务状态与结果摘要
    GET  /api/job/<job_id>/<file>   获取任务产物（result.jpg / result.json / masks / candidates.png）

模式：
- 完整链路：未传 plan，需要 Planner 与 VLM 配置（PLANNER_* / VLM_*，
  默认本地 Ollama，无需云端 key）。
- 本地调试：传 plan JSON（或示例计划），仅运行 Detector → SAM2 → Action，
  不需要模型配置（verify=False）。UI 中明确标注，不改变生产语义。
"""

import argparse
import io
import json
import mimetypes
import os
import shutil
import threading
import time
import uuid
import warnings
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from visual_agent.pipeline import run_pipeline
from visual_agent.deepseek_agent import build_planner_client
from visual_agent.vlm_client import load_vlm_config

warnings.filterwarnings("ignore", category=DeprecationWarning)

ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = ROOT / "uploads"
OUTPUT_DIR = ROOT / "outputs"
STATIC_DIR = ROOT / "static"
INDEX_HTML = STATIC_DIR / "index.html"
ARTIFACT_RETENTION = timedelta(hours=24)

for directory in (UPLOAD_DIR, OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_queue: list[str] = []
_queue_cond = threading.Condition(_jobs_lock)

ACTION_LABELS = {
    "highlight": "高亮标注",
    "outline": "描边",
    "box": "矩形框选",
    "blur_target": "模糊",
    "dim_background": "背景变暗",
    "cutout": "抠图",
}

EXAMPLE_PLANS = {
    "只给穿红色衣服的人描边": {
        "target_object": "person",
        "label": "穿红色衣服的人",
        "constraints": [{"text": "穿红色衣服", "route": "attribute"}],
        "action": {"type": "outline"},
        "related_objects": [],
    },
    "把拿雨伞的人单独抠出来": {
        "target_object": "person",
        "label": "拿雨伞的人",
        "constraints": [{"text": "手持雨伞", "route": "relation"}],
        "action": {"type": "cutout"},
        "related_objects": [{"object": "umbrella", "relation": "held_by_target"}],
    },
    "把正在钓鱼的人高亮": {
        "target_object": "person",
        "label": "正在钓鱼的人",
        "constraints": [{"text": "正在钓鱼", "route": "behavior"}],
        "action": {"type": "highlight"},
        "related_objects": [],
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _full_chain_config_errors() -> list[str]:
    """完整链路是否可用的只读检查：Planner 与 VLM 配置必须都可解析。

    与视觉 Agent 生产代码共用同一配置 seam（build_planner_client /
    load_vlm_config），本地 Ollama 无需云端 key；缺配置时返回可读原因。
    """
    errors = []
    try:
        build_planner_client()
    except RuntimeError as error:
        errors.append(f"Planner：{error}")
    try:
        load_vlm_config()
    except RuntimeError as error:
        errors.append(f"VLM：{error}")
    return errors


def _remove_job_artifacts(
    job_id: str,
    *,
    image_path: Path | None = None,
    output_dir: Path | None = None,
) -> None:
    """只删除 Demo 专用目录内属于指定 job 的文件。"""
    uploads_root = UPLOAD_DIR.resolve()
    outputs_root = OUTPUT_DIR.resolve()
    upload_candidates = (
        [image_path]
        if image_path is not None
        else [path for path in UPLOAD_DIR.iterdir() if path.is_file() and path.stem == job_id]
    )
    for candidate in upload_candidates:
        resolved = candidate.resolve()
        if resolved.parent != uploads_root:
            raise RuntimeError(f"拒绝清理 uploads 目录外的文件：{resolved}")
        resolved.unlink(missing_ok=True)

    resolved_output = (output_dir or OUTPUT_DIR / job_id).resolve()
    if resolved_output.parent != outputs_root:
        raise RuntimeError(f"拒绝清理 outputs 目录外的目录：{resolved_output}")
    if resolved_output.is_dir():
        shutil.rmtree(resolved_output)


def _cleanup_expired_jobs(now: datetime | None = None) -> list[str]:
    """清理内存中已完成且超过保留期的 job，并同步删除其磁盘产物。"""
    cutoff = (now or datetime.now(timezone.utc)) - ARTIFACT_RETENTION
    expired_jobs = []
    with _jobs_lock:
        for job_id, job in list(_jobs.items()):
            if job.get("status") not in {"done", "error"} or not job.get("finished_at"):
                continue
            try:
                finished_at = datetime.fromisoformat(job["finished_at"])
                if finished_at.tzinfo is None:
                    finished_at = finished_at.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
            if finished_at.astimezone(timezone.utc) >= cutoff.astimezone(timezone.utc):
                continue
            expired_jobs.append(_jobs.pop(job_id))

    for job in expired_jobs:
        _remove_job_artifacts(
            job["id"], image_path=job["image_path"], output_dir=job["output_dir"]
        )
    return [job["id"] for job in expired_jobs]


def _cleanup_stale_disk_artifacts(now: datetime | None = None) -> list[str]:
    """服务启动时清理超过保留期的历史磁盘残留；此时不存在存活 job。"""
    cutoff_timestamp = ((now or datetime.now(timezone.utc)) - ARTIFACT_RETENTION).timestamp()
    output_dirs = {path.name: path for path in OUTPUT_DIR.iterdir() if path.is_dir()}
    uploads_by_job: dict[str, list[Path]] = {}
    for path in UPLOAD_DIR.iterdir():
        if path.is_file():
            uploads_by_job.setdefault(path.stem, []).append(path)

    removed = []
    for job_id in output_dirs.keys() | uploads_by_job.keys():
        output_dir = output_dirs.get(job_id)
        paths = [*uploads_by_job.get(job_id, [])]
        if output_dir is not None:
            paths.append(output_dir)
            paths.extend(output_dir.iterdir())
        if paths and max(path.stat().st_mtime for path in paths) < cutoff_timestamp:
            _remove_job_artifacts(job_id, output_dir=output_dir)
            removed.append(job_id)
    return removed


def _validate_plan(plan: dict) -> str | None:
    """本地调试模式下校验 plan 契约（与 DeepSeek Planner 输出契约一致）。"""
    try:
        target = plan["target_object"]
        if not isinstance(target, str) or not (1 <= len(target.split()) <= 3):
            return "target_object 必须是 1-3 个英文单词的基础实体"
        label = plan["label"]
        if not isinstance(label, str) or not label.strip():
            return "label 必须是非空字符串"
        constraints = plan["constraints"]
        if not isinstance(constraints, list):
            return "constraints 必须是 typed object 数组"
        for item in constraints:
            if (
                not isinstance(item, dict)
                or set(item) != {"text", "route"}
                or not isinstance(item["text"], str)
                or not item["text"].strip()
                or item["route"] not in {"attribute", "behavior", "relation"}
            ):
                return "constraint 必须只包含非空 text 和合法 route"
        action = plan["action"]
        if (
            not isinstance(action, dict)
            or not {"type"} <= set(action) <= {"type", "color"}
            or action["type"] not in ACTION_LABELS
        ):
            return "action.type 必须是白名单之一"
        color = action.get("color")
        if color is not None and (
            action["type"] not in {"box", "outline", "highlight"}
            or not isinstance(color, str)
            or len(color) != 7
            or not color.startswith("#")
            or any(character not in "0123456789abcdefABCDEF" for character in color[1:])
        ):
            return "action.color 只能是 box、outline 或 highlight 使用的 #RRGGBB"
        related = plan["related_objects"]
        if not isinstance(related, list) or len(related) > 1:
            return "related_objects 必须是长度 0..1 的数组"
        for item in related:
            if (
                not isinstance(item, dict)
                or set(item) != {"object", "relation"}
                or item["relation"] != "held_by_target"
            ):
                return "related object 只能包含 object 与 relation=held_by_target"
        relation_count = sum(item["route"] == "relation" for item in constraints)
        if relation_count != len(related):
            return "relation constraint 与 related_objects 必须保持 1:1 ownership"
    except KeyError as error:
        return f"plan 缺少字段：{error}"
    return None


def _candidate_status(candidate: dict, local_mode: bool) -> str:
    """只按 pipeline 已有结果归纳展示状态，不在 Demo 中增加判断。"""
    if local_mode:
        return "skipped"
    checks = candidate.get("verification_checks", [])
    if not checks:
        return "not_applicable"
    statuses = {check.get("status") for check in checks}
    if "not_satisfied" in statuses:
        return "not_satisfied"
    if statuses == {"satisfied"}:
        return "satisfied"
    return "uncertain"


def _annotate_candidates(
    input_image: Path, result: dict, output_png: Path, local_mode: bool
) -> None:
    """把 Detector 候选框与验证状态画到输入图上，作为调试面板的候选 bbox 图。"""
    image = Image.open(input_image).convert("RGB")
    draw = ImageDraw.Draw(image)
    scale = max(1.0, 1400 / max(image.size))
    if scale > 1:
        image = image.resize(
            (round(image.width * scale), round(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
        draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(16, min(image.size) // 40))
    line_width = max(2, min(image.size) // 250)
    candidates = result.get("candidates", [])
    for candidate in candidates:
        bbox = [coordinate * scale for coordinate in candidate["bbox"]]
        status = _candidate_status(candidate, local_mode)
        if status in {"satisfied", "not_applicable"}:
            color = "#00cc44"
        elif status in {"uncertain", "skipped"}:
            color = "#f0ad4e"
        else:
            color = "#ff4444"
        draw.rectangle(bbox, outline=color, width=line_width)
        candidate_id = candidate["id"]
        text = f"{candidate_id} {status}"
        text_bbox = draw.textbbox((0, 0), text, font=font)
        label_x = max(0, int(bbox[0]))
        label_y = max(0, int(bbox[1]) - (text_bbox[3] - text_bbox[1]) - 6)
        draw.rectangle(
            (
                label_x,
                label_y,
                label_x + (text_bbox[2] - text_bbox[0]) + 8,
                label_y + (text_bbox[3] - text_bbox[1]) + 4,
            ),
            fill=color,
        )
        draw.text((label_x + 4, label_y + 2), text, fill="white", font=font)
    image.save(output_png, format="PNG")


def _build_summary(result: dict, local_mode: bool) -> dict:
    """把 pipeline 现有字段整理为只读 UI 摘要。"""
    relation_by_subject = {
        item["subject_id"]: item for item in result.get("relation_bindings", [])
    }
    return {
        "prompt": result["prompt"],
        "mode": "local_debug" if local_mode else "full_chain",
        "plan": result["plan"],
        "agent_response": result.get("agent_response"),
        "candidates_count": len(result["candidates"]),
        "verified_subjects_count": len(result["verified_subjects"]),
        "targets_count": len(result["targets"]),
        "action_type": result["plan"]["action"]["type"],
        "action_label": ACTION_LABELS.get(result["plan"]["action"]["type"]),
        "candidates": [
            {
                "id": candidate["id"],
                "label": candidate.get("text_label"),
                "confidence": candidate.get("dino_confidence"),
                "verification_status": _candidate_status(candidate, local_mode),
                "verification_checks": candidate.get("verification_checks", []),
                "verification_reason": candidate.get("verification_reason"),
            }
            for candidate in result["candidates"]
        ],
        "relation_bindings": [
            {
                "subject_id": item["subject_id"],
                "related_id": item["related_id"],
                "status": item["status"],
                "evidence": item["evidence"],
            }
            for item in result["relation_bindings"]
        ],
        "targets": [
            {
                "id": target["id"],
                "label": target["label"],
                "verification_reason": target["reason"],
                "relation": relation_by_subject.get(target["id"]),
                "mask_score": target.get("segmentation", {}).get("mask_score"),
                "mask_area_pixels": target.get("segmentation", {}).get("mask_area_pixels"),
            }
            for target in result["targets"]
        ],
        "timings": result["timings"],
    }


def _worker() -> None:
    while True:
        with _queue_cond:
            while not _queue:
                _queue_cond.wait()
            job_id = _queue.pop(0)
            job = _jobs[job_id]
            job["status"] = "running"
            job["started_at"] = _now_iso()
        try:
            _run_job(job)
        except Exception as error:  # noqa: BLE001 - 前台收集并结构化返回
            with _jobs_lock:
                job["status"] = "error"
                job["error"] = str(error)
                job["finished_at"] = _now_iso()


def _run_job(job: dict) -> None:
    plan = job.get("plan")
    local_mode = plan is not None
    image_output, json_output = run_pipeline(
        job["image_path"],
        job["prompt"],
        plan=plan,
        verify=not local_mode,
        final_response=not local_mode,
        fresh_models=False,
        output_dir=job["output_dir"],
    )
    result = json.loads(json_output.read_text(encoding="utf-8"))
    _annotate_candidates(
        job["image_path"], result, job["output_dir"] / "candidates.png", local_mode
    )
    with _jobs_lock:
        job["status"] = "done"
        job["finished_at"] = _now_iso()
        job["result_image"] = image_output.name
        job["result_json"] = json_output.name
        job["summary"] = _build_summary(result, local_mode)


class Handler(BaseHTTPRequestHandler):
    server_version = "VisualAgentDemo/1.0"

    def log_message(self, fmt, *args):  # 精简访问日志
        print(f"[ui] {self.address_string()} {fmt % args}")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, download: bool = False) -> None:
        if not path.is_file():
            self._send_json({"error": "文件不存在"}, 404)
            return
        mime, _ = mimetypes.guess_type(path.name)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/":
            if not INDEX_HTML.is_file():
                self._send_json({"error": "index.html 缺失"}, 500)
                return
            self._send_file(INDEX_HTML)
            return
        if path == "/api/health":
            self._send_json({
                "ok": True,
                "jobs": len(_jobs),
                "full_chain_available": not _full_chain_config_errors(),
            })
            return
        if path.startswith("/static/"):
            filename = path.removeprefix("/static/")
            candidate = (STATIC_DIR / filename).resolve()
            if not str(candidate).startswith(str(STATIC_DIR.resolve())):
                self._send_json({"error": "非法路径"}, 403)
                return
            self._send_file(candidate)
            return
        if path.startswith("/api/status/"):
            job_id = path.removeprefix("/api/status/")
            with _jobs_lock:
                job = _jobs.get(job_id)
            if job is None:
                self._send_json({"error": "任务不存在"}, 404)
                return
            self._send_json({key: job[key] for key in
                             ["id", "status", "mode", "prompt", "error",
                              "created_at", "started_at", "finished_at",
                              "result_image", "result_json", "summary"] if key in job})
            return
        if path.startswith("/api/job/"):
            parts = path.removeprefix("/api/job/").split("/", 1)
            if len(parts) != 2:
                self._send_json({"error": "路径格式错误"}, 400)
                return
            job_id, filename = parts
            with _jobs_lock:
                job = _jobs.get(job_id)
            if job is None:
                self._send_json({"error": "任务不存在"}, 404)
                return
            if filename == "original":
                self._send_file(job["image_path"])
                return
            candidate = (job["output_dir"] / filename).resolve()
            if not str(candidate).startswith(str(job["output_dir"].resolve())):
                self._send_json({"error": "非法路径"}, 403)
                return
            self._send_file(candidate)
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/api/run":
            self._send_json({"error": "not found"}, 404)
            return
        try:
            self._handle_run()
        except Exception as error:  # noqa: BLE001
            self._send_json({"error": f"请求处理失败：{error}"}, 400)

    def _handle_run(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json({"error": "需要 multipart/form-data"}, 400)
            return
        import cgi

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
            },
        )
        image_field = form["image"]
        if image_field is None or not getattr(image_field, "file", None):
            self._send_json({"error": "缺少图片文件"}, 400)
            return
        prompt = form.getvalue("prompt") or ""
        prompt = prompt.strip()
        if not prompt:
            self._send_json({"error": "缺少自然语言指令"}, 400)
            return
        plan_text = form.getvalue("plan") or ""
        plan = None
        local_mode = bool(plan_text.strip())
        if local_mode:
            try:
                plan = json.loads(plan_text)
            except json.JSONDecodeError as error:
                self._send_json({"error": f"plan JSON 解析失败：{error}"}, 400)
                return
            validation_error = _validate_plan(plan)
            if validation_error:
                self._send_json({"error": f"plan 契约校验失败：{validation_error}"}, 400)
                return
        else:
            config_errors = _full_chain_config_errors()
            if config_errors:
                self._send_json(
                    {
                        "error": (
                            "完整链路配置不完整："
                            + "；".join(config_errors)
                            + "。请按 README 设置 PLANNER_* 与 VLM_* 环境变量"
                            "（本地 Ollama 无需云端 key），"
                            "或切换到「本地调试模式」并提供预编译计划 JSON。"
                        )
                    },
                    400,
                )
                return

        _cleanup_expired_jobs()
        job_id = uuid.uuid4().hex[:12]
        job_dir = OUTPUT_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        raw_name = Path(image_field.filename or "upload.jpg").name
        suffix = Path(raw_name).suffix.lower() or ".jpg"
        if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
            self._send_json({"error": f"不支持的图片格式：{suffix}"}, 400)
            return
        image_path = UPLOAD_DIR / f"{job_id}{suffix}"
        with open(image_path, "wb") as handle:
            handle.write(image_field.file.read())

        job = {
            "id": job_id,
            "status": "queued",
            "mode": "local_debug" if local_mode else "full_chain",
            "prompt": prompt,
            "plan": plan,
            "image_path": image_path,
            "output_dir": job_dir,
            "result_image": None,
            "result_json": None,
            "error": None,
            "summary": None,
            "created_at": _now_iso(),
            "started_at": None,
            "finished_at": None,
        }
        with _queue_cond:
            _jobs[job_id] = job
            _queue.append(job_id)
            _queue_cond.notify()
        self._send_json({"job_id": job_id, "mode": job["mode"]}, 202)


def main() -> None:
    parser = argparse.ArgumentParser(description="Visual Agent Demo UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    removed = _cleanup_stale_disk_artifacts()
    worker = threading.Thread(target=_worker, daemon=True, name="visual-agent-worker")
    worker.start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    config_errors = _full_chain_config_errors()
    print("Visual Agent Demo UI 已启动：")
    print(f"  地址：http://{args.host}:{args.port}")
    if config_errors:
        print("  完整链路：配置不完整（" + "；".join(config_errors) + "）")
    else:
        print("  完整链路：Planner / VLM 配置就绪")
    print(f"  产物保留：24 小时（启动时已清理 {len(removed)} 个过期任务）")
    print("  按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("正在停止…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
