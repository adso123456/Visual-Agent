import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from benchmark.joint_targeted_confirmation_v1 import runner
from benchmark.joint_targeted_confirmation_v1.runner import (
    BehaviorSlot,
    JointFailure,
    PreflightReceipt,
    RelationSlot,
)
from visual_agent.vlm_client import VlmConfig


def _authorization(**overrides):
    payload = {
        "schema_version": "GENERAL_RGB_BEHAVIOR_RELATION_JOINT_EXECUTION_AUTHORIZATION_V1",
        "status": "MODEL_EXECUTION_AUTHORIZED",
        "frozen_evidence_head": runner.FROZEN_EVIDENCE_HEAD,
        "execution_base": runner.EXECUTION_BASE,
        "runner_review_sha": "a" * 40,
        "model": runner.FROZEN_MODEL,
        "base_url": runner.FROZEN_BASE_URL,
        "timeout_seconds": 120,
        "concurrency": 1,
        "failed_execution_replacement": False,
        "production_modification_authorized": False,
    }
    payload.update(overrides)
    return payload


def _write_image(path: Path, color):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color).save(path)
    return {
        "path": str(path),
        "sha256": runner.sha256(path),
        "bytes": path.stat().st_size,
    }


def _behavior_manifest(tmp_path: Path):
    artifacts = []
    colors = {"A": (10, 20, 30), "B": (40, 50, 60), "C": (70, 80, 90)}
    for arm in ("A", "B", "C"):
        for kind in ("isolated", "local"):
            row = _write_image(tmp_path / f"{arm}_{kind}.png", colors[arm])
            row.update({"candidate_id": "A", "arm": arm, "evidence_type": kind})
            artifacts.append(row)
        if arm in {"A", "C"}:
            row = _write_image(tmp_path / f"{arm}_full_scene.png", colors[arm])
            row.update({"candidate_id": "A", "arm": arm, "evidence_type": "full_scene"})
            artifacts.append(row)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"artifacts": artifacts}), encoding="utf-8")
    return path


def _behavior_slot(*, risk=False, count=2, expected="satisfied"):
    return BehaviorSlot(
        "slot", "challenge_004", 1,
        {"id": "A", "bbox": [1, 1, 5, 7], "expected": expected},
        count, risk, "正在钓鱼",
    )


def test_authorization_locks_frozen_head_base_runtime_and_failure_policy():
    assert runner.validate_authorization(_authorization()) == "a" * 40
    for key, bad in (
        ("frozen_evidence_head", "wrong"),
        ("execution_base", "wrong"),
        ("model", "wrong"),
        ("base_url", "http://cloud.example/v1"),
        ("timeout_seconds", 60),
        ("concurrency", 2),
        ("failed_execution_replacement", True),
        ("production_modification_authorized", True),
    ):
        with pytest.raises(JointFailure) as error:
            runner.validate_authorization(_authorization(**{key: bad}))
        assert (error.value.stage, error.value.category) == (
            "authorization", "authorization_contract"
        )


