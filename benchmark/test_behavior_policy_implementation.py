"""Production Implementation Contract §3.2：behavior 确定性路由实现单测（全部 stub，无模型调用）。

覆盖：identity_contamination_risk 冻结向量表 15/15；_object_mediated_behavior_constraint_indices
冻结 marker；blend 公式 byte-exact；routing 决策（satisfied/uncertain-single/uncertain-multi/
not_satisfied-armed）；fallback 复用 first-pass 证据对象；write-back 位置集；不可覆写；每 candidate 至多一次 fallback。
"""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from visual_agent.evidence import (
    blend_non_target_people,
    identity_contamination_risk,
)
from visual_agent.pipeline import (
    OBJECT_MEDIATED_BEHAVIOR_MARKER,
    _object_mediated_behavior_constraint_indices,
    run_pipeline,
)

HERE = Path(__file__).resolve().parent
FROZEN_TABLE = json.loads(
    (HERE / "r3_frozen_identity_table.json").read_text(encoding="utf-8")
)

# 合同 §1.3 冻结向量表（15/15）
EXPECTED_VECTORS = {
    "challenge_001": {"A": True, "B": True},
    "challenge_003": {"A": False},
    "challenge_004": {"A": True, "B": False},
    "F1::fishing_001.jpeg": {"A": False},
    "F1::fishing_005.jpeg": {"A": False},
    "F1::fishing_010.jpeg": {"A": False, "B": False, "C": False},
    "F1::fishing_014.jpeg": {"A": False, "B": False, "C": False},
    "F1::fishing_004.jpeg": {"A": False},
    "F1::fishing_018.jpeg": {"A": False},
}


def _plan(constraints, action="box", related_objects=None):
    return {
        "target_object": "person",
        "label": "测试人物",
        "constraints": constraints,
        "action": {"type": action},
        "related_objects": related_objects or [],
    }


def _image(tmp_path):
    path = tmp_path / "input.jpg"
    cv2.imwrite(str(path), np.zeros((32, 48, 3), dtype=np.uint8))
    return path


class DetectorStub:
    device = "cpu"
    load_seconds = 0.0
    memory_after_load_mb = 0.0

    def __init__(self, count=1):
        self.count = count
        self.calls = []

    def detect(self, _image_path, target_object, threshold=0.3):
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
        image = cv2.imread(str(image_path))
        results = []
        for box in boxes:
            mask = np.zeros(image.shape[:2], dtype=bool)
            x1, y1, x2, y2 = map(int, box)
            mask[y1:y2, x1:x2] = True
            results.append({"mask": mask, "score": 0.95})
        return results, {"model": "stub", "device": "cpu"}


def _install(monkeypatch, detector, routed):
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
    monkeypatch.setattr("visual_agent.pipeline.verify_candidate_constraints", routed)


def test_identity_contamination_risk_frozen_vector_table():
    total = 0
    for case_id, expected in EXPECTED_VECTORS.items():
        case = FROZEN_TABLE[case_id]
        candidates = case["candidates"]
        for candidate in candidates:
            got = identity_contamination_risk(
                tuple(case["image_size"]),
                candidate["id"],
                candidates,
            )
            assert got == expected[candidate["id"]], (
                f"{case_id} {candidate['id']}: got={got} want={expected[candidate['id']]}"
            )
            total += 1
    assert total == 15


def test_identity_contamination_risk_excludes_by_id_not_bbox_equality():
    """同 bbox 双 ID：只能按 ID 排除，不能因 bbox 相同互相误判。"""
    candidates = [
        {"id": "A", "bbox": [100.0, 100.0, 300.0, 400.0]},
        {"id": "B", "bbox": [100.0, 100.0, 300.0, 400.0]},
    ]
    # crop 覆盖邻居 100% 且邻居中心在 crop 内 → 仅当邻居是不同 ID 时才为 True
    assert identity_contamination_risk((600, 600), "A", candidates) is True
    # 单候选 → False（即使 bbox 相同）
    assert identity_contamination_risk((600, 600), "A", candidates[:1]) is False


def test_identity_contamination_risk_single_candidate_false():
    candidates = [{"id": "A", "bbox": [10.0, 10.0, 50.0, 80.0]}]
    assert identity_contamination_risk((100, 100), "A", candidates) is False


