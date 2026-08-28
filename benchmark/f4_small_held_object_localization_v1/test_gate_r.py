import json
from pathlib import Path

import pytest

from benchmark.f4_small_held_object_localization_v1.run_gate_r import (
    FrozenInputs,
    GateRFailure,
    Slot,
    _historical_candidates,
    build_candidate_universe,
    frozen_slots,
    run_slots,
    summarize,
    validate_authorization,
    verify_slot,
)
from visual_agent.vlm_client import VlmConfig


HISTORICAL = (
    {"id": "R1", "object": "fish", "text_label": "fish", "bbox": [0, 0, 10, 10], "dino_confidence": 0.5},
)
REFERENCE = {"bbox": [820, 690, 945, 780], "center": [885, 735]}
GATE_L_ARM = {
    "deduplicated_detections": [
        {"bbox": [814.11, 688.52, 963.71, 799.0], "confidence": 0.5126, "text_label": "fish"},
        {"bbox": [600, 2100, 1000, 2400], "confidence": 0.4, "text_label": "fish"},
    ]
}


def inputs(tmp_path: Path) -> FrozenInputs:
    candidates, target_ids = build_candidate_universe(HISTORICAL, GATE_L_ARM, REFERENCE)
    return FrozenInputs(
        image_path=tmp_path / "original.jpeg",
        subject={"id": "A", "bbox": [0, 0, 100, 100]},
        candidates_by_arm={"B": candidates, "C": candidates},
        target_ids_by_arm={"B": target_ids, "C": target_ids},
        slots=frozen_slots(),
        evidence_head="reviewed",
        authorization_sha256="authorization",
        runner_review_sha="reviewed-runner",
    )


def test_candidate_universe_keeps_historical_and_marks_only_gate_l_target():
    candidates, target_ids = build_candidate_universe(HISTORICAL, GATE_L_ARM, REFERENCE)
    assert [row["id"] for row in candidates] == ["R1", "R2", "R3"]
    assert target_ids == {"R2"}
    assert candidates[0] == HISTORICAL[0]


def test_historical_universe_keeps_only_initial_full_scene_r1_to_r4(tmp_path):
    candidates = [
        {"id": f"R{index}", "bbox": [index, index, index + 1, index + 1]}
        for index in range(1, 8)
    ]
    path = tmp_path / "gate2.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(
                {
                    "case_id": "F4::fishing_017.jpeg",
                    "relation_candidates": candidates,
                }
            )
            for _ in range(5)
        )
        + "\n",
        encoding="utf-8",
    )
    assert [row["id"] for row in _historical_candidates(path)] == [
        "R1", "R2", "R3", "R4"
    ]


def test_schedule_is_exactly_five_independent_calls_per_successful_arm():
    slots = frozen_slots()
    assert len(slots) == 10
    assert [(slot.arm, slot.repetition) for slot in slots] == [
        (arm, repetition) for repetition in range(1, 6) for arm in ("B", "C")
    ]


def test_execution_authorization_is_separate_and_strict():
    payload = {
        "schema_version": "GENERAL_RGB_F4_GATE_R_EXECUTION_AUTHORIZATION_V1",
        "status": "GATE_R_RELATION_VLM_EXECUTION_AUTHORIZED",
        "gate_l_evidence_head": "3308fee09ac2d3fa827f81854c1d556a0b4c87f6",
        "runner_review_sha": "a" * 40,
        "arms": ["B", "C"],
        "calls_per_arm": 5,
        "scheduled_calls": 10,
        "failed_execution_replacement": False,
        "production_modification_authorized": False,
    }
    assert validate_authorization(payload) == "a" * 40
    payload["scheduled_calls"] = 9
    with pytest.raises(GateRFailure, match="scheduled_calls"):
        validate_authorization(payload)


