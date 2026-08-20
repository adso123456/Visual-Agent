"""API V1 对外数据结构与校验常量。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

TaskStatusValue = Literal["queued", "running", "success", "failed"]
BatchStatusValue = Literal["queued", "running", "completed"]

SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class TaskCreated(BaseModel):
    task_id: str
    status: Literal["queued"] = "queued"


class BatchCreated(BaseModel):
    batch_id: str
    status: BatchStatusValue
    total: int
    queued: int = 0
    completed: int = 0
    failed: int = 0


class ArtifactInfo(BaseModel):
    name: str
    url: str


class TaskResult(BaseModel):
    summary: dict
    artifacts: list[ArtifactInfo]
    result_image: str | None = None
    result_json: str | None = None


class TaskStatus(BaseModel):
    task_id: str
    status: TaskStatusValue
    prompt: str
    image_name: str
    batch_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    result: TaskResult | None = None


class BatchItem(BaseModel):
    image_name: str
    task_id: str
    status: TaskStatusValue
    error: str | None = None


class BatchStatus(BaseModel):
    batch_id: str
    status: BatchStatusValue
    prompt: str
    total: int
    queued: int
    running: int
    completed: int
    failed: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    items: list[BatchItem]