def test_object_mediated_indices_only_exact_marker():
    plan = _plan(
        [
            {"text": "正在钓鱼", "route": "behavior"},
        ]
    )
    assert _object_mediated_behavior_constraint_indices(plan) == (0,)
    plan = _plan(
        [
            {"text": "正在钓鱼", "route": "behavior"},
            {"text": "正在钓鱼", "route": "behavior"},
        ]
    )
    assert _object_mediated_behavior_constraint_indices(plan) == (0, 1)
    plan = _plan(
        [
            {"text": "正在跑步", "route": "behavior"},
        ]
    )
    assert _object_mediated_behavior_constraint_indices(plan) == ()
    plan = _plan(
        [
            {"text": "拿着鱼竿", "route": "relation"},
        ]
    )
    assert _object_mediated_behavior_constraint_indices(plan) == ()


def test_object_mediated_indices_deterministic_across_calls():
    plan = _plan([{"text": "正在钓鱼", "route": "behavior"}])
    first = _object_mediated_behavior_constraint_indices(plan)
    second = _object_mediated_behavior_constraint_indices(plan)
    assert first == second == (0,)


def test_blend_formula_byte_exact():
    source = np.zeros((4, 4, 3), dtype=np.uint8)
    original = np.array([100, 200, 50], dtype=np.uint8)
    source[0, 0] = original
    source[1, 1] = original
    target = np.zeros((4, 4), dtype=bool)
    target[1, 1] = True  # target-wins：不被弱化
    person = np.zeros((4, 4), dtype=bool)
    person[0, 0] = True
    person[1, 1] = True
    result = blend_non_target_people(source, target, [person])
    expected_non_target = np.array(
        (45 * original.astype(np.uint16) + 55 * 128 + 50) // 100,
        dtype=np.uint8,
    )
    assert (result[0, 0] == expected_non_target).all()
    assert (result[1, 1] == original).all()  # target 优先
    assert (result[2, 2] == 0).all()  # 非 person 区域保持原样


def test_blend_preserves_scene_pixels():
    source = np.full((3, 3, 3), 77, dtype=np.uint8)
    target = np.zeros((3, 3), dtype=bool)
    target[1, 1] = True
    person = np.zeros((3, 3), dtype=bool)
    person[0, 0] = True
    result = blend_non_target_people(source, target, [person])
    assert int(result[2, 2][0]) == 77  # 场景像素不被删除/填充
    assert int(result[1, 1][0]) == 77  # target 原样


