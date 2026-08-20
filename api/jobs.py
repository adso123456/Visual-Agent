"""任务与批处理调度层：内存 job 表 + worker queue。

V1 不引入 Redis/Celery/数据库；任务状态保存在进程内，
产物保存在 data_dir 对应的 uploads/outputs 目录。
"""

import json
import queue
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from api.schemas import SUPPORTED_IMAGE_SUFFIXES

MAX_UPLOAD_BYTES = 64 * 1024 * 1024

Runner = Callable[[Path, str, Path], tuple[Path, Path]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_runner(image_path: Path, prompt: str, output_dir: Path) -> tuple[Path, Path]:
    """生产默认 runner：直接复用已验证的视觉 Pipeline。"""
    from visual_agent.pipeline import run_pipeline

    return run_pipeline(image_path, prompt, output_dir=output_dir)


class JobManager:
    """管理单图任务、批处理任务与后台 worker 队列。"""

    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        max_concurrent_jobs: int = 1,
        runner: Runner | None = None,
    ) -> None:
        self._data_dir = (
            Path(data_dir).resolve()
            if data_dir is not None
            else Path(__file__).resolve().parent / "storage"
        )
        self._uploads_dir = self._data_dir / "uploads"
        self._outputs_dir = self._data_dir / "outputs"
        self._runner = runner or _default_runner
        self._max_concurrent_jobs = max(1, int(max_concurrent_jobs))

        self._jobs: dict[str, dict] = {}
        self._batches: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._stop = threading.Event()
        self._workers = [
            threading.Thread(
                target=self._worker_loop,
                name=f"api-worker-{index}",
                daemon=True,
            )
            for index in range(self._max_concurrent_jobs)
        ]
        for worker in self._workers:
            worker.start()

    def __enter__(self) -> "JobManager":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.shutdown(wait=True)

    def shutdown(self, *, wait: bool = False) -> None:
        """停止 worker；wait=True 时等待已排队的任务执行完成。"""
        self._stop.set()
        if wait:
            for worker in self._workers:
                worker.join(timeout=5)
        else:
            for _ in self._workers:
                self._queue.put(None)

    def _worker_loop(self) -> None:
        while True:
            try:
                task_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                if self._stop.is_set():
                    return
                continue
            if task_id is None:
                return
            self._execute_task(task_id)
            self._queue.task_done()

    def submit_task(
        self,
        image_bytes: bytes,
        image_name: str,
        prompt: str,
        *,
        batch_id: str | None = None,
    ) -> str:
        """创建单图任务并进入 worker queue。"""
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt 不能为空")
        if not image_bytes:
            raise ValueError("图片内容为空")
        if len(image_bytes) > MAX_UPLOAD_BYTES:
            raise ValueError("图片超过 64 MiB 上限")
        suffix = Path(image_name).suffix.lower()
        if suffix not in SUPPORTED_IMAGE_SUFFIXES:
            raise ValueError(f"不支持的图片格式：{suffix}")

        task_id = uuid.uuid4().hex[:16]
        self._uploads_dir.mkdir(parents=True, exist_ok=True)
        self._outputs_dir.mkdir(parents=True, exist_ok=True)
        image_path = self._uploads_dir / f"{task_id}{suffix}"
        image_path.write_bytes(image_bytes)
        output_dir = self._outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        task = {
            "id": task_id,
            "status": "queued",
            "prompt": prompt,
            "image_name": Path(image_name).name,
            "batch_id": batch_id,
            "image_path": image_path,
            "output_dir": output_dir,
            "result_image": None,
            "result_json": None,
            "error": None,
            "created_at": _now_iso(),
            "started_at": None,
            "finished_at": None,
        }
        with self._lock:
            self._jobs[task_id] = task
            self._queue.put(task_id)
        return task_id

    def submit_batch(
        self,
        prompt: str,
        images: list[tuple[bytes, str]],
    ) -> str:
        """创建批处理：同一 prompt 作用到多张图片，单图失败不影响其他图。"""
        if not prompt.strip():
            raise ValueError("prompt 不能为空")
        if not images:
            raise ValueError("images 不能为空")

        batch_id = uuid.uuid4().hex[:16]
        with self._lock:
            self._batches[batch_id] = {
                "id": batch_id,
                "prompt": prompt.strip(),
                "task_ids": [],
                "created_at": _now_iso(),
            }

        task_ids = []
        for image_bytes, image_name in images:
            try:
                task_id = self.submit_task(
                    image_bytes,
                    image_name,
                    prompt,
                    batch_id=batch_id,
                )
            except ValueError as error:
                task_id = self._create_failed_task(
                    image_name,
                    prompt,
                    str(error),
                    batch_id=batch_id,
                )
            task_ids.append(task_id)

        with self._lock:
            self._batches[batch_id]["task_ids"] = task_ids
        return batch_id

    def _create_failed_task(
        self,
        image_name: str,
        prompt: str,
        error: str,
        *,
        batch_id: str | None = None,
    ) -> str:
        task_id = uuid.uuid4().hex[:16]
        task = {
            "id": task_id,
            "status": "failed",
            "prompt": prompt.strip(),
            "image_name": Path(image_name).name,
            "batch_id": batch_id,
            "image_path": None,
            "output_dir": None,
            "result_image": None,
            "result_json": None,
            "error": error,
            "created_at": _now_iso(),
            "started_at": None,
            "finished_at": _now_iso(),
        }
        with self._lock:
            self._jobs[task_id] = task
        return task_id

    def _execute_task(self, task_id: str) -> None:
        with self._lock:
            task = self._jobs[task_id]
            task["status"] = "running"
            task["started_at"] = _now_iso()
        try:
            image_output, json_output = self._runner(
                task["image_path"],
                task["prompt"],
                task["output_dir"],
            )
            with self._lock:
                task["status"] = "success"
                task["finished_at"] = _now_iso()
                task["result_image"] = image_output.name
                task["result_json"] = json_output.name
        except Exception as error:  # noqa: BLE001 - 单图失败必须隔离
            with self._lock:
                task["status"] = "failed"
                task["finished_at"] = _now_iso()
                task["error"] = f"{type(error).__name__}: {error}"

    def get_task(self, task_id: str) -> dict | None:
        with self._lock:
            task = self._jobs.get(task_id)
            if task is None:
                return None
            return self._task_view(task)

    def _task_view(self, task: dict) -> dict:
        view = {
            "task_id": task["id"],
            "status": task["status"],
            "prompt": task["prompt"],
            "image_name": task["image_name"],
            "batch_id": task.get("batch_id"),
            "created_at": task["created_at"],
            "started_at": task.get("started_at"),
            "finished_at": task.get("finished_at"),
            "error": task.get("error"),
            "result": None,
        }
        if task["status"] != "success" or not task.get("result_json"):
            return view
        json_path = task["output_dir"] / task["result_json"]
        if not json_path.is_file():
            return view
        view["result"] = {
            "summary": _load_result_summary(json_path),
            "artifacts": [
                {
                    "name": path.name,
                    "url": (
                        f"/api/v1/tasks/{task['id']}/artifacts/"
                        f"{quote(path.name)}"
                    ),
                }
                for path in sorted(task["output_dir"].iterdir())
                if path.is_file()
            ],
            "result_image": (
                f"/api/v1/tasks/{task['id']}/artifacts/"
                f"{quote(task['result_image'])}"
                if task.get("result_image")
                else None
            ),
            "result_json": (
                f"/api/v1/tasks/{task['id']}/artifacts/"
                f"{quote(task['result_json'])}"
            ),
        }
        return view

    def get_batch(self, batch_id: str) -> dict | None:
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                return None
            tasks = [self._jobs[task_id] for task_id in batch["task_ids"]]

        statuses = [task["status"] for task in tasks]
        queued = statuses.count("queued")
        running = statuses.count("running")
        completed = statuses.count("success")
        failed = statuses.count("failed")
        if queued + running == 0:
            batch_status = "completed"
        elif running:
            batch_status = "running"
        else:
            batch_status = "queued"

        started_values = [
            task.get("started_at") for task in tasks if task.get("started_at")
        ]
        finished_values = [
            task.get("finished_at")
            for task in tasks
            if task.get("finished_at") and task["status"] in {"success", "failed"}
        ]
        return {
            "batch_id": batch_id,
            "status": batch_status,
            "prompt": batch["prompt"],
            "total": len(tasks),
            "queued": queued,
            "running": running,
            "completed": completed,
            "failed": failed,
            "created_at": batch["created_at"],
            "started_at": min(started_values) if started_values else None,
            "finished_at": (
                max(finished_values)
                if finished_values and len(finished_values) == len(tasks)
                else None
            ),
            "items": [
                {
                    "image_name": task["image_name"],
                    "task_id": task["id"],
                    "status": task["status"],
                    "error": task.get("error"),
                }
                for task in tasks
            ],
        }

    def resolve_artifact(self, task_id: str, filename: str) -> Path | None:
        with self._lock:
            task = self._jobs.get(task_id)
            if task is None or task.get("output_dir") is None:
                return None
            output_dir = task["output_dir"]
        if Path(filename).name != filename:
            return None
        candidate = (output_dir / filename).resolve()
        if candidate.parent != output_dir.resolve() or not candidate.is_file():
            return None
        return candidate


def _load_result_summary(json_path: Path) -> dict:
    result = json.loads(json_path.read_text(encoding="utf-8"))
    return {
        "prompt": result.get("prompt"),
        "agent_response": result.get("agent_response"),
        "plan": result.get("plan"),
        "candidates_count": len(result.get("candidates", [])),
        "verified_subjects_count": len(result.get("verified_subjects", [])),
        "targets_count": len(result.get("targets", [])),
        "timings": result.get("timings"),
    }
