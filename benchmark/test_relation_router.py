import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from visual_agent import pipeline


SUBJECTS = [
    {"id": "A", "bbox": [2, 2, 12, 24]},
    {"id": "B", "bbox": [16, 2, 28, 24]},
]
RELATED = [
    {"id": "R1", "bbox": [8, 8, 16, 20]},
    {"id": "R2", "bbox": [24, 8, 32, 20]},
]
PLAN = {
    "target_object": "person",
    "label": "拿雨伞的人",
    "constraints": [{"text": "拿着雨伞", "route": "relation"}],
    "action": {"type": "box"},
    "related_objects": [{"object": "umbrella", "relation": "held_by_target"}],
}


def _binding(subject, related, status, evidence=None):
    return {
        "subject_id": subject,
        "related_id": related,
        "relation": "held_by_target",
        "status": status,
        "evidence": evidence or f"{subject}-{related}-{status}",
    }


def test_relation_resolver_freezes_all_status_mappings():
    absent = pipeline.resolve_relation_outcomes(SUBJECTS[:1], [], [], PLAN)["A"]
    assert (absent["status"], absent["completion_reason"]) == (
        "uncertain",
        "related_object_not_detected",
    )

    unique = pipeline.resolve_relation_outcomes(
        SUBJECTS[:1],
        RELATED,
        [_binding("A", "R1", "satisfied"), _binding("A", "R2", "uncertain")],
        PLAN,
    )["A"]
    assert unique["status"] == "satisfied"
    assert unique["completion_reason"] is None
    assert unique["group"]["composite_complete"] is True

    multiple_for_same_subject = pipeline.resolve_relation_outcomes(
        SUBJECTS[:1],
        [
            {**RELATED[0], "dino_confidence": 0.7},
            {**RELATED[1], "dino_confidence": 0.9},
        ],
        [_binding("A", "R1", "satisfied"), _binding("A", "R2", "satisfied")],
        PLAN,
    )["A"]
    assert multiple_for_same_subject["status"] == "satisfied"
    assert multiple_for_same_subject["completion_reason"] is None
    assert multiple_for_same_subject["related_member"]["candidate_id"] == "R2"

    uncertain = pipeline.resolve_relation_outcomes(
        SUBJECTS[:1],
        RELATED,
        [_binding("A", "R1", "uncertain"), _binding("A", "R2", "not_satisfied")],
        PLAN,
    )["A"]
    assert (uncertain["status"], uncertain["completion_reason"]) == (
        "uncertain",
        "binding_uncertain",
    )

    negative = pipeline.resolve_relation_outcomes(
        SUBJECTS[:1],
        RELATED,
        [_binding("A", "R1", "not_satisfied"), _binding("A", "R2", "not_satisfied")],
        PLAN,
    )["A"]
    assert (negative["status"], negative["completion_reason"]) == (
        "not_satisfied",
        "binding_not_satisfied",
    )

    conflict = pipeline.resolve_relation_outcomes(
        SUBJECTS,
        RELATED[:1],
        [_binding("A", "R1", "satisfied"), _binding("B", "R1", "satisfied")],
        PLAN,
    )
    assert all(
        (item["status"], item["completion_reason"])
        == ("uncertain", "binding_conflict")
        for item in conflict.values()
    )


class DetectorStub:
    device = "cpu"
    load_seconds = 0.0
    memory_after_load_mb = 0.0

    def __init__(self):
        self.calls = []

    def detect(self, _image_path: Path, target_object: str):
        self.calls.append(target_object)
        if target_object == "person":
            return [{"bbox": [2, 2, 14, 26], "text_label": "person", "confidence": 0.9}]
        return [{"bbox": [10, 8, 20, 22], "text_label": "umbrella", "confidence": 0.8}]