def test_preflight_missing_authorization_stops_before_any_git_or_runtime(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(runner, "_git", lambda *_args: calls.append("git"))
    with pytest.raises(JointFailure) as error:
        runner.verify_preflight(tmp_path / "repo", tmp_path / "evidence", tmp_path / "missing.json")
    assert error.value.category == "authorization_missing"
    assert calls == []


def test_frozen_manifest_is_verified_from_reviewed_git_blob_not_mutable_head(
    monkeypatch, tmp_path
):
    frozen = b'{"status":"CONTRACT_FROZEN"}\n'
    calls = []

    def git_run(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=frozen)

    monkeypatch.setattr(runner.subprocess, "run", git_run)
    runner._verify_frozen_git_blob(
        tmp_path, "frozen-head", "path/manifest.json",
        __import__("hashlib").sha256(frozen).hexdigest(),
    )
    assert calls == [["git", "show", "frozen-head:path/manifest.json"]]


def test_preflight_requires_head_to_equal_authorized_review_commit(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner,
        "_require_git",
        lambda *_args: "b" * 40,
    )
    runner._require_exact_reviewed_head(tmp_path, "b" * 40)
    with pytest.raises(JointFailure) as error:
        runner._require_exact_reviewed_head(tmp_path, "c" * 40)
    assert error.value.category == "runner_review_head"


def test_frozen_vlm_config_rejects_wrong_endpoint_before_client_creation():
    bad = VlmConfig(runner.FROZEN_MODEL, "https://dashscope.example/v1", "secret", 120)
    with pytest.raises(JointFailure) as error:
        runner.frozen_vlm_config(lambda: bad)
    assert error.value.category == "frozen_vlm_config"


def test_identity_contamination_requires_count_coverage_and_center():
    case = {
        "candidates": [
            {"id": "A", "bbox": [20, 20, 40, 60]},
            {"id": "B", "bbox": [34, 25, 45, 55]},
        ]
    }
    assert runner.identity_contamination_risk(case, case["candidates"][0], (100, 100))
    assert not runner.identity_contamination_risk(
        {"candidates": [case["candidates"][0]]}, case["candidates"][0], (100, 100)
    )


@pytest.mark.parametrize(
    ("risk", "count", "first", "fallback", "expected_route"),
    [
        (True, 2, "uncertain", "not_satisfied", "MULTI_CANDIDATE_FULL_SCENE_DISAMBIGUATION"),
        (False, 1, "uncertain", None, "SINGLE_CANDIDATE_UNCERTAIN_IMMUTABLE"),
        (False, 2, "satisfied", None, "BINARY_IMMUTABLE"),
        (False, 1, "not_satisfied", "satisfied", "OBJECT_MEDIATED_NOT_SATISFIED_ESCALATION"),
    ],
)
def test_behavior_routing_is_state_and_geometry_deterministic(
    tmp_path, risk, count, first, fallback, expected_route
):
    manifest = _behavior_manifest(tmp_path)
    statuses = [first] + ([fallback] if fallback else [])
    calls = []

    def verifier(_slot, images):
        calls.append(len(images))
        return {"status": statuses.pop(0), "evidence": "stub"}

    result = runner.run_behavior_slot(
        _behavior_slot(risk=risk, count=count, expected="satisfied"),
        manifest,
        verifier,
    )
    assert result["routing"] == expected_route
    assert result["fallback_attempted"] is bool(fallback)
    assert calls == ([2, 3] if fallback else [2])
    if risk:
        assert result["first_pass_arm"] == "B"


def test_behavior_adjudication_uses_frozen_baseline_not_absolute_errors():
    existing_fp = BehaviorSlot(
        "slot", "F1::fishing_001.jpeg", 1,
        {"id": "A", "expected": "not_satisfied"}, 1, False, "正在钓鱼",
    )
    unchanged_uncertain = BehaviorSlot(
        "slot", "F1::fishing_014.jpeg", 1,
        {"id": "B", "expected": "not_satisfied"}, 3, False, "正在钓鱼",
    )
    assert runner.behavior_adjudication(existing_fp, "satisfied", False) == {
        "baseline_status": "satisfied",
        "expected_statuses": ["not_satisfied"],
        "candidate_correct": False,
        "new_false_assignment": False,
        "fallback_harm": False,
    }
    result = runner.behavior_adjudication(unchanged_uncertain, "uncertain", True)
    assert result["new_false_assignment"] is False
    assert result["fallback_harm"] is False


def test_behavior_adjudication_detects_new_assignment_and_fallback_regression():
    slot = BehaviorSlot(
        "slot", "challenge_003", 1,
        {"id": "A", "expected": "uncertain"}, 1, False, "正在钓鱼",
    )
    result = runner.behavior_adjudication(slot, "satisfied", True)
    assert result["new_false_assignment"] is True
    assert result["fallback_harm"] is True


def test_windows_safe_artifact_slug_removes_all_windows_invalid_characters():
    slug = runner.windows_safe_artifact_slug("RELATION|F4::fishing_017.jpeg|r1")
    assert slug == "RELATION_F4__fishing_017.jpeg_r1"
    assert not any(char in slug for char in '<>:"/\\|?*')


def test_admission_rejects_all_old_candidates_then_stably_deduplicates_new():
    old = [{"id": "R1", "bbox": [0, 0, 10, 10]}]
    detected = [
        {"bbox": [0, 0, 10, 10], "dino_confidence": 0.99},
        {"bbox": [20, 20, 30, 30], "dino_confidence": 0.8},
        {"bbox": [20.2, 20.2, 30.2, 30.2], "dino_confidence": 0.7},
        {"bbox": [40, 40, 50, 50], "dino_confidence": 0.6},
    ]
    admitted = runner.stable_admit(detected, old)
    assert [row["id"] for row in admitted] == ["R2", "R3"]
    assert [row["bbox"] for row in admitted] == [[20, 20, 30, 30], [40, 40, 50, 50]]


def _pipeline_result(tmp_path, *, complete):
    image = tmp_path / "result.jpg"
    image.write_bytes(b"image")
    result = {
        "targets": [{"id": "A"}] if complete else [],
        "candidates": [
            {"id": "A", "text_label": "person", "bbox": [10, 10, 40, 70], "dino_confidence": 0.9}
        ],
        "relation_candidates": [
            {
                "id": "R1", "object": "fishing rod", "text_label": "rod",
                "bbox": [60, 10, 80, 50], "dino_confidence": 0.8,
            }
        ],
        "relation_bindings": ([{
            "subject_id": "A", "related_id": "R1",
            "relation": "held_by_target", "status": "satisfied",
            "evidence": "existing binding",
        }] if complete else []),
        "semantic_groups": [{"id": "A", "composite_complete": complete}],
    }
    data = tmp_path / "result.json"
    data.write_text(json.dumps(result), encoding="utf-8")
    return image, data


def _relation_slot(tmp_path, case_id="F2::fishing_024.jpeg"):
    image = tmp_path / "input.jpg"
    image.write_bytes(b"input")
    related = "fish" if case_id.startswith("F4") else "fishing rod"
    return RelationSlot(
        f"RELATION|{case_id}|r1",
        {
            "case_id": case_id,
            "prompt": "prompt",
            "related_object": related,
            "resolved_image_path": str(image),
        },
        1,
    )


def _good_config():
    return VlmConfig(
        runner.FROZEN_MODEL, runner.FROZEN_BASE_URL, "ollama", runner.FROZEN_TIMEOUT
    )


def test_relation_existing_positive_blocks_hand_detector_and_fallback_client(tmp_path):
    calls = []
    slot = _relation_slot(tmp_path)
    result = runner.run_relation_slot(
        slot,
        tmp_path / "out",
        {"bbox": [1, 1, 2, 2], "center": [1.5, 1.5]},
        pipeline_runner=lambda *_args, **_kwargs: _pipeline_result(tmp_path, complete=True),
        detector_factory=lambda: calls.append("detector"),
        config_loader=_good_config,
        client_factory=lambda _config: calls.append("client"),
    )
    assert result["fallback_attempts"] == 0
    assert result["hand_detector_calls"] == 0
    assert result["hand_relation_calls"] == 0
    assert result["final_retained_subject_ids"] == ["A"]
    assert calls == []


def test_relation_slot_passes_windows_safe_artifact_directory(tmp_path):
    output_dirs = []

    def pipeline_runner(*_args, **kwargs):
        output_dirs.append(kwargs["output_dir"])
        return _pipeline_result(tmp_path, complete=True)

    runner.run_relation_slot(
        _relation_slot(tmp_path),
        tmp_path / "out",
        {"bbox": [1, 1, 2, 2], "center": [1.5, 1.5]},
        pipeline_runner=pipeline_runner,
        config_loader=_good_config,
    )
    assert output_dirs[0].name == "RELATION_F2__fishing_024.jpeg_r1"
    assert not any(char in output_dirs[0].name for char in '<>:"/\\|?*')


def test_relation_incomplete_stage_runs_one_hand_fallback_and_existing_verifier(
    tmp_path, monkeypatch
):
    slot = _relation_slot(tmp_path, "F4::fishing_017.jpeg")
    admitted = [
        {"id": "R2", "object": "fish", "text_label": "fish", "bbox": [10, 10, 20, 20], "dino_confidence": 0.8}
    ]
    monkeypatch.setattr(
        runner,
        "hand_conditioned_candidates",
        lambda *_args: (admitted, {"calls": [{}, {}], "admitted_count": 1}),
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_kwargs: None))
    )
    verifier_calls = []

    def relation_verifier(_image, subjects, candidates, obj, relation):
        verifier_calls.append((subjects, candidates, obj, relation))
        return ([{"subject_id": "A", "related_id": "R2", "status": "satisfied", "relation": relation, "evidence": "stub"}], {"attempts": 1})

    result = runner.run_relation_slot(
        slot,
        tmp_path / "out",
        {"bbox": [9, 9, 21, 21], "center": [15, 15]},
        pipeline_runner=lambda *_args, **_kwargs: _pipeline_result(tmp_path, complete=False),
        detector_factory=lambda: object(),
        relation_verifier=relation_verifier,
        config_loader=_good_config,
        client_factory=lambda _config: fake_client,
    )
    assert result["fallback_attempts"] == 1
    assert result["hand_detector_calls"] == 2
    assert result["hand_relation_calls"] == 1
    assert result["target_satisfied"] is True
    assert result["final_retained_subject_ids"] == ["A"]
    assert len(verifier_calls) == 1