def test_behavior_routing_satisfied_no_fallback(tmp_path, monkeypatch):
    calls = []
    detector = DetectorStub(count=2)

    def routed(candidate, constraints, evidence, route):
        calls.append((candidate["id"], len(evidence)))
        return (
            [
                {
                    "constraint": item["text"],
                    "status": "satisfied",
                    "evidence": "明确",
                }
                for item in constraints
            ],
            {"attempts": 1},
        )

    _install(monkeypatch, detector, routed)
    _, result_path = run_pipeline(
        _image(tmp_path),
        "框出正在钓鱼的人",
        plan=_plan([{"text": "正在钓鱼", "route": "behavior"}]),
        verify=True,
        final_response=False,
        output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert len(calls) == 2  # 两个候选各一次 first-pass，无 fallback
    for entry in result["behavior_routing"].values():
        assert entry["fallback_attempted"] is False


def test_behavior_routing_uncertain_single_candidate_immutable(
    tmp_path, monkeypatch
):
    calls = []
    detector = DetectorStub(count=1)

    def routed(candidate, constraints, evidence, route):
        calls.append(len(evidence))
        return (
            [
                {
                    "constraint": item["text"],
                    "status": "uncertain",
                    "evidence": "局部不足",
                }
                for item in constraints
            ],
            {"attempts": 1},
        )

    _install(monkeypatch, detector, routed)
    _, result_path = run_pipeline(
        _image(tmp_path),
        "框出正在钓鱼的人",
        plan=_plan([{"text": "正在钓鱼", "route": "behavior"}]),
        verify=True,
        final_response=False,
        output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert calls == [2]  # uncertain + 单候选 → 不 fallback（合同 §1.1 immutable）
    entry = result["behavior_routing"]["A"]
    assert entry["fallback_attempted"] is False
    assert result["candidates"][0]["verification_checks"][0]["status"] == "uncertain"


def test_behavior_routing_uncertain_multi_disambiguation(tmp_path, monkeypatch):
    calls = []
    detector = DetectorStub(count=2)

    def routed(candidate, constraints, evidence, route):
        calls.append((len(evidence), [item.size for item in evidence]))
        if len(evidence) == 2:
            return (
                [{"constraint": "正在钓鱼", "status": "uncertain", "evidence": "局部不足"}],
                {"attempts": 1},
            )
        return (
            [{"constraint": "正在钓鱼", "status": "satisfied", "evidence": "全图确认"}],
            {"attempts": 1},
        )

    _install(monkeypatch, detector, routed)
    _, result_path = run_pipeline(
        _image(tmp_path),
        "框出正在钓鱼的人",
        plan=_plan([{"text": "正在钓鱼", "route": "behavior"}]),
        verify=True,
        final_response=False,
        output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    # 两个候选：first-pass(2) + fallback(3) × 2
    assert calls[0][0] == 2
    assert calls[1][0] == 3
    assert len(calls) == 4
    # fallback 证据序列 = (isolated, SAME local, full_scene)
    for entry in result["behavior_routing"].values():
        assert entry["fallback_attempted"] is True
        assert entry["fallback_arm"] in {"A", "C"}
        assert entry["write_back_positions"] == [0]
    # disambiguation 后状态为 satisfied（写回生效）
    assert (
        result["candidates"][0]["verification_checks"][0]["status"] == "satisfied"
    )


def test_behavior_fallback_reuses_first_pass_evidence_objects(
    tmp_path, monkeypatch
):
    """合同 §2.2 P1：fallback 不得重建 first-pass local/isolated——断言对象身份一致。"""
    first_pass_evidence_ids = {}
    detector = DetectorStub(count=2)

    def routed(candidate, constraints, evidence, route):
        if len(evidence) == 2:
            first_pass_evidence_ids[candidate["id"]] = (id(evidence[0]), id(evidence[1]))
            return (
                [{"constraint": "正在钓鱼", "status": "uncertain", "evidence": "局部不足"}],
                {"attempts": 1},
            )
        assert id(evidence[0]) == first_pass_evidence_ids[candidate["id"]][0]
        assert id(evidence[1]) == first_pass_evidence_ids[candidate["id"]][1]
        return (
            [{"constraint": "正在钓鱼", "status": "satisfied", "evidence": "全图确认"}],
            {"attempts": 1},
        )

    _install(monkeypatch, detector, routed)
    run_pipeline(
        _image(tmp_path),
        "框出正在钓鱼的人",
        plan=_plan([{"text": "正在钓鱼", "route": "behavior"}]),
        verify=True,
        final_response=False,
        output_dir=tmp_path / "out",
    )


def test_behavior_escalation_on_not_satisfied_armed(tmp_path, monkeypatch):
    """OBJECT_MEDIATED（正在钓鱼，单约束）+ not_satisfied → target-anchored full-scene escalation。"""
    calls = []
    detector = DetectorStub(count=2)

    def routed(candidate, constraints, evidence, route):
        calls.append(len(evidence))
        if len(evidence) == 2:
            return (
                [{"constraint": "正在钓鱼", "status": "not_satisfied", "evidence": "未见"}],
                {"attempts": 1},
            )
        return (
            [{"constraint": "正在钓鱼", "status": "satisfied", "evidence": "全图确认"}],
            {"attempts": 1},
        )

    _install(monkeypatch, detector, routed)
    _, result_path = run_pipeline(
        _image(tmp_path),
        "框出正在钓鱼的人",
        plan=_plan([{"text": "正在钓鱼", "route": "behavior"}]),
        verify=True,
        final_response=False,
        output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    for entry in result["behavior_routing"].values():
        assert entry["fallback_attempted"] is True
        assert entry["fallback_arm"] == "C"  # escalation 一律 target-anchored 全图
        assert entry["write_back_positions"] == [0]


def test_behavior_no_escalation_for_unarmed_not_satisfied(tmp_path, monkeypatch):
    """非 OBJECT_MEDIATED 约束 not_satisfied → 不触发 escalation（不可覆写）。"""
    calls = []
    detector = DetectorStub(count=2)

    def routed(candidate, constraints, evidence, route):
        calls.append(len(evidence))
        return (
            [{"constraint": "正在跑步", "status": "not_satisfied", "evidence": "未见"}],
            {"attempts": 1},
        )

    _install(monkeypatch, detector, routed)
    _, result_path = run_pipeline(
        _image(tmp_path),
        "框出正在跑步的人",
        plan=_plan([{"text": "正在跑步", "route": "behavior"}]),
        verify=True,
        final_response=False,
        output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert calls == [2, 2]  # 无 fallback
    for entry in result["behavior_routing"].values():
        assert entry["fallback_attempted"] is False
