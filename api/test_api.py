"""API V1 单图 / 批处理接口测试（使用假 runner，不加载模型）。"""

import json
import io
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from api import jobs as jobs_module
from api.jobs import JobManager
from api.server import _iter_limited_images, _read_image_bytes, create_app


def _write_result(output_dir: Path, prompt: str, image_bytes: bytes):
    output_dir.mkdir(parents=True, exist_ok=True)
    image_output = output_dir / "result_001.jpg"
    json_output = output_dir / "result_001.json"
    image_output.write_bytes(image_bytes)
    result = {
        "prompt": prompt,
        "agent_response": "完成",
        "plan": {"action": {"type": "box"}},
        "candidates": [],
        "verified_subjects": [],
        "targets": [],
        "timings": {"total_seconds": 0.01},
    }
    json_output.write_text(
        json.dumps(result, ensure_ascii=False),
        encoding="utf-8",
    )
    return image_output, json_output


def _fake_runner(image_path: Path, prompt: str, output_dir: Path):
    image_bytes = image_path.read_bytes()
    if image_bytes == b"bad":
        raise RuntimeError("模拟单图失败")
    return _write_result(output_dir, prompt, image_bytes)


def _wait_status(client, url: str, terminal: set[str], timeout: float = 5.0):
    deadline = time.time() + timeout
    payload = None
    while time.time() < deadline:
        payload = client.get(url).json()
        if payload["status"] in terminal:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"等待超时：{payload}")


def test_single_task_lifecycle(tmp_path):
    with JobManager(
        data_dir=tmp_path / "data",
        max_concurrent_jobs=1,
        runner=_fake_runner,
    ) as manager:
        with TestClient(create_app(manager)) as client:
            response = client.post(
                "/api/v1/tasks",
                files={"image": ("a.jpg", b"good", "image/jpeg")},
                data={"prompt": "找到戴安全帽的人"},
            )
            assert response.status_code == 202
            created = response.json()
            assert created["status"] == "queued"

            task = _wait_status(
                client,
                f"/api/v1/tasks/{created['task_id']}",
                {"success", "failed"},
            )
            assert task["status"] == "success"
            assert task["result"]["summary"]["prompt"] == "找到戴安全帽的人"
            assert task["result"]["summary"]["targets_count"] == 0
            assert task["result"]["result_json"].endswith("result_001.json")

            artifact = client.get(task["result"]["result_json"])
            assert artifact.status_code == 200
            assert artifact.json()["prompt"] == "找到戴安全帽的人"


def test_batch_progress_and_failure_isolation(tmp_path):
    with JobManager(
        data_dir=tmp_path / "data",
        max_concurrent_jobs=1,
        runner=_fake_runner,
    ) as manager:
        with TestClient(create_app(manager)) as client:
            files = [
                ("images", ("001.jpg", b"good", "image/jpeg")),
                ("images", ("002.jpg", b"bad", "image/jpeg")),
                ("images", ("003.jpg", b"good", "image/jpeg")),
                ("images", ("004.txt", b"not-an-image", "text/plain")),
            ]
            response = client.post(
                "/api/v1/batches",
                files=files,
                data={"prompt": "框出所有戴安全帽的人"},
            )
            assert response.status_code == 202
            created = response.json()
            assert created["total"] == 4

            batch = _wait_status(
                client,
                f"/api/v1/batches/{created['batch_id']}",
                {"completed"},
            )
            assert batch["status"] == "completed"
            assert batch["total"] == 4
            assert batch["completed"] == 2
            assert batch["failed"] == 2

            by_name = {item["image_name"]: item for item in batch["items"]}
            assert by_name["001.jpg"]["status"] == "success"
            assert by_name["002.jpg"]["status"] == "failed"
            assert by_name["003.jpg"]["status"] == "success"
            assert by_name["004.txt"]["status"] == "failed"
            assert "不支持的图片格式" in by_name["004.txt"]["error"]

            failed = client.get(
                f"/api/v1/tasks/{by_name['002.jpg']['task_id']}"
            ).json()
            assert failed["status"] == "failed"
            assert "模拟单图失败" in failed["error"]