def test_relation_new_candidates_use_global_ids_full_subject_matrix_and_production_resolvers(
    tmp_path, monkeypatch
):
    slot = _relation_slot(tmp_path, "F4::fishing_017.jpeg")
    result_image = tmp_path / "result_multi.jpg"
    result_image.write_bytes(b"image")
    result_json = tmp_path / "result_multi.json"
    result_json.write_text(
        json.dumps(
            {
                "targets": [],
                "candidates": [
                    {"id": "A", "text_label": "person", "bbox": [10, 10, 40, 70], "dino_confidence": 0.9},
                    {"id": "B", "text_label": "person", "bbox": [35, 10, 65, 70], "dino_confidence": 0.8},
                ],
                "relation_candidates": [
                    {"id": "R1", "object": "fish", "text_label": "fish", "bbox": [70, 10, 90, 40], "dino_confidence": 0.6}
                ],
                "relation_bindings": [],
                "semantic_groups": [
                    {"id": "A", "composite_complete": False},
                    {"id": "B", "composite_complete": False},
                ],
            }
        ),
        encoding="utf-8",
    )
    localization_calls = []

    def hand_candidates(_image, subject, _object, old_candidates, _detector):
        localization_calls.append((subject["id"], [row["id"] for row in old_candidates]))
        if subject["id"] == "A":
            return (
                [{"id": "R2", "object": "fish", "text_label": "fish", "bbox": [10, 10, 20, 20], "dino_confidence": 0.9}],
                {"calls": [{}, {}]},
            )
        return ([], {"calls": [{}]})

    monkeypatch.setattr(runner, "hand_conditioned_candidates", hand_candidates)
    verifier_subjects = []

    def relation_verifier(_image, subjects, _candidates, _object, relation):
        subject_id = subjects[0]["id"]
        verifier_subjects.append(subject_id)
        return (
            [{
                "subject_id": subject_id,
                "related_id": "R2",
                "relation": relation,
                "status": "satisfied",
                "evidence": f"raw {subject_id}",
            }],
            {"attempts": 1},
        )

    focused_calls = []

    def focused(_image, subjects, candidates, _object, relation):
        focused_calls.append(([row["id"] for row in subjects], [row["id"] for row in candidates]))
        return (
            [
                {"subject_id": "A", "related_id": "R2", "relation": relation, "status": "satisfied", "evidence": "A owns"},
                {"subject_id": "B", "related_id": "R2", "relation": relation, "status": "not_satisfied", "evidence": "B does not own"},
            ],
            {"attempts": 1},
        )

    monkeypatch.setattr(runner.pipeline, "verify_focused_ownership", focused)
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_kwargs: None))
    )
    result = runner.run_relation_slot(
        slot,
        tmp_path / "out",
        {"bbox": [9, 9, 21, 21], "center": [15, 15]},
        pipeline_runner=lambda *_args, **_kwargs: (result_image, result_json),
        detector_factory=lambda: object(),
        relation_verifier=relation_verifier,
        config_loader=_good_config,
        client_factory=lambda _config: fake_client,
    )
    assert localization_calls == [("A", ["R1"]), ("B", ["R1", "R2"])]
    assert verifier_subjects == ["A", "B"]
    assert focused_calls == [(["A", "B"], ["R2"])]
    assert result["hand_relation_calls"] == 2
    assert result["focused_ownership_calls"] == 1
    assert result["final_retained_subject_ids"] == ["A"]
    assert result["relation_outcomes"]["B"]["status"] == "not_satisfied"


