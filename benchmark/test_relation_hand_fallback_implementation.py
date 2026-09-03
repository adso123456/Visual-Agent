"""Production Implementation Contract §3.2：relation hand-conditioned fallback 实现单测
（全部 stub，禁止真实模型调用）。

覆盖：stable admission（排序/IoU>=0.80 拒绝/去重）；hand 中心过滤、top-2、100% 扩展、
clamp、view 坐标 remap；orchestrator 的 mixed-status（satisfied subject 不触发 hand
Detector 但参加 new-candidate matrix）；case 级单主体 positive control（hand Detector=0
且 hand Relation VLM=0）；每 subject 至多一次；无新增 → 0 次新 Relation VLM 且 outcome 保留；
F2::005 负例语义；core_014 0-target 语义。
"""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from visual_agent.pipeline import (
    _hand_detector_size,
    _hand_conditioned_candidates,
    _run_hand_conditioned_fallback,
    _stable_hand_candidate_admission,
)


def _image(tmp_path):
    path = tmp_path / "input.jpg"
    cv2.imwrite(str(path), np.zeros((128, 128, 3), dtype=np.uint8))
    return path


def _subject(sid, bbox):
    return {"id": sid, "label": "人", "text_label": "person", "bbox": bbox}


def _binding(subject_id, related_id, status):
    return {
        "subject_id": subject_id,
        "related_id": related_id,
        "status": status,
        "evidence": f"{subject_id}-{related_id}",
    }


class HandDetectorStub:
    """hand 与 related-object 都返回固定几何；可编程开关控制是否产生 admission。"""

    def __init__(self, hand_boxes, related_boxes, hand_center_in_subject=True):
        self.hand_boxes = hand_boxes
        self.related_boxes = related_boxes
        self.hand_center_in_subject = hand_center_in_subject
        self.calls = []

    def detect(self, image_path: Path, target_text: str, threshold: float = 0.3):
        self.calls.append((Path(image_path).name, target_text))
        if target_text == "hand":
            return [
                {"bbox": list(box), "text_label": "hand", "confidence": 0.9}
                for box in self.hand_boxes
            ]
        return [
            {"bbox": list(box), "text_label": target_text, "confidence": 0.8}
            for box in self.related_boxes
        ]


def test_full_resolution_failure_shape_is_bounded_without_allocating_image():
    assert _hand_detector_size((4932, 7032)) == (800, 1141)


def test_scaled_hand_detection_remaps_with_independent_axes(tmp_path):
    image_path = tmp_path / "large_subject.png"
    Image.new("RGB", (1701, 1001), "white").save(image_path)

    class ScaledDetector:
        def __init__(self):
            self.hand_context_size = None

        def detect(self, detection_path, target_text, threshold=0.3):
            with Image.open(detection_path) as evidence:
                if target_text == "hand":
                    assert evidence.size == (1333, 784)
                    return [
                        {
                            "bbox": [100.25, 150.5, 200.75, 250.25],
                            "text_label": "hand",
                            "confidence": 0.9,
                        }
                    ]
                self.hand_context_size = evidence.size
                return [
                    {
                        "bbox": [1.25, 2.5, 8.75, 9.5],
                        "text_label": target_text,
                        "confidence": 0.8,
                    }
                ]

    detector = ScaledDetector()
    admitted, telemetry = _hand_conditioned_candidates(
        image_path,
        _subject("A", [0.0, 0.0, 1701.0, 1001.0]),
        "fish",
        [],
        detector,
    )

    assert detector.hand_context_size == (385, 383)
    assert admitted[0]["bbox"] == [1.25, 66.5, 8.75, 73.5]
    assert telemetry["subject_view_dimensions"] == [1701, 1001]
    assert telemetry["hand_detector_dimensions"] == [1333, 784]
    assert telemetry["hand_detector_resized"] is True


def test_hand_crop_fractional_bbox_uses_floor_ceil_and_exact_remap(tmp_path):
    """非整数 hand bbox 必须按 floor/floor/ceil/ceil 扩展并精确 remap。"""
    image_path = tmp_path / "coordinate_image.png"
    pixels = np.zeros((128, 128, 3), dtype=np.uint8)
    pixels[:, :, 0] = np.arange(128, dtype=np.uint8)[None, :]
    pixels[:, :, 1] = np.arange(128, dtype=np.uint8)[:, None]
    Image.fromarray(pixels, mode="RGB").save(image_path)

    class FractionalDetector:
        def __init__(self):
            self.hand_crop_bbox = None
            self.hand_crop_size = None

        def detect(self, detection_path, target_text, threshold=0.3):
            with Image.open(detection_path).convert("RGB") as evidence:
                if target_text == "hand":
                    assert evidence.size == (69, 120)
                    return [
                        {
                            "bbox": [20.25, 30.25, 30.75, 40.75],
                            "text_label": "hand",
                            "confidence": 0.9,
                        }
                    ]
                top_left = evidence.getpixel((0, 0))
                self.hand_crop_size = evidence.size
                self.hand_crop_bbox = [
                    top_left[0],
                    top_left[1],
                    top_left[0] + evidence.width,
                    top_left[1] + evidence.height,
                ]
                return [
                    {
                        "bbox": [1.25, 2.5, 8.75, 9.5],
                        "text_label": target_text,
                        "confidence": 0.8,
                    }
                ]

    detector = FractionalDetector()
    admitted, _ = _hand_conditioned_candidates(
        image_path,
        _subject("A", [40.2, 30.4, 80.2, 100.4]),
        "fish",
        [],
        detector,
    )

    assert detector.hand_crop_bbox == [35, 24, 68, 57]
    assert detector.hand_crop_size == (33, 33)
    assert admitted[0]["bbox"] == [36.25, 26.5, 43.75, 33.5]