def test_single_worker_serializes_jobs(tmp_path):
    started = threading.Event()
    release = threading.Event()

    def blocking_runner(image_path: Path, prompt: str, output_dir: Path):
        started.set()
        release.wait(2)
        return _write_result(output_dir, prompt, image_path.read_bytes())

    with JobManager(
        data_dir=tmp_path / "data",
        max_concurrent_jobs=1,
        runner=blocking_runner,
    ) as manager:
        first = manager.submit_task(b"first", "a.jpg", "任务1")
        second = manager.submit_task(b"second", "b.jpg", "任务2")
        assert started.wait(2)
        time.sleep(0.05)
        assert manager.get_task(first)["status"] == "running"
        assert manager.get_task(second)["status"] == "queued"

        release.set()
        deadline = time.time() + 5
        while time.time() < deadline:
            statuses = {
                manager.get_task(first)["status"],
                manager.get_task(second)["status"],
            }
            if statuses == {"success"}:
                break
            time.sleep(0.02)
        assert statuses == {"success"}


def test_single_task_rejects_bad_image(tmp_path):
    with JobManager(
        data_dir=tmp_path / "data",
        max_concurrent_jobs=1,
        runner=_fake_runner,
    ) as manager:
        with TestClient(create_app(manager)) as client:
            response = client.post(
                "/api/v1/tasks",
                files={"image": ("a.txt", b"x", "text/plain")},
                data={"prompt": "找到人"},
            )
            assert response.status_code == 400
            assert "不支持的图片格式" in response.json()["detail"]


def test_single_task_rejects_oversized_image(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_module, "MAX_UPLOAD_BYTES", 16)
    with JobManager(
        data_dir=tmp_path / "data",
        max_concurrent_jobs=1,
        runner=_fake_runner,
    ) as manager:
        with TestClient(create_app(manager)) as client:
            response = client.post(
                "/api/v1/tasks",
                files={"image": ("big.jpg", b"x" * 100, "image/jpeg")},
                data={"prompt": "找到人"},
            )
            assert response.status_code == 400
            assert "超过 1 MiB 上限" in response.json()["detail"]


def test_single_upload_read_is_bounded(monkeypatch):
    monkeypatch.setattr(jobs_module, "MAX_UPLOAD_BYTES", 16)

    class FakeUpload:
        def __init__(self, data: bytes):
            self.file = io.BytesIO(data)

    payload = b"x" * 100
    data = _read_image_bytes(FakeUpload(payload))
    assert len(data) == 17


def test_batch_rejects_too_many_images(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_module, "MAX_BATCH_IMAGES", 2)
    with JobManager(
        data_dir=tmp_path / "data",
        max_concurrent_jobs=1,
        runner=_fake_runner,
    ) as manager:
        with TestClient(create_app(manager)) as client:
            files = [
                ("images", (f"{index}.jpg", b"good", "image/jpeg"))
                for index in range(3)
            ]
            response = client.post(
                "/api/v1/batches",
                files=files,
                data={"prompt": "框出所有人"},
            )
            assert response.status_code == 400
            assert "最多 2 张图片" in response.json()["detail"]


def test_batch_oversized_image_is_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_module, "MAX_UPLOAD_BYTES", 16)
    with JobManager(
        data_dir=tmp_path / "data",
        max_concurrent_jobs=1,
        runner=_fake_runner,
    ) as manager:
        with TestClient(create_app(manager)) as client:
            files = [
                ("images", ("big.jpg", b"x" * 100, "image/jpeg")),
                ("images", ("ok.jpg", b"good", "image/jpeg")),
            ]
            response = client.post(
                "/api/v1/batches",
                files=files,
                data={"prompt": "框出所有人"},
            )
            assert response.status_code == 202

            batch = _wait_status(
                client,
                f"/api/v1/batches/{response.json()['batch_id']}",
                {"completed"},
            )
            assert batch["completed"] == 1
            assert batch["failed"] == 1
            by_name = {item["image_name"]: item for item in batch["items"]}
            assert by_name["big.jpg"]["status"] == "failed"
            assert "超过 1 MiB 上限" in by_name["big.jpg"]["error"]
            assert by_name["ok.jpg"]["status"] == "success"


def test_bounded_upload_read(monkeypatch):
    monkeypatch.setattr(jobs_module, "MAX_UPLOAD_BYTES", 16)

    class FakeUpload:
        def __init__(self, data: bytes):
            self.file = io.BytesIO(data)
            self.filename = "big.jpg"

    payload = b"x" * 100
    data, name = next(_iter_limited_images([FakeUpload(payload)]))
    assert len(data) == 17
    assert name == "big.jpg"