def _joint_receipt(tmp_path):
    behavior_slots = []
    for case_id, candidates, repetitions in (
        ("challenge_001", ("A", "B"), 5),
        ("challenge_003", ("A",), 5),
        ("challenge_004", ("A", "B"), 5),
        ("F1::fishing_001.jpeg", ("A",), 1),
        ("F1::fishing_005.jpeg", ("A",), 1),
        ("F1::fishing_010.jpeg", ("A", "B", "C"), 1),
        ("F1::fishing_014.jpeg", ("A", "B", "C"), 1),
        ("F1::fishing_004.jpeg", ("A",), 1),
        ("F1::fishing_018.jpeg", ("A",), 1),
    ):
        for repetition in range(1, repetitions + 1):
            for candidate_id in candidates:
                expected = "satisfied" if candidate_id == "B" and case_id == "challenge_001" or candidate_id == "A" and case_id in {"challenge_004", "F1::fishing_004.jpeg"} else "uncertain" if case_id == "challenge_003" else "not_satisfied"
                behavior_slots.append(
                    BehaviorSlot(
                        f"B|{case_id}|{repetition}|{candidate_id}", case_id,
                        repetition, {"id": candidate_id, "expected": expected},
                        len(candidates), False, "正在钓鱼"
                    )
                )
    relation_slots = []
    for case_id, repetitions in (
        ("F4::fishing_017.jpeg", 5), ("F2::fishing_005.jpeg", 5),
        ("F2::fishing_024.jpeg", 1), ("core_003", 1), ("core_014", 1),
    ):
        for repetition in range(1, repetitions + 1):
            relation_slots.append(
                RelationSlot(
                    f"R|{case_id}|{repetition}",
                    {"case_id": case_id, "image_sha256": case_id, "role": "test"},
                    repetition,
                )
            )
    manifests = {slot.case_id: tmp_path / "unused" for slot in behavior_slots}
    return PreflightReceipt("head", "review", "auth", tuple(behavior_slots), tuple(relation_slots), manifests, {})