class TwoSubjectDetectorStub(DetectorStub):
    def detect(self, _image_path: Path, target_object: str):
        self.calls.append(target_object)
        if target_object == "person":
            return [
                {"bbox": [2, 2, 14, 26], "text_label": "person", "confidence": 0.9},
                {"bbox": [22, 2, 36, 26], "text_label": "person", "confidence": 0.85},
            ]
        return [
            {"bbox": [8, 8, 16, 22], "text_label": "umbrella", "confidence": 0.8},
            {"bbox": [24, 8, 34, 22], "text_label": "umbrella", "confidence": 0.75},
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
            results.append({"mask": mask, "score": 0.9})
        return results, {
            "model": "stub", "device": "cpu", "load_seconds": 0.0,
            "inference_seconds": 0.01, "memory_after_load_mb": 0.0,
            "peak_memory_mb": 0.0,
        }


def _image(tmp_path):
    path = tmp_path / "input.jpg"
    cv2.imwrite(str(path), np.zeros((32, 40, 3), dtype=np.uint8))
    return path


@pytest.mark.parametrize(
    ("validity", "expected_check"),
    [("invalid", "not_satisfied"), ("uncertain", "uncertain")],
)
def test_non_valid_subject_never_enters_relation(
    tmp_path, monkeypatch, validity, expected_check
):
    detector = DetectorStub()
    segmenter = SegmenterStub()
    monkeypatch.setattr(pipeline, "get_detector", lambda fresh=False: (detector, True))
    monkeypatch.setattr(pipeline, "get_segmenter", lambda fresh=False: (segmenter, True))
    monkeypatch.setattr(
        pipeline,
        "verify_subject_instance",
        lambda candidate, target, evidence: (
            {"candidate_id": candidate["id"], "target_object": target, "status": validity, "evidence": "前置证据"},
            {"attempts": 1},
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "verify_relations",
        lambda *_args: (_ for _ in ()).throw(AssertionError("无效主体不得进入 Relation")),
    )

    _, result_path = pipeline.run_pipeline(
        _image(tmp_path), "框出拿雨伞的人", plan=PLAN, verify=True,
        final_response=False, output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert detector.calls == ["person"]
    assert len(segmenter.calls) == 1
    assert result["candidates"][0]["verification_checks"][0]["status"] == expected_check
    assert result["targets"] == []


def test_relation_check_and_group_share_single_resolver_outcome(tmp_path, monkeypatch):
    detector = DetectorStub()
    segmenter = SegmenterStub()
    monkeypatch.setattr(pipeline, "get_detector", lambda fresh=False: (detector, True))
    monkeypatch.setattr(pipeline, "get_segmenter", lambda fresh=False: (segmenter, True))
    monkeypatch.setattr(
        pipeline,
        "verify_subject_instance",
        lambda candidate, target, evidence: (
            {"candidate_id": candidate["id"], "target_object": target, "status": "valid", "evidence": "独立人物"},
            {"attempts": 1},
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "verify_relations",
        lambda *_args: ([_binding("A", "R1", "satisfied", "直接持握")], {"attempts": 1}),
    )
    original_resolver = pipeline.resolve_relation_outcomes
    calls = []

    def counted_resolver(*args):
        calls.append(args)
        return original_resolver(*args)

    monkeypatch.setattr(pipeline, "resolve_relation_outcomes", counted_resolver)

    _, result_path = pipeline.run_pipeline(
        _image(tmp_path), "框出拿雨伞的人", plan=PLAN, verify=True,
        final_response=False, output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    check = result["candidates"][0]["verification_checks"][0]
    group = result["semantic_groups"][0]
    assert len(calls) == 1
    assert check["status"] == "satisfied"
    assert check["evidence"] == "直接持握"
    assert group["completion_reason"] is None
    assert group["composite_complete"] is True
    assert len(result["targets"]) == 1
    assert detector.calls == ["person", "umbrella"]
    assert len(segmenter.calls) == 1


def test_relation_verification_isolated_per_subject_with_all_related_candidates(
    tmp_path, monkeypatch
):
    detector = TwoSubjectDetectorStub()
    segmenter = SegmenterStub()
    monkeypatch.setattr(pipeline, "get_detector", lambda fresh=False: (detector, True))
    monkeypatch.setattr(pipeline, "get_segmenter", lambda fresh=False: (segmenter, True))
    monkeypatch.setattr(
        pipeline,
        "verify_subject_instance",
        lambda candidate, target, evidence: (
            {"candidate_id": candidate["id"], "target_object": target, "status": "valid", "evidence": "独立人物"},
            {"attempts": 1},
        ),
    )
    calls = []

    def record_relation_call(_image_path, subjects, related, *_args):
        calls.append(
            {
                "subjects": [subject["id"] for subject in subjects],
                "related": [candidate["id"] for candidate in related],
            }
        )
        subject_id = subjects[0]["id"]
        satisfied_id = "R1" if subject_id == "A" else "R2"
        return (
            [
                _binding(
                    subject_id,
                    candidate["id"],
                    "satisfied" if candidate["id"] == satisfied_id else "not_satisfied",
                )
                for candidate in related
            ],
            {"attempts": 1},
        )

    monkeypatch.setattr(pipeline, "verify_relations", record_relation_call)

    pipeline.run_pipeline(
        _image(tmp_path), "框出拿雨伞的人", plan=PLAN, verify=True,
        final_response=False, output_dir=tmp_path / "out",
    )

    assert calls == [
        {"subjects": ["A"], "related": ["R1", "R2"]},
        {"subjects": ["B"], "related": ["R1", "R2"]},
    ]


def test_relation_secondary_grounding_is_once_per_unsatisfied_subject_and_remaps_bbox(
    tmp_path, monkeypatch
):
    class SecondaryDetector(DetectorStub):
        def detect(self, image_path: Path, target_object: str):
            self.calls.append((Path(image_path).name, target_object))
            if target_object == "person":
                return [
                    {
                        "bbox": [10, 4, 20, 28],
                        "text_label": "person",
                        "confidence": 0.9,
                    }
                ]
            if Path(image_path).name == "input.jpg":
                return [
                    {
                        "bbox": [2, 2, 6, 8],
                        "text_label": "umbrella",
                        "confidence": 0.7,
                    }
                ]
            return [
                {
                    "bbox": [3, 5, 8, 14],
                    "text_label": "umbrella",
                    "confidence": 0.8,
                }
            ]

    detector = SecondaryDetector()
    segmenter = SegmenterStub()
    monkeypatch.setattr(pipeline, "get_detector", lambda fresh=False: (detector, True))
    monkeypatch.setattr(pipeline, "get_segmenter", lambda fresh=False: (segmenter, True))
    monkeypatch.setattr(
        pipeline,
        "verify_subject_instance",
        lambda candidate, target, evidence: (
            {"candidate_id": candidate["id"], "target_object": target, "status": "valid", "evidence": "独立人物"},
            {"attempts": 1},
        ),
    )
    relation_calls = []

    def verify(_image_path, subjects, related, *_args):
        relation_calls.append([item["id"] for item in related])
        status = "not_satisfied" if related[0]["id"] == "R1" else "satisfied"
        return (
            [_binding(subjects[0]["id"], item["id"], status) for item in related],
            {"attempts": 1},
        )

    monkeypatch.setattr(pipeline, "verify_relations", verify)

    _, result_path = pipeline.run_pipeline(
        _image(tmp_path), "框出拿雨伞的人", plan=PLAN, verify=True,
        final_response=False, output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert detector.calls == [
        ("input.jpg", "person"),
        ("input.jpg", "umbrella"),
        ("subject_context.png", "umbrella"),
    ]
    assert relation_calls == [["R1"], ["R2"]]
    # subject bbox [10,4,20,28] 的固定 35% crop 起点为 [6,0]。
    assert result["relation_candidates"][1]["bbox"] == [9, 5, 14, 14]
    assert result["candidates"][0]["verification_checks"][0]["status"] == "satisfied"


def test_relation_secondary_candidate_enters_full_cross_subject_universe(
    tmp_path, monkeypatch
):
    class SecondaryDetector(DetectorStub):
        def detect(self, image_path: Path, target_object: str):
            self.calls.append((Path(image_path).name, target_object))
            if target_object == "person":
                return [
                    {
                        "bbox": [2, 2, 14, 26],
                        "text_label": "person",
                        "confidence": 0.9,
                    },
                    {
                        "bbox": [22, 2, 36, 26],
                        "text_label": "person",
                        "confidence": 0.85,
                    },
                ]
            if Path(image_path).name == "input.jpg":
                # full-scene related grounding 无发现
                return []
            # 只让第一个 subject 的 secondary crop 发现雨伞；第二个 crop 无发现
            secondary_count = sum(
                1
                for name, target in self.calls
                if name == "subject_context.png"
            )
            if secondary_count == 1:
                return [
                    {
                        "bbox": [3, 5, 8, 14],
                        "text_label": "umbrella",
                        "confidence": 0.8,
                    }
                ]
            return []

    detector = SecondaryDetector()
    segmenter = SegmenterStub()
    monkeypatch.setattr(pipeline, "get_detector", lambda fresh=False: (detector, True))
    monkeypatch.setattr(pipeline, "get_segmenter", lambda fresh=False: (segmenter, True))
    monkeypatch.setattr(
        pipeline,
        "verify_subject_instance",
        lambda candidate, target, evidence: (
            {
                "candidate_id": candidate["id"],
                "target_object": target,
                "status": "valid",
                "evidence": "独立人物",
            },
            {"attempts": 1},
        ),
    )
    relation_calls = []
    focused_calls = []

    def verify(_image_path, subjects, related, *_args):
        subject_id = subjects[0]["id"]
        related_ids = [item["id"] for item in related]
        relation_calls.append((subject_id, related_ids))
        return (
            [
                _binding(subject_id, related_id, "satisfied")
                for related_id in related_ids
            ],
            {"attempts": 1},
        )

    def focused(_image_path, subjects, related, *_args):
        focused_calls.append(
            (
                sorted(subject["id"] for subject in subjects),
                related[0]["id"],
            )
        )
        return (
            [
                _binding("A", related[0]["id"], "satisfied"),
                _binding("B", related[0]["id"], "not_satisfied"),
            ],
            {"attempts": 1},
        )

    monkeypatch.setattr(pipeline, "verify_relations", verify)
    monkeypatch.setattr(pipeline, "verify_focused_ownership", focused)

    _, result_path = pipeline.run_pipeline(
        _image(tmp_path),
        "框出拿雨伞的人",
        plan=PLAN,
        verify=True,
        final_response=False,
        output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))

    # full-scene 无初始候选 → 两个 unsatisfied subject 各触发一次 secondary grounding
    assert detector.calls == [
        ("input.jpg", "person"),
        ("input.jpg", "umbrella"),
        ("subject_context.png", "umbrella"),
        ("subject_context.png", "umbrella"),
    ]
    # 新增候选 R1 必须对 A、B 都完成关系判断（保持单 subject isolation）
    assert relation_calls == [
        ("A", ["R1"]),
        ("B", ["R1"]),
    ]
    # A、B 均 satisfied R1 → focused ownership 必须被调用
    assert focused_calls == [(["A", "B"], "R1")]
    # 最终 binding matrix 不缺少任一应有 subject-R1 pair
    pairs = {
        (binding["subject_id"], binding["related_id"])
        for binding in result["relation_bindings"]
    }
    assert pairs == {("A", "R1"), ("B", "R1")}
    statuses = {
        binding["subject_id"]: binding["status"]
        for binding in result["relation_bindings"]
    }
    assert statuses == {"A": "satisfied", "B": "not_satisfied"}
    checks = {
        candidate["id"]: candidate["verification_checks"][0]["status"]
        for candidate in result["candidates"]
    }
    assert checks == {"A": "satisfied", "B": "not_satisfied"}
    # 只有 A 最终成为 target
    assert [target["id"] for target in result["targets"]] == ["A"]


def test_relation_mask_action_reuses_subject_and_segments_related_only_on_demand(
    tmp_path, monkeypatch
):
    detector = DetectorStub()
    segmenter = SegmenterStub()
    monkeypatch.setattr(pipeline, "get_detector", lambda fresh=False: (detector, True))
    monkeypatch.setattr(pipeline, "get_segmenter", lambda fresh=False: (segmenter, True))
    monkeypatch.setattr(
        pipeline,
        "verify_subject_instance",
        lambda candidate, target, evidence: (
            {"candidate_id": candidate["id"], "target_object": target, "status": "valid", "evidence": "独立人物"},
            {"attempts": 1},
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "verify_relations",
        lambda *_args: ([_binding("A", "R1", "satisfied")], {"attempts": 1}),
    )
    outline_plan = {**PLAN, "action": {"type": "outline"}}

    pipeline.run_pipeline(
        _image(tmp_path), "描边拿雨伞的人", plan=outline_plan, verify=True,
        final_response=False, output_dir=tmp_path / "out",
    )

    assert len(segmenter.calls) == 2
    assert segmenter.calls[0] == [[2, 2, 14, 26]]
    assert segmenter.calls[1] == [[10, 8, 20, 22]]
