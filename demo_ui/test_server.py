import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from demo_ui.server import (
    EXAMPLE_PLANS,
    Handler,
    STATIC_DIR,
    _build_summary,
    _candidate_status,
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
    assert "0 final targets — valid negative result" in script


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
            assert b"Visual Agent Developer Demo" in response.read()
        with urllib.request.urlopen(base + "/static/app.js") as response:
            assert response.headers.get_content_type() == "application/javascript"
    finally:
        httpd.shutdown()
        httpd.server_close()
