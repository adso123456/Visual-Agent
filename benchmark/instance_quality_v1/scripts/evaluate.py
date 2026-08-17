import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmark.instance_quality_v1.evaluator import evaluate
from benchmark.instance_quality_v1.annotation_tool.gt_store import GroundTruthStore


ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_semantic_artifact(semantic, raw_path, review_path, spec_path, raw, expected_gt_fingerprint):
    required = {
        "benchmark_version", "model", "provider", "prompt_version", "probe_type",
        "semantic_spec_sha256",
        "raw_candidates_sha256", "review_sha256", "gt_fingerprint",
        "created_at", "image_leaves_machine", "images",
    }
    if not required <= set(semantic):
        raise ValueError(f"SEMANTIC_ARTIFACT_UNVERIFIABLE: missing={sorted(required - set(semantic))}")
    if semantic["raw_candidates_sha256"] != hashlib.sha256(raw_path.read_bytes()).hexdigest():
        raise ValueError("SEMANTIC_ARTIFACT_RAW_MISMATCH")
    if semantic["review_sha256"] != hashlib.sha256(review_path.read_bytes()).hexdigest():
        raise ValueError("SEMANTIC_ARTIFACT_REVIEW_MISMATCH")
    if semantic["gt_fingerprint"] != expected_gt_fingerprint:
        raise ValueError("SEMANTIC_ARTIFACT_GT_MISMATCH")
    if semantic["probe_type"] != "predeclared_semantic_constraint":
        raise ValueError("SEMANTIC_ARTIFACT_PROBE_TYPE_INVALID")
    if semantic["prompt_version"] != "semantic_constraint_v1":
        raise ValueError("SEMANTIC_ARTIFACT_PROMPT_VERSION_INVALID")
    if semantic["semantic_spec_sha256"] != hashlib.sha256(spec_path.read_bytes()).hexdigest():
        raise ValueError("SEMANTIC_ARTIFACT_SPEC_MISMATCH")
    expected = {item["image_id"]: {candidate["id"] for candidate in item["candidates"]} for item in raw["images"]}
    actual = {item.get("image_id"): {candidate.get("id") for candidate in item.get("candidates", [])} for item in semantic["images"]}
    if actual != expected:
        raise ValueError("SEMANTIC_ARTIFACT_CANDIDATE_SET_MISMATCH")
    if semantic["image_leaves_machine"] is not True:
        raise ValueError("SEMANTIC_ARTIFACT_TRANSPORT_DECLARATION_INVALID")
    return semantic


