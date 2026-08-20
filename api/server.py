"""Visual Agent 生产 API 服务。

运行：
    python -m api.server --host 0.0.0.0 --port 8000

端点：
    POST /api/v1/tasks                 提交单图任务（image + prompt）
    GET  /api/v1/tasks/{task_id}       查询任务状态与结果
    GET  /api/v1/tasks/{task_id}/artifacts/{name}
    POST /api/v1/batches               提交批量任务（prompt + images[]）
    GET  /api/v1/batches/{batch_id}    查询批量进度
"""

import argparse
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from api.jobs import JobManager
from api.schemas import BatchCreated, BatchStatus, TaskCreated, TaskStatus


def _max_concurrent_jobs() -> int:
    return max(1, int(os.getenv("MAX_CONCURRENT_JOBS", "1")))


def create_app(job_manager: JobManager | None = None) -> FastAPI:
    manager = job_manager or JobManager(max_concurrent_jobs=_max_concurrent_jobs())
    app = FastAPI(title="Visual Agent API", version="0.1.0")
    app.state.job_manager = manager

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"ok": True, "service": "visual-agent-api"}

    @app.post("/api/v1/tasks", response_model=TaskCreated, status_code=202)
    async def create_task(
        image: UploadFile = File(...),
        prompt: str = Form(...),
    ) -> dict:
        image_bytes = await image.read()
        try:
            task_id = manager.submit_task(
                image_bytes,
                image.filename or "upload.jpg",
                prompt,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"task_id": task_id, "status": "queued"}

    @app.get("/api/v1/tasks/{task_id}", response_model=TaskStatus)
    def get_task(task_id: str) -> dict:
        view = manager.get_task(task_id)
        if view is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return view

    @app.get("/api/v1/tasks/{task_id}/artifacts/{filename}")
    def get_artifact(task_id: str, filename: str):
        path = manager.resolve_artifact(task_id, filename)
        if path is None:
            raise HTTPException(status_code=404, detail="产物不存在")
        return FileResponse(path)

    @app.post("/api/v1/batches", response_model=BatchCreated, status_code=202)
    async def create_batch(
        prompt: str = Form(...),
        images: list[UploadFile] = File(...),
    ) -> dict:
        uploaded = [
            (await image.read(), image.filename or "upload.jpg")
            for image in images
        ]
        try:
            batch_id = manager.submit_batch(prompt, uploaded)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        view = manager.get_batch(batch_id)
        return {
            "batch_id": batch_id,
            "status": view["status"],
            "total": view["total"],
            "queued": view["queued"],
            "completed": view["completed"],
            "failed": view["failed"],
        }

    @app.get("/api/v1/batches/{batch_id}", response_model=BatchStatus)
    def get_batch(batch_id: str) -> dict:
        view = manager.get_batch(batch_id)
        if view is None:
            raise HTTPException(status_code=404, detail="批处理任务不存在")
        return view

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Visual Agent 生产 API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="上传与产物根目录，默认 api/storage",
    )
    parser.add_argument(
        "--max-concurrent-jobs",
        type=int,
        default=None,
        help="后台 worker 数，默认 1",
    )
    args = parser.parse_args()

    manager = JobManager(
        data_dir=args.data_dir,
        max_concurrent_jobs=(
            args.max_concurrent_jobs
            if args.max_concurrent_jobs is not None
            else _max_concurrent_jobs()
        ),
    )
    application = create_app(manager)
    uvicorn.run(application, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
