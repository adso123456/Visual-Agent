import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visual_agent.pipeline import _build_semantic_groups
from visual_agent.relations import validate_relation_bindings


SUBJECTS = [
    {"id": "A", "bbox": [0, 0, 10, 20]},
    {"id": "B", "bbox": [20, 0, 30, 20]},
]
RELATED = [
    {"id": "R1", "bbox": [2, 0, 12, 8]},
    {"id": "R2", "bbox": [22, 0, 32, 8]},
]
PLAN = {
    "target_object": "person",
    "label": "持有物体的人",
    "related_objects": [{"object": "umbrella", "relation": "held_by_target"}],
}


def binding(subject: str, related: str, status: str) -> dict:
    return {
        "subject_id": subject,
        "related_id": related,
        "relation": "held_by_target",
        "status": status,
        "evidence": "测试证据",
    }


def expect_validation_failure(bindings: list[dict]) -> None:
    try:
        validate_relation_bindings({"bindings": bindings}, SUBJECTS, RELATED, "held_by_target")
    except RuntimeError:
        return
    raise AssertionError("预期 relation matrix 校验失败")


def main() -> None:
    complete = [
        binding("A", "R1", "satisfied"),
        binding("A", "R2", "not_satisfied"),
        binding("B", "R1", "not_satisfied"),
        binding("B", "R2", "satisfied"),
    ]
    assert len(validate_relation_bindings(
        {"bindings": complete}, SUBJECTS, RELATED, "held_by_target"
    )) == 4
    expect_validation_failure(complete[:-1])
    expect_validation_failure([*complete[:-1], complete[0]])
    expect_validation_failure([{**complete[0], "subject_id": "C"}, *complete[1:]])
    expect_validation_failure([{**complete[0], "related_id": "R3"}, *complete[1:]])
    expect_validation_failure([{**complete[0], "relation": "near"}, *complete[1:]])
    expect_validation_failure([{**complete[0], "status": "yes"}, *complete[1:]])
    expect_validation_failure([{**complete[0], "evidence": ""}, *complete[1:]])

    subject_conflict = [
        binding("A", "R1", "satisfied"),
        binding("A", "R2", "satisfied"),
        binding("B", "R1", "not_satisfied"),
        binding("B", "R2", "not_satisfied"),
    ]
    assert _build_semantic_groups(SUBJECTS, RELATED, subject_conflict, PLAN)[0][
        "completion_reason"
    ] == "binding_conflict"

    related_conflict = [
        binding("A", "R1", "satisfied"),
        binding("A", "R2", "not_satisfied"),
        binding("B", "R1", "satisfied"),
        binding("B", "R2", "not_satisfied"),
    ]
    assert all(
        group["completion_reason"] == "binding_conflict"
        for group in _build_semantic_groups(SUBJECTS, RELATED, related_conflict, PLAN)
    )
    assert _build_semantic_groups([], [], [], PLAN) == []
    assert _build_semantic_groups(SUBJECTS[:1], [], [], PLAN)[0][
        "completion_reason"
    ] == "related_object_not_detected"
    all_false = [binding("A", "R1", "not_satisfied"), binding("A", "R2", "not_satisfied")]
    assert _build_semantic_groups(SUBJECTS[:1], RELATED, all_false, PLAN)[0][
        "completion_reason"
    ] == "binding_not_satisfied"
    uncertain = [binding("A", "R1", "uncertain"), binding("A", "R2", "not_satisfied")]
    assert _build_semantic_groups(SUBJECTS[:1], RELATED, uncertain, PLAN)[0][
        "completion_reason"
    ] == "binding_uncertain"
    print("Phase 7 relation contract: PASS")


if __name__ == "__main__":
    main()