def report_state(reviews: dict) -> dict:
    """从 Candidate Review 文档推导 report 的正式状态（绝不人工改字段）。

    只有当 24 张图的 review 全部 reviewed_by=human 且 review_status=COMPLETE 时，
    才输出 FROZEN / official_baseline=true；否则一律 PROVISIONAL。
    状态由上游输入推导，防止草稿与正式资产混淆。
    """
    images = reviews.get("images", [])
    all_human = all(
        entry.get("reviewed_by") == "human" and entry.get("review_status") == "COMPLETE"
        for entry in images
    ) if images else False
    review_source = reviews.get("review_source")
    if not review_source:
        review_source = "human" if all_human else "assistant_vision_draft"
    if all_human:
        return {
            "status": "FROZEN",
            "official_baseline": True,
            "review_source": "human",
            "review_status": "COMPLETE",
            "warning": None,
        }
    return {
        "status": "PROVISIONAL",
        "official_baseline": False,
        "review_source": review_source,
        "review_status": "IN_PROGRESS",
        "warning": "NOT FOR FORMAL DETECTOR A/B — Candidate Review 尚未人工确认",
    }


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    ground_truth = json.loads((ROOT / "annotations" / "ground_truth.json").read_text(encoding="utf-8"))
    run = json.loads((ROOT / "runs" / "grounding_dino_base" / "candidates.json").read_text(encoding="utf-8"))
    reviews = json.loads((ROOT / "reviews" / "grounding_dino_base.json").read_text(encoding="utf-8"))
    raw_path = ROOT / "runs" / "grounding_dino_base" / "candidates.json"
    review_path = ROOT / "reviews" / "grounding_dino_base.json"
    semantic_path = ROOT / "runs" / "grounding_dino_base" / "semantic_results.json"
    semantic_spec_path = ROOT / "annotations" / "semantic_probe_v1.json"
    semantic = {"images": []}
    if semantic_path.exists():
        semantic = validate_semantic_artifact(
            json.loads(semantic_path.read_text(encoding="utf-8")),
            raw_path,
            review_path,
            semantic_spec_path,
            run,
            GroundTruthStore(ROOT).fingerprint(),
        )
    fingerprint = hashlib.sha256((canonical(manifest) + canonical(ground_truth)).encode()).hexdigest()
    config_hash = hashlib.sha256(canonical(run["detector_config"]).encode()).hexdigest()
    metrics = evaluate(manifest, ground_truth, run["images"], reviews["images"], semantic)
    state = report_state(reviews)
    test = [item for item in manifest["images"] if item["split"] == "test"]
    report = {
        "benchmark_version": "1.0",
        "status": state["status"],
        "official_baseline": state["official_baseline"],
        "review_source": state["review_source"],
        "review_status": state["review_status"],
        "warning": state["warning"],
        "benchmark_fingerprint": fingerprint,
        "gt_fingerprint": GroundTruthStore(ROOT).fingerprint(),
        "detector_config_hash": config_hash,
        "dataset": {"test_count": len(test), "calibration_count": len(manifest["images"]) - len(test), "scenario_distribution": dict(Counter(x["scenario"] for x in test)), "target_distribution": dict(Counter(x["target_object"] for x in test))},
        "detector_config": run["detector_config"], "metrics": metrics, "runtime": run["runtime"],
        "semantic_probe": {
            "probe_type": semantic.get("probe_type"),
            "prompt_version": semantic.get("prompt_version"),
            "semantic_spec_sha256": semantic.get("semantic_spec_sha256"),
        },
        "deployment": {
            "detector_local_inference": True,
            "semantic_probe_included": bool(semantic["images"]),
            "requires_cloud_api": bool(semantic["images"]),
            "requires_api_token": bool(semantic["images"]),
            "image_leaves_machine": bool(semantic["images"]),
            "model_license": "UNKNOWN (local cache contains no model card)",
        },
    }
    reports = ROOT / "reports"; reports.mkdir(exist_ok=True)
    (reports / "grounding_dino_base_v1.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")

    # Markdown：顶部醒目状态横幅（provisional 时）
    banner = []
    if not state["official_baseline"]:
        banner = [
            "> \u26a0\ufe0f STATUS: **PROVISIONAL / NOT FROZEN**",
            f"> Candidate Review: {state['review_source']}（24/24 IN_PROGRESS，待人工确认）",
            "> DO NOT USE FOR FORMAL DETECTOR A/B",
            ">",
            f"> 这些指标基于 {state['review_source']} Candidate Review 计算，不是正式基线。",
            "> 人工确认完成后，由 evaluator 重新生成 FROZEN 版本（status=FROZEN / official_baseline=true）。",
            "",
        ]
    lines = [
        "# Grounding DINO Base — Instance Quality Benchmark v1.0",
        "",
        *banner,
        f"- Status: {state['status']}",
        f"- Official baseline: {state['official_baseline']}",
        f"- Review source: {state['review_source']}",
        f"- Review status: {state['review_status']}",
        f"- Benchmark fingerprint: `{fingerprint}`",
        f"- Test / Calibration: {len(test)} / {len(manifest['images']) - len(test)}",
        f"- Instance Recall: {metrics['instance_recall']}",
        f"- Instance Purity: {metrics['instance_purity']}",
        f"- Semantic Downstream Usability: {metrics['downstream_usability']['rate']}",
        f"- Semantic definition: {metrics['downstream_usability']['definition']}",
        f"- Semantic VLM correct / limit: {metrics['downstream_usability']['vlm_correct']} / {metrics['downstream_usability']['vlm_semantic_limit']}",
        f"- Detector downstream unusable: {metrics['downstream_usability']['detector_downstream_unusable']}",
        f"- Semantic spec SHA-256: `{semantic.get('semantic_spec_sha256')}`",
        "",
        "See `grounding_dino_base_v1.json` for complete machine-readable results.",
    ]
    (reports / "grounding_dino_base_v1.md").write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    print(json.dumps({"status": state["status"], "official_baseline": state["official_baseline"], "review_source": state["review_source"], "benchmark_fingerprint": fingerprint, "metrics": metrics}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