def test_verify_slot_reuses_production_signature_and_classifies_bindings(tmp_path):
    frozen = inputs(tmp_path)
    captured = {}

    def fake_verifier(image_path, subjects, candidates, related_object, relation):
        captured.update(
            image_path=image_path,
            subjects=subjects,
            candidates=candidates,
            related_object=related_object,
            relation=relation,
        )
        return (
            [
                {"subject_id": "A", "related_id": row["id"], "relation": relation,
                 "status": "satisfied" if row["id"] == "R2" else "not_satisfied", "evidence": "e"}
                for row in candidates
            ],
            {"attempts": 1, "retry_count": 0, "recovered": False, "first_error_code": None},
        )

    class Client:
        class Chat:
            class Completions:
                pass
            completions = Completions()
        chat = Chat()

    result = verify_slot(
        frozen,
        Slot("slot", "B", 1),
        config_loader=lambda: VlmConfig(
            "qwen3.8:27b-mtp-q4_K_M", "http://192.168.250.9:11434/v1", "ollama", 120.0
        ),
        client_factory=lambda config: Client(),
        verifier=fake_verifier,
    )
    assert captured["subjects"] == [frozen.subject]
    assert captured["candidates"] == list(frozen.candidates_by_arm["B"])
    assert captured["related_object"] == "fish"
    assert captured["relation"] == "held_by_target"
    assert result["target_satisfied"] is True
    assert result["non_target_satisfied_ids"] == []
    assert result["subject_retained"] is True


def test_subject_retained_is_independent_from_correct_target_binding(tmp_path):
    frozen = inputs(tmp_path)

    def wrong_object_satisfied(_image_path, _subjects, candidates, _object, relation):
        return (
            [
                {"subject_id": "A", "related_id": row["id"], "relation": relation,
                 "status": "satisfied" if row["id"] == "R1" else "not_satisfied", "evidence": "e"}
                for row in candidates
            ],
            {"attempts": 1, "retry_count": 0, "recovered": False, "first_error_code": None},
        )

    class Client:
        chat = type("Chat", (), {"completions": object()})()

    result = verify_slot(
        frozen,
        Slot("slot", "B", 1),
        config_loader=lambda: VlmConfig(
            "qwen3.8:27b-mtp-q4_K_M", "http://192.168.250.9:11434/v1", "ollama", 120.0
        ),
        client_factory=lambda config: Client(),
        verifier=wrong_object_satisfied,
    )
    assert result["target_satisfied"] is False
    assert result["subject_retained"] is True
    assert result["non_target_satisfied_ids"] == ["R1"]


def test_wrong_vlm_config_is_rejected_before_client_creation(tmp_path):
    called = False

    def client_factory(config):
        nonlocal called
        called = True

    with pytest.raises(GateRFailure, match="VlmConfig"):
        verify_slot(
            inputs(tmp_path),
            Slot("slot", "B", 1),
            config_loader=lambda: VlmConfig("cloud", "https://example.test/v1", "secret", 120.0),
            client_factory=client_factory,
        )
    assert called is False


def test_terminal_failure_is_retained_and_never_replaced(tmp_path):
    frozen = inputs(tmp_path)
    output = tmp_path / "results.jsonl"
    calls = 0

    def failing(_inputs, _slot):
        nonlocal calls
        calls += 1
        raise GateRFailure("validator", "contract", "bad")

    run_slots(frozen, output, failing)
    assert calls == 10
    first_bytes = output.read_bytes()
    run_slots(frozen, output, failing)
    assert calls == 10
    assert output.read_bytes() == first_bytes
    assert all(
        row["terminal_status"] == "failure"
        for row in map(json.loads, output.read_text(encoding="utf-8").splitlines())
    )


def test_summary_applies_gate_per_arm():
    records = []
    for slot in frozen_slots():
        records.append(
            {
                "slot_id": slot.slot_id,
                "arm": slot.arm,
                "terminal_status": "success",
                "result": {
                    "target_satisfied": slot.repetition <= 4,
                    "subject_retained": slot.repetition <= 4,
                    "non_target_satisfied_ids": [],
                },
            }
        )
    summary = summarize(records)
    assert summary["confirmed_arms"] == ["B", "C"]
    assert summary["mechanism_confirmed"] is True
    assert summary["all_arms_pass"] is True
    records[0]["result"]["non_target_satisfied_ids"] = ["R1"]
    summary = summarize(records)
    assert summary["arms"]["B"]["gate_pass"] is False
    assert summary["confirmed_arms"] == ["C"]
    assert summary["mechanism_confirmed"] is True
    assert summary["all_arms_pass"] is False
