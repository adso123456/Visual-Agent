import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from benchmark.r3_candidate_identity_v1.evidence_builder import (
    BEHAVIOR_CONTOUR_WIDTH,
    ArmEvidence,
    blend_non_target_people,
    build_arm_evidence,
    build_target_anchored_evidence,
    materialize_case_evidence,
    save_png,
    write_manifest,
)
from benchmark.r3_candidate_identity_v1.mask_cache import MaskCache
from benchmark.r3_candidate_identity_v1.runner import (
    ResultRecorder,
    Slot,
    classify_fallback,
    expand_schedule,
    run_slots,
)


def _image(path: Path, width: int = 20, height: int = 16) -> np.ndarray:
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    pixels[:, :, 0] = np.arange(width, dtype=np.uint8)
    pixels[:, :, 1] = np.arange(height, dtype=np.uint8)[:, None]
    pixels[:, :, 2] = 201
    Image.fromarray(pixels, mode="RGB").save(path)
    return pixels


def _masks(height: int = 16, width: int = 20):
    target = np.zeros((height, width), dtype=bool)
    target[4:12, 6:15] = True
    other = np.zeros((height, width), dtype=bool)
    other[2:9, 2:9] = True
    return target, other


def test_pixel_formula_and_target_overlap_priority():
    source = np.array(
        [[[0, 1, 2], [100, 101, 102], [250, 251, 252]]],
        dtype=np.uint8,
    )
    target = np.array([[False, True, False]])
    other = np.array([[True, True, False]])

    result = blend_non_target_people(source, target, [target, other])

    expected = (45 * source[0, 0].astype(np.uint16) + 55 * 128 + 50) // 100
    assert np.array_equal(result[0, 0], expected.astype(np.uint8))
    assert np.array_equal(result[0, 1], source[0, 1])
    assert np.array_equal(result[0, 2], source[0, 2])


def test_target_anchored_local_keeps_frozen_crop_and_five_pixel_contour(tmp_path):
    image_path = tmp_path / "source.png"
    _image(image_path)
    target, other = _masks()

    evidence = np.asarray(
        build_target_anchored_evidence(
            image_path,
            [6, 4, 15, 12],
            target,
            [target, other],
            full_scene=False,
        )
    )

    assert evidence.shape[:2] == (14, 17)  # 固定 35% crop: [2, 1, 19, 15]
    assert BEHAVIOR_CONTOUR_WIDTH == 5
    assert np.all(evidence[4, 4] == (255, 0, 0))


def test_arm_assets_follow_frozen_a_b_c_contract(tmp_path):
    image_path = tmp_path / "source.png"
    _image(image_path)
    target, other = _masks()

    arm_a = build_arm_evidence("A", image_path, [6, 4, 15, 12], target, [target, other])
    arm_b = build_arm_evidence("B", image_path, [6, 4, 15, 12], target, [target, other])
    arm_c = build_arm_evidence("C", image_path, [6, 4, 15, 12], target, [target, other])

    assert len(arm_a.first_pass) == len(arm_b.first_pass) == len(arm_c.first_pass) == 2
    assert arm_a.fallback is not None
    assert arm_b.fallback is None
    assert arm_c.fallback is not None
    assert arm_a.first_pass[1].size == arm_b.first_pass[1].size == (17, 14)
    assert arm_a.fallback.size == arm_c.fallback.size == (20, 16)


def test_mask_cache_generates_once_reuses_exact_bytes_and_rejects_corruption(tmp_path):
    image_path = tmp_path / "source.png"
    _image(image_path)
    image_sha = hashlib.sha256(image_path.read_bytes()).hexdigest()
    target, other = _masks()
    calls = []

    def segmenter(path, bboxes):
        calls.append((path, bboxes))
        return [target, other]

    candidates = [
        {"id": "A", "bbox": [6, 4, 15, 12]},
        {"id": "B", "bbox": [2, 2, 9, 9]},
    ]
    cache = MaskCache(tmp_path / "cache")
    first_manifest = cache.build(
        case_id="case",
        image_path=image_path,
        image_sha256=image_sha,
        candidates=candidates,
        segmenter=segmenter,
    )
    second_manifest = cache.build(
        case_id="case",
        image_path=image_path,
        image_sha256=image_sha,
        candidates=candidates,
        segmenter=segmenter,
    )
    loaded = cache.load(
        image_path=image_path,
        image_sha256=image_sha,
        candidates=candidates,
    )

    assert first_manifest == second_manifest
    assert len(calls) == 1
    assert np.array_equal(loaded["A"], target)
    assert np.array_equal(loaded["B"], other)

    manifest = json.loads(first_manifest.read_text(encoding="utf-8"))
    mask_path = first_manifest.parent / manifest["masks"][0]["path"]
    mask_path.write_bytes(mask_path.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="SHA-256"):
        cache.load(
            image_path=image_path,
            image_sha256=image_sha,
            candidates=candidates,
        )


def test_png_and_manifest_sha_are_byte_auditable(tmp_path):
    image = Image.new("RGB", (3, 2), (10, 20, 30))
    image_path = tmp_path / "evidence.png"
    record = save_png(image, image_path)
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, {"artifacts": [record]})

    assert record["sha256"] == hashlib.sha256(image_path.read_bytes()).hexdigest()
    assert record["bytes"] == image_path.stat().st_size
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["artifacts"][0] == record