def test_joint_runner_is_sequential_retains_terminal_records_and_writes_gate_summary(
    tmp_path, monkeypatch
):
    receipt = _joint_receipt(tmp_path)
    monkeypatch.setattr(
        runner,
        "FROZEN_BEHAVIOR_SLOT_SEQUENCE_SHA256",
        runner._behavior_sequence_sha(receipt.behavior_slots),
    )
    monkeypatch.setattr(
        runner,
        "FROZEN_RELATION_SLOT_SEQUENCE_SHA256",
        runner._relation_sequence_sha(receipt.relation_slots),
    )
    calls = []

    def behavior_executor(slot, _manifest):
        calls.append(slot.slot_id)
        status = slot.candidate["expected"]
        return {
            "final_status": status,
            "candidate_correct": True,
            "new_false_assignment": False,
            "fallback_harm": False,
        }

    def relation_executor(slot, _root, _reference):
        calls.append(slot.slot_id)
        case_id = slot.case["case_id"]
        if case_id == "F4::fishing_017.jpeg":
            return {"fallback_attempts": 1, "target_satisfied": True, "final_retained_subject_ids": ["A"], "hand_satisfied_related_ids": ["R8"], "target_candidate_ids": ["R8"], "hand_detector_calls": 2, "hand_relation_calls": 1}
        if case_id == "F2::fishing_005.jpeg":
            return {"fallback_attempts": 1, "target_satisfied": False, "final_retained_subject_ids": [], "hand_satisfied_related_ids": [], "target_candidate_ids": [], "hand_detector_calls": 2, "hand_relation_calls": 1}
        if case_id in {"F2::fishing_024.jpeg", "core_003"}:
            return {"fallback_attempts": 0, "target_satisfied": False, "final_retained_subject_ids": ["A"], "hand_satisfied_related_ids": [], "target_candidate_ids": [], "hand_detector_calls": 0, "hand_relation_calls": 0}
        return {"fallback_attempts": 0, "target_satisfied": False, "final_retained_subject_ids": [], "hand_satisfied_related_ids": [], "target_candidate_ids": [], "hand_detector_calls": 0, "hand_relation_calls": 0}

    output = tmp_path / "output"
    runner.run_joint(receipt, output, behavior_executor=behavior_executor, relation_executor=relation_executor)
    first_calls = list(calls)
    runner.run_joint(receipt, output, behavior_executor=behavior_executor, relation_executor=relation_executor)
    assert calls == first_calls
    assert len(first_calls) == 48
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["terminal_failure"] == 0
    assert summary["behavior"]["F1_candidate_regression"] == 0
    assert summary["behavior"]["F1_task_regression"] == 0
    assert summary["relation"]["F2_024_final_positive_retained"] is True
    assert summary["relation"]["core_003_final_positive_retained"] is True
    assert summary["joint_policy_candidate_confirmed"] is True