def test_stable_admission_ordering_dedupe_and_rejection():
    old = [
        {"bbox": [10.0, 10.0, 20.0, 20.0], "dino_confidence": 0.9},
    ]
    hand = [
        {"bbox": [10.5, 10.5, 19.5, 19.5], "dino_confidence": 0.95},  # IoU 0.81 vs old → 拒绝
        {"bbox": [40.0, 40.0, 50.0, 50.0], "dino_confidence": 0.7},
        {"bbox": [40.5, 40.5, 49.5, 49.5], "dino_confidence": 0.8},  # 与上一个 IoU 0.81 → 去重
        {"bbox": [60.0, 10.0, 70.0, 20.0], "dino_confidence": 0.75},
    ]
    admitted = _stable_hand_candidate_admission(hand, old)
    ids = [item["bbox"] for item in admitted]
    assert ids == [[40.5, 40.5, 49.5, 49.5], [60.0, 10.0, 70.0, 20.0]]


def test_hand_fallback_mixed_status_satisfied_subject_no_detector(
    tmp_path, monkeypatch
):
    """一 satisfied subject + 一 incomplete subject：incomplete 产生 admission →
    satisfied subject 不触发 hand Detector（hand_detector_calls=0），但参加 new-candidate matrix。"""
    image_path = _image(tmp_path)
    subjects = [
        _subject("A", [20.0, 20.0, 60.0, 100.0]),
        _subject("B", [70.0, 20.0, 110.0, 100.0]),
    ]
    detector = HandDetectorStub(
        hand_boxes=[[24.0, 40.0, 44.0, 60.0]],  # subject view 坐标系（B 的 35% view 内）
        related_boxes=[[10.0, 30.0, 30.0, 50.0]],  # hand view 坐标系
    )
    related_candidates = []
    relation_bindings = [_binding("A", "R1", "satisfied")]  # A 已 satisfied
    relation_protocols = [{"attempts": 1}]
    relation_calls = []
    monkeypatch.setattr(
        "visual_agent.pipeline.verify_relations",
        lambda _p, subjects, related, *_args: (
            [_binding(subjects[0]["id"], item["id"], "satisfied") for item in related],
            {"attempts": 1},
        ),
    )
    monkeypatch.setattr(
        "visual_agent.pipeline._resolve_focused_ownership",
        lambda *args, **kwargs: relation_bindings,
    )
    fallback = _run_hand_conditioned_fallback(
        image_path=image_path,
        relation_subjects=subjects,
        relation_candidates=related_candidates,
        relation_bindings=relation_bindings,
        related_plan={"object": "umbrella", "relation": "held_by_target"},
        detector=detector,
        relation_protocols=relation_protocols,
    )
    telemetry = fallback["telemetry"]
    assert telemetry["attempts"] == 1
    assert telemetry["admitted_count"] == 1
    assert telemetry["subjects"]["A"]["hand_detector_calls"] == 0  # satisfied 不触发
    assert telemetry["subjects"]["A"]["hand_relation_calls"] == 1  # 仍参加 matrix
    assert telemetry["subjects"]["B"]["hand_detector_calls"] == 1
    assert telemetry["hand_relation_calls"] == 2  # A、B 各一次
    assert len(fallback["relation_candidates"]) == 1
    assert fallback["relation_candidates"][0]["id"] == "R1"


def test_hand_fallback_positive_control_case_gate(tmp_path, monkeypatch):
    """case 级单主体 positive control：整案无 incomplete subject ⇒
    hand Detector=0 且 hand Relation VLM=0（F2::024 / core_003 语义）。"""
    image_path = _image(tmp_path)
    subjects = [_subject("A", [20.0, 20.0, 60.0, 100.0])]
    detector = HandDetectorStub(hand_boxes=[], related_boxes=[])
    bindings = [_binding("A", "R1", "satisfied")]
    fallback = _run_hand_conditioned_fallback(
        image_path=image_path,
        relation_subjects=subjects,
        relation_candidates=[{"id": "R1", "bbox": [0.0, 0.0, 1.0, 1.0]}],
        relation_bindings=bindings,
        related_plan={"object": "umbrella", "relation": "held_by_target"},
        detector=detector,
        relation_protocols=[{"attempts": 1}],
    )
    telemetry = fallback["telemetry"]
    assert telemetry["attempts"] == 0
    assert telemetry["detector_calls"] == 0
    assert telemetry["hand_relation_calls"] == 0
    assert detector.calls == []


