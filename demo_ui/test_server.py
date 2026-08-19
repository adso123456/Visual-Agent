import json
import os
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

from demo_ui import server as server_module
from demo_ui.server import (
    EXAMPLE_PLANS,
    Handler,
    STATIC_DIR,
    _build_summary,
    _candidate_status,
    _cleanup_expired_jobs,
    _cleanup_stale_disk_artifacts,
)


def _result_fixture():
    return {
        "prompt": "只给穿红色衣服的人描边",
        "plan": {
            "target_object": "person",
            "label": "穿红色衣服的人",
            "constraints": ["穿红色衣服"],
            "action": {"type": "outline"},
            "related_objects": [],
        },
        "agent_response": "完成",
        "candidates": [{
            "id": "A", "text_label": "person", "dino_confidence": 0.9,
            "verification_checks": [{
                "constraint": "穿红色衣服", "status": "satisfied", "evidence": "红色上衣",
            }],
            "verification_reason": "红色上衣", "verified": True,
        }],
        "verified_subjects": [{"id": "A"}],
        "relation_bindings": [],
        "targets": [{
            "id": "A", "label": "穿红色衣服的人", "reason": "红色上衣",
            "segmentation": {"mask_score": 0.95, "mask_area_pixels": 1234},
        }],
        "timings": {"grounding_dino_seconds": 1.2, "total_seconds": 2.5},
    }


def test_three_fixed_examples_and_static_split():
    assert list(EXAMPLE_PLANS) == [
        "只给穿红色衣服的人描边",
        "把拿雨伞的人单独抠出来",
        "把正在钓鱼的人高亮",
    ]
    assert (STATIC_DIR / "style.css").is_file()
    assert (STATIC_DIR / "app.js").is_file()
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert script.count("prompt:") == 3
    assert "最终目标为 0——这是有效的负向结果" in script


def test_image_viewer_static_contract():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="imageViewer"' in html
    assert 'id="viewerStage"' in html
    assert 'id="viewerClose"' in html
    assert "function openViewer" in script
    assert "function closeViewer" in script
    assert "function resetViewer" in script
    assert '.addEventListener("wheel"' in script
    assert 'event.key === "Escape"' in script


def test_summary_only_exposes_existing_pipeline_values():
    result = _result_fixture()
    summary = _build_summary(result, local_mode=False)
    assert summary["candidates"][0]["verification_status"] == "satisfied"
    assert summary["targets"][0]["mask_score"] == 0.95
    assert summary["timings"] is result["timings"]
    assert _candidate_status(result["candidates"][0], local_mode=True) == "skipped"


def test_health_home_and_static_assets():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/health") as response:
            health = json.load(response)
        assert health["ok"] is True
        with urllib.request.urlopen(base + "/") as response:
            assert "Visual Agent 开发者演示" in response.read().decode("utf-8")
        with urllib.request.urlopen(base + "/static/app.js") as response:
            assert response.headers.get_content_type() == "application/javascript"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_cleanup_expired_jobs_keeps_active_jobs_and_removes_memory(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    outputs = tmp_path / "outputs"
    uploads.mkdir()
    outputs.mkdir()
    monkeypatch.setattr(server_module, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(server_module, "OUTPUT_DIR", outputs)
    now = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)
    old = (now - timedelta(hours=25)).isoformat()
    recent = (now - timedelta(hours=23)).isoformat()

    jobs = {}
    for job_id, status, finished_at in [
        ("done_old", "done", old),
        ("error_old", "error", old),
        ("queued_old", "queued", old),
        ("running_old", "running", old),
        ("done_recent", "done", recent),
    ]:
        image_path = uploads / f"{job_id}.jpg"
        output_dir = outputs / job_id
        image_path.write_bytes(b"image")
        output_dir.mkdir()
        (output_dir / "result.json").write_text("{}", encoding="utf-8")
        jobs[job_id] = {
            "id": job_id,
            "status": status,
            "finished_at": finished_at,
            "image_path": image_path,
            "output_dir": output_dir,
        }

    with server_module._jobs_lock:
        server_module._jobs.clear()
        server_module._jobs.update(jobs)
    try:
        removed = _cleanup_expired_jobs(now)
        assert set(removed) == {"done_old", "error_old"}
        assert set(server_module._jobs) == {"queued_old", "running_old", "done_recent"}
        assert not (uploads / "done_old.jpg").exists()
        assert not (outputs / "error_old").exists()
        assert (uploads / "queued_old.jpg").is_file()
        assert (outputs / "running_old").is_dir()
    finally:
        with server_module._jobs_lock:
            server_module._jobs.clear()


def test_startup_cleanup_removes_only_stale_disk_artifacts(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    outputs = tmp_path / "outputs"
    uploads.mkdir()
    outputs.mkdir()
    monkeypatch.setattr(server_module, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(server_module, "OUTPUT_DIR", outputs)
    now = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)

    def make_artifacts(job_id: str, modified_at: datetime):
        image_path = uploads / f"{job_id}.jpg"
        output_dir = outputs / job_id
        result_path = output_dir / "result.json"
        image_path.write_bytes(b"image")
        output_dir.mkdir()
        result_path.write_text("{}", encoding="utf-8")
        timestamp = modified_at.timestamp()
        for path in (image_path, result_path, output_dir):
            os.utime(path, (timestamp, timestamp))

    make_artifacts("stale", now - timedelta(hours=25))
    make_artifacts("recent", now - timedelta(hours=23))

    removed = _cleanup_stale_disk_artifacts(now)
    assert removed == ["stale"]
    assert not (uploads / "stale.jpg").exists()
    assert not (outputs / "stale").exists()
    assert (uploads / "recent.jpg").is_file()
    assert (outputs / "recent").is_dir()