def test_summary_does_not_treat_missing_existing_positive_as_retained(tmp_path):
    receipt = _joint_receipt(tmp_path)
    behavior = []
    for slot in receipt.behavior_slots:
        behavior.append({
            "slot_id": slot.slot_id,
            "terminal_status": "success",
            "result": {
                "kind": "behavior",
                "case_id": slot.case_id,
                "candidate_id": slot.candidate["id"],
                "final_status": slot.candidate["expected"],
                "candidate_correct": True,
                "new_false_assignment": False,
                "fallback_harm": False,
            },
        })
    relation = []
    for slot in receipt.relation_slots:
        if slot.case["case_id"] == "F2::fishing_024.jpeg":
            relation.append({
                "slot_id": slot.slot_id,
                "terminal_status": "failure",
                "failure_stage": "unexpected",
                "failure_category": "OSError",
            })
            continue
        retained = ["A"] if slot.case["case_id"] == "core_003" else []
        relation.append({
            "slot_id": slot.slot_id,
            "terminal_status": "success",
            "result": {
                "kind": "relation",
                "case_id": slot.case["case_id"],
                "fallback_attempts": 0,
                "target_satisfied": False,
                "final_retained_subject_ids": retained,
                "hand_satisfied_related_ids": [],
                "target_candidate_ids": [],
                "hand_detector_calls": 0,
                "hand_relation_calls": 0,
            },
        })
    summary = runner.summarize(behavior + relation)
    assert summary["relation"]["F2_024_final_positive_retained"] is False
    assert summary["relation"]["core_003_final_positive_retained"] is True


def test_joint_runner_rejects_tampered_actual_slot_sequence_before_execution(
    tmp_path, monkeypatch
):
    receipt = _joint_receipt(tmp_path)
    monkeypatch.setattr(
        runner,
        "FROZEN_BEHAVIOR_SLOT_SEQUENCE_SHA256",
        runner._behavior_sequence_sha(receipt.behavior_slots),
    )
    monkeypatch.setattr(
        runner,
        "FROZEN_RELATION_SLOT_SEQUENCE_SHA256",
        runner._relation_sequence_sha(receipt.relation_slots),
    )
    tampered = PreflightReceipt(
        receipt.evidence_head,
        receipt.runner_review_sha,
        receipt.authorization_sha256,
        tuple(reversed(receipt.behavior_slots)),
        receipt.relation_slots,
        receipt.behavior_manifests,
        receipt.relation_reference,
    )
    calls = []
    with pytest.raises(JointFailure) as error:
        runner.run_joint(
            tampered,
            tmp_path / "output",
            behavior_executor=lambda *_args: calls.append("behavior"),
            relation_executor=lambda *_args: calls.append("relation"),
        )
    assert error.value.category == "behavior_slot_sequence"
    assert calls == []


def test_relation_plans_are_frozen_without_planner_calls():
    assert runner.relation_plan({"case_id": "F4::fishing_017.jpeg", "related_object": "fish"})["action"] == {"type": "highlight"}
    assert runner.relation_plan({"case_id": "core_003", "related_object": "umbrella"})["constraints"] == [{"text": "手持雨伞", "route": "relation"}]
