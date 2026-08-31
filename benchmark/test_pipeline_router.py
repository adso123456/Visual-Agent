import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from visual_agent.pipeline import run_pipeline


def _plan(constraints, action="outline", related_objects=None):
    return {
        "target_object": "person",
        "label": "测试人物",
        "constraints": constraints,
        "action": {"type": action},
        "related_objects": related_objects or [],
    }


class DetectorStub:
    device = "cpu"
    load_seconds = 0.0
    memory_after_load_mb = 0.0

    def __init__(self, count=1):
        self.count = count
        self.calls = []

    def detect(self, _image_path: Path, target_object: str, threshold: float = 0.3):
        self.calls.append(target_object)
        if target_object == "hand":
            return []
        return [
            {
                "bbox": [2 + 10 * index, 3, 10 + 10 * index, 20],
                "text_label": target_object,
                "confidence": 0.9,
            }
            for index in range(self.count)
        ]


class SegmenterStub:
    device = "cpu"
    load_seconds = 0.0
    memory_after_load_mb = 0.0

    def __init__(self):
        self.calls = []

    def segment(self, image_path, boxes):
        self.calls.append([list(box) for box in boxes])
        image = cv2.imread(str(image_path))
        results = []
        for box in boxes:
            mask = np.zeros(image.shape[:2], dtype=bool)
            x1, y1, x2, y2 = map(int, box)
            mask[y1:y2, x1:x2] = True
            results.append({"mask": mask, "score": 0.95})
        return results, {
            "model": "stub",
            "device": "cpu",
            "load_seconds": 0.0,
            "inference_seconds": 0.01,
            "memory_after_load_mb": 0.0,
            "peak_memory_mb": 0.0,
        }


def _image(tmp_path):
    path = tmp_path / "input.jpg"
    cv2.imwrite(str(path), np.zeros((32, 48, 3), dtype=np.uint8))
    return path


def _install_common(monkeypatch, detector, segmenter, routed_calls, validity_calls):
    monkeypatch.setattr(
        "visual_agent.pipeline.get_detector", lambda fresh=False: (detector, True)
    )
    monkeypatch.setattr(
        "visual_agent.pipeline.get_segmenter", lambda fresh=False: (segmenter, True)
    )

    def validity(candidate, target_object, evidence):
        validity_calls.append((candidate["id"], target_object, evidence.size))
        return {
            "candidate_id": candidate["id"],
            "target_object": target_object,
            "status": "valid",
            "evidence": "有效独立实例",
        }, {"attempts": 1, "retry_count": 0, "recovered": False, "first_error_code": None}

    def routed(candidate, constraints, evidence, route):
        sizes = (
            [item.size for item in evidence]
            if isinstance(evidence, list)
            else [evidence.size]
        )
        routed_calls.append((candidate["id"], route, [item["text"] for item in constraints], sizes))
        return [
            {"constraint": item["text"], "status": "satisfied", "evidence": f"{route} 证据"}
            for item in constraints
        ], {"attempts": 1, "retry_count": 0, "recovered": False, "first_error_code": None}

    monkeypatch.setattr("visual_agent.pipeline.verify_subject_instance", validity)
    monkeypatch.setattr("visual_agent.pipeline.verify_candidate_constraints", routed)


