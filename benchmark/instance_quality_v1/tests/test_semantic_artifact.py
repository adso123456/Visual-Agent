import hashlib
import json

import pytest

from benchmark.instance_quality_v1.scripts.evaluate import report_state, validate_semantic_artifact
from benchmark.instance_quality_v1.scripts.run_semantic_probe import _attribute


def test_semantic_artifact_is_bound_to_raw_review_and_gt(tmp_path):
    raw_path = tmp_path / "candidates.json"
    review_path = tmp_path / "review.json"
    spec_path = tmp_path / "semantic_probe_v1.json"
    raw_path.write_text('{"raw":1}\n', encoding="utf-8")
    review_path.write_text('{"review":1}\n', encoding="utf-8")
    spec_path.write_text('{"benchmark_version":"1.0","probe":"semantic"}\n', encoding="utf-8")
    raw = {"images": [{"image_id": "T1", "candidates": [{"id": "C001"}]}]}
    semantic = {
        "benchmark_version": "1.0",
        "model": "qwen3-vl-flash",
        "provider": "dashscope_openai_compatible",
        "prompt_version": "semantic_constraint_v1",
        "probe_type": "predeclared_semantic_constraint",
        "semantic_spec_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
        "raw_candidates_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "review_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        "gt_fingerprint": "gt-v1",
        "created_at": "2026-08-14T00:00:00Z",
        "image_leaves_machine": True,
        "images": [{"image_id": "T1", "candidates": [{"id": "C001", "attribution": "VLM_CORRECT"}]}],
    }
    assert validate_semantic_artifact(semantic, raw_path, review_path, spec_path, raw, "gt-v1") is semantic

    stale = json.loads(json.dumps(semantic))
    stale["review_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SEMANTIC_ARTIFACT_REVIEW_MISMATCH"):
        validate_semantic_artifact(stale, raw_path, review_path, spec_path, raw, "gt-v1")

    incomplete = json.loads(json.dumps(semantic))
    incomplete["images"][0]["candidates"] = []
    with pytest.raises(ValueError, match="SEMANTIC_ARTIFACT_CANDIDATE_SET_MISMATCH"):
        validate_semantic_artifact(incomplete, raw_path, review_path, spec_path, raw, "gt-v1")


def test_semantic_attribution_respects_predeclared_evidence_and_expected_answer():
    usable = {"classification": "VALID_INSTANCE", "completeness": "COMPLETE"}
    assert _attribute(usable, "YES", True, "YES") == "VLM_CORRECT"
    assert _attribute(usable, "YES", True, "NO") == "VLM_SEMANTIC_LIMIT"
    assert _attribute(usable, "NO", True, "UNCLEAR") == "VLM_SEMANTIC_LIMIT"
    assert _attribute(usable, "YES", False, None) == "DETECTOR_DOWNSTREAM_UNUSABLE"


def test_frozen_report_preserves_real_review_provenance():
    reviews = {
        "review_source": "human_confirmed_codex_manual_visual_audit_gt_repaired_v1_1",
        "images": [{"reviewed_by": "human", "review_status": "COMPLETE"}],
    }
    assert report_state(reviews)["review_source"] == reviews["review_source"]