def test_hand_fallback_per_subject_max_once(tmp_path, monkeypatch):
    """incomplete subject 至多执行一次 hand localization（即使有多个 hand）。"""
    image_path = _image(tmp_path)
    subjects = [_subject("B", [70.0, 20.0, 110.0, 100.0])]
    detector = HandDetectorStub(
        hand_boxes=[[80.0, 40.0, 100.0, 60.0], [85.0, 45.0, 105.0, 65.0]],
        related_boxes=[[82.0, 42.0, 98.0, 58.0]],
    )
    monkeypatch.setattr(
        "visual_agent.pipeline.verify_relations",
        lambda _p, subjects, related, *_args: (
            [_binding(subjects[0]["id"], item["id"], "satisfied") for item in related],
            {"attempts": 1},
        ),
    )
    monkeypatch.setattr(
        "visual_agent.pipeline._resolve_focused_ownership",
        lambda *args, **kwargs: [],
    )
    fallback = _run_hand_conditioned_fallback(
        image_path=image_path,
        relation_subjects=subjects,
        relation_candidates=[],
        relation_bindings=[],
        related_plan={"object": "umbrella", "relation": "held_by_target"},
        detector=detector,
        relation_protocols=[],
    )
    telemetry = fallback["telemetry"]
    assert telemetry["subjects"]["B"]["hand_detector_calls"] == 1
    assert telemetry["attempts"] == 1


def test_hand_fallback_no_admission_zero_new_relation_calls(tmp_path, monkeypatch):
    """无有效 hand / 无新增 related candidate → 0 次新 Relation VLM，outcome 保留。"""
    image_path = _image(tmp_path)
    subjects = [_subject("B", [70.0, 20.0, 110.0, 100.0])]
    detector = HandDetectorStub(hand_boxes=[], related_boxes=[])
    relation_calls = []
    monkeypatch.setattr(
        "visual_agent.pipeline.verify_relations",
        lambda *args: relation_calls.append(args) or ([(args[0],)], {}),
    )
    fallback = _run_hand_conditioned_fallback(
        image_path=image_path,
        relation_subjects=subjects,
        relation_candidates=[],
        relation_bindings=[],
        related_plan={"object": "umbrella", "relation": "held_by_target"},
        detector=detector,
        relation_protocols=[],
    )
    assert fallback["telemetry"]["admitted_count"] == 0
    assert fallback["telemetry"]["hand_relation_calls"] == 0
    assert relation_calls == []
    assert fallback["relation_bindings"] == []


def test_hand_fallback_admitted_but_zero_satisfied_f2_005_semantics(
    tmp_path, monkeypatch
):
    """F2::005 负例：admitted 后仍 0 satisfied → 保留既有 outcome，不产生误绑定。"""
    image_path = _image(tmp_path)
    subjects = [_subject("B", [70.0, 20.0, 110.0, 100.0])]
    detector = HandDetectorStub(
        hand_boxes=[[24.0, 40.0, 44.0, 60.0]],  # subject view 坐标系
        related_boxes=[[10.0, 30.0, 30.0, 50.0]],  # hand view 坐标系
    )
    monkeypatch.setattr(
        "visual_agent.pipeline.verify_relations",
        lambda _p, subjects, related, *_args: (
            [_binding(subjects[0]["id"], item["id"], "not_satisfied") for item in related],
            {"attempts": 1},
        ),
    )
    monkeypatch.setattr(
        "visual_agent.pipeline._resolve_focused_ownership",
        lambda *args, **kwargs: [_binding("B", "R1", "not_satisfied")],
    )
    fallback = _run_hand_conditioned_fallback(
        image_path=image_path,
        relation_subjects=subjects,
        relation_candidates=[],
        relation_bindings=[],
        related_plan={"object": "umbrella", "relation": "held_by_target"},
        detector=detector,
        relation_protocols=[],
    )
    assert fallback["telemetry"]["admitted_count"] == 1
    assert all(
        binding["status"] != "satisfied"
        for binding in fallback["relation_bindings"]
    )


def test_hand_fallback_core_014_zero_target_semantics(tmp_path, monkeypatch):
    """core_014 语义：0 个 relation-eligible subject → 全链路 0 次新调用。"""
    image_path = _image(tmp_path)
    fallback = _run_hand_conditioned_fallback(
        image_path=image_path,
        relation_subjects=[],
        relation_candidates=[],
        relation_bindings=[],
        related_plan={"object": "umbrella", "relation": "held_by_target"},
        detector=HandDetectorStub([], []),
        relation_protocols=[],
    )
    telemetry = fallback["telemetry"]
    assert telemetry["attempts"] == 0
    assert telemetry["detector_calls"] == 0
    assert telemetry["hand_relation_calls"] == 0
    assert fallback["relation_candidates"] == []