def test_semantic_three_candidates_use_one_subject_sam_batch_and_reuse_masks(tmp_path, monkeypatch):
    detector = DetectorStub(count=3)
    segmenter = SegmenterStub()
    routed_calls = []
    validity_calls = []
    _install_common(monkeypatch, detector, segmenter, routed_calls, validity_calls)

    _, result_path = run_pipeline(
        _image(tmp_path),
        "描边穿红衣服的人",
        plan=_plan([{"text": "穿红衣服", "route": "attribute"}]),
        verify=True,
        final_response=False,
        output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert len(segmenter.calls) == 1
    assert len(segmenter.calls[0]) == 3
    assert len(validity_calls) == 3
    assert len(routed_calls) == 3
    assert len(result["targets"]) == 3


def test_mixed_routes_use_separate_requests_and_restore_original_order(tmp_path, monkeypatch):
    detector = DetectorStub()
    segmenter = SegmenterStub()
    routed_calls = []
    validity_calls = []
    _install_common(monkeypatch, detector, segmenter, routed_calls, validity_calls)
    constraints = [
        {"text": "正在跑步", "route": "behavior"},
        {"text": "穿红衣服", "route": "attribute"},
        {"text": "戴眼镜", "route": "attribute"},
    ]

    _, result_path = run_pipeline(
        _image(tmp_path),
        "描边穿红衣服且正在跑步的人",
        plan=_plan(constraints),
        verify=True,
        final_response=False,
        output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert [(call[1], call[2]) for call in routed_calls] == [
        ("attribute", ["穿红衣服", "戴眼镜"]),
        ("behavior", ["正在跑步"]),
    ]
    assert [item["constraint"] for item in result["candidates"][0]["verification_checks"]] == [
        "正在跑步",
        "穿红衣服",
        "戴眼镜",
    ]
    assert len(segmenter.calls) == 1


def test_no_constraint_box_skips_qwen_and_sam(tmp_path, monkeypatch):
    detector = DetectorStub()
    monkeypatch.setattr("visual_agent.pipeline.get_detector", lambda fresh=False: (detector, True))
    monkeypatch.setattr(
        "visual_agent.pipeline.get_segmenter",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("不得加载 SAM")),
    )
    monkeypatch.setattr(
        "visual_agent.pipeline.verify_subject_instance",
        lambda *_args: (_ for _ in ()).throw(AssertionError("不得调用 validity Qwen")),
    )

    _, result_path = run_pipeline(
        _image(tmp_path),
        "框出所有人",
        plan=_plan([], action="box"),
        verify=True,
        final_response=False,
        output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert len(result["targets"]) == 1
    assert result["timings"]["sam2"] is None


def test_no_constraint_outline_uses_one_sam_batch_without_qwen(tmp_path, monkeypatch):
    detector = DetectorStub(count=2)
    segmenter = SegmenterStub()
    monkeypatch.setattr("visual_agent.pipeline.get_detector", lambda fresh=False: (detector, True))
    monkeypatch.setattr("visual_agent.pipeline.get_segmenter", lambda fresh=False: (segmenter, True))
    monkeypatch.setattr(
        "visual_agent.pipeline.verify_subject_instance",
        lambda *_args: (_ for _ in ()).throw(AssertionError("不得调用 validity Qwen")),
    )

    run_pipeline(
        _image(tmp_path),
        "描边所有人",
        plan=_plan([], action="outline"),
        verify=True,
        final_response=False,
        output_dir=tmp_path / "out",
    )
    assert len(segmenter.calls) == 1
    assert len(segmenter.calls[0]) == 2


@pytest.mark.parametrize(
    ("constraint", "prompt"),
    [
        ({"text": "穿红衣服", "route": "attribute"}, "框出穿红衣服的人"),
        ({"text": "正在跑步", "route": "behavior"}, "框出正在跑步的人"),
    ],
)
def test_semantic_box_runs_subject_sam_but_not_render_sam(
    tmp_path, monkeypatch, constraint, prompt
):
    detector = DetectorStub()
    segmenter = SegmenterStub()
    routed_calls = []
    validity_calls = []
    _install_common(monkeypatch, detector, segmenter, routed_calls, validity_calls)

    _, result_path = run_pipeline(
        _image(tmp_path),
        prompt,
        plan=_plan([constraint], action="box"),
        verify=True,
        final_response=False,
        output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert len(segmenter.calls) == 1
    assert len(result["targets"]) == 1
    assert "segmentation" not in result["targets"][0]


def test_behavior_fallback_rechecks_only_uncertain_and_cannot_overturn_binary(
    tmp_path, monkeypatch
):
    detector = DetectorStub(count=2)
    segmenter = SegmenterStub()
    monkeypatch.setattr(
        "visual_agent.pipeline.get_detector", lambda fresh=False: (detector, True)
    )
    monkeypatch.setattr(
        "visual_agent.pipeline.get_segmenter", lambda fresh=False: (segmenter, True)
    )
    monkeypatch.setattr(
        "visual_agent.pipeline.verify_subject_instance",
        lambda candidate, target, evidence: (
            {
                "candidate_id": candidate["id"],
                "target_object": target,
                "status": "valid",
                "evidence": "有效实例",
            },
            {"attempts": 1},
        ),
    )
    calls = []

    def routed(candidate, constraints, evidence, route):
        calls.append(
            {
                "constraints": [item["text"] for item in constraints],
                "evidence_sizes": [item.size for item in evidence],
            }
        )
        if len(calls) == 1:
            return [
                {"constraint": "正在跑步", "status": "satisfied", "evidence": "动作明确"},
                {"constraint": "正在挥手", "status": "uncertain", "evidence": "局部不足"},
            ], {"attempts": 1}
        return [
            {"constraint": "正在挥手", "status": "not_satisfied", "evidence": "全图仍未见"}
        ], {"attempts": 1}

    monkeypatch.setattr(
        "visual_agent.pipeline.verify_candidate_constraints",
        routed,
    )
    constraints = [
        {"text": "正在跑步", "route": "behavior"},
        {"text": "正在挥手", "route": "behavior"},
    ]

    _, result_path = run_pipeline(
        _image(tmp_path),
        "框出正在跑步且挥手的人",
        plan=_plan(constraints, action="box"),
        verify=True,
        final_response=False,
        output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert calls[0]["constraints"] == ["正在跑步", "正在挥手"]
    assert len(calls[0]["evidence_sizes"]) == 2
    assert calls[1]["constraints"] == ["正在挥手"]
    assert len(calls[1]["evidence_sizes"]) == 3
    checks = result["candidates"][0]["verification_checks"]
    assert checks[0]["status"] == "satisfied"
    assert checks[1]["status"] == "not_satisfied"