def test_materialize_all_arms_and_refuse_manifest_overwrite(tmp_path):
    image_path = tmp_path / "source.png"
    _image(image_path)
    image_sha = hashlib.sha256(image_path.read_bytes()).hexdigest()
    target, other = _masks()
    case = {
        "case_id": "case",
        "image_sha256": image_sha,
        "candidates": [
            {"id": "A", "bbox": [6, 4, 15, 12]},
            {"id": "B", "bbox": [2, 2, 9, 9]},
        ],
    }

    manifest_path = materialize_case_evidence(
        tmp_path / "output", case, image_path, {"A": target, "B": other}
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert len(payload["artifacts"]) == 16  # 每 candidate: A=3, B=2, C=3
    assert {row["arm"] for row in payload["artifacts"]} == {"A", "B", "C"}
    assert all(Path(row["path"]).exists() for row in payload["artifacts"])
    with pytest.raises(ValueError, match="禁止覆盖"):
        materialize_case_evidence(
            tmp_path / "output", case, image_path, {"A": target, "B": other}
        )


def test_schedule_expands_frozen_order_and_count():
    selection = {
        "cases": [
            {
                "case_id": "case",
                "candidates": [
                    {"id": "A", "bbox": [0, 0, 1, 1]},
                    {"id": "B", "bbox": [1, 1, 2, 2]},
                ],
            }
        ]
    }
    schedule = {
        "failed_execution_replacement": False,
        "challenge_schedule": [
            {"case_id": "case", "repetition": 1, "arm_order": ["B", "A", "C"]}
        ],
        "F1_schedule": [],
        "totals": {"scheduled_first_pass_candidate_calls": 6},
    }

    slots = expand_schedule(selection, schedule)

    assert [slot.arm for slot in slots] == ["B", "B", "A", "A", "C", "C"]
    assert len({slot.slot_id for slot in slots}) == 6


def test_fallback_is_uncertain_only_and_binary_results_are_immutable(tmp_path):
    image = Image.new("RGB", (1, 1), (0, 0, 0))
    evidence = ArmEvidence(first_pass=(image, image), fallback=image)
    slots = [
        Slot("case", 1, "A", {"id": "s"}),
        Slot("case", 1, "C", {"id": "u", "expected": "satisfied"}),
        Slot("case", 1, "B", {"id": "b"}),
    ]
    answers = iter(["satisfied", "uncertain", "not_satisfied", "uncertain"])
    calls = []

    def verifier(images):
        calls.append(len(images))
        return next(answers)

    recorder = ResultRecorder(tmp_path / "results.jsonl")
    run_slots(
        slots,
        evidence_provider=lambda _slot: evidence,
        verifier=verifier,
        recorder=recorder,
    )
    rows = [json.loads(line) for line in recorder.path.read_text(encoding="utf-8").splitlines()]

    assert calls == [2, 2, 1, 2]
    assert rows[0]["final_status"] == "satisfied" and not rows[0]["fallback_used"]
    assert rows[1]["final_status"] == "not_satisfied" and rows[1]["fallback_used"]
    assert rows[1]["fallback_classification"] == "fallback_harm"
    assert rows[2]["final_status"] == "uncertain" and not rows[2]["fallback_used"]


@pytest.mark.parametrize(
    ("candidate", "final", "expected_classification"),
    [
        ({"expected": "satisfied"}, "satisfied", "correctly_resolved"),
        ({"expected": "satisfied"}, "uncertain", "still_uncertain"),
        ({"expected": "satisfied"}, "not_satisfied", "fallback_harm"),
        ({"expected": "not_satisfied"}, "satisfied", "fallback_harm"),
        ({"expected": "uncertain"}, "uncertain", "correctly_preserved"),
        ({"expected": "uncertain"}, "not_satisfied", "fallback_harm"),
        (
            {"allowed": ["not_satisfied", "uncertain"]},
            "satisfied",
            "fallback_harm",
        ),
        (
            {"allowed": ["not_satisfied", "uncertain"]},
            "not_satisfied",
            "non_harm",
        ),
    ],
)
def test_fallback_harm_is_mechanically_classified(
    candidate, final, expected_classification
):
    assert classify_fallback(candidate, final) == expected_classification


def test_failure_is_retained_schedule_continues_and_slot_is_not_rerun(tmp_path):
    image = Image.new("RGB", (1, 1), (0, 0, 0))
    evidence = ArmEvidence(first_pass=(image, image), fallback=None)
    slots = [
        Slot("case", 1, "B", {"id": "bad"}),
        Slot("case", 1, "B", {"id": "good"}),
    ]

    def provider(slot):
        if slot.candidate["id"] == "bad":
            raise RuntimeError("evidence failed")
        return evidence

    recorder = ResultRecorder(tmp_path / "results.jsonl")
    run_slots(
        slots,
        evidence_provider=provider,
        verifier=lambda _images: "not_satisfied",
        recorder=recorder,
    )
    rows = [json.loads(line) for line in recorder.path.read_text(encoding="utf-8").splitlines()]

    assert [row["terminal"] for row in rows] == ["failed", "success"]
    assert rows[0]["failure_type"] == "RuntimeError"
    rerun_provider_calls = []
    run_slots(
        slots,
        evidence_provider=lambda slot: rerun_provider_calls.append(slot) or evidence,
        verifier=lambda _images: "not_satisfied",
        recorder=recorder,
    )
    assert rerun_provider_calls == []
    assert len(recorder.path.read_text(encoding="utf-8").splitlines()) == 2

    with pytest.raises(ValueError, match="禁止替换"):
        recorder.append(rows[0])
