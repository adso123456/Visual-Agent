import hashlib
import json
from collections import Counter
from pathlib import Path

from benchmark.instance_quality_v1.evaluator import evaluate


ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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
    semantic_path = ROOT / "runs" / "grounding_dino_base" / "semantic_results.json"
    semantic = json.loads(semantic_path.read_text(encoding="utf-8")) if semantic_path.exists() else {"images": []}
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
        "detector_config_hash": config_hash,
        "dataset": {"test_count": len(test), "calibration_count": len(manifest["images"]) - len(test), "scenario_distribution": dict(Counter(x["scenario"] for x in test)), "target_distribution": dict(Counter(x["target_object"] for x in test))},
        "detector_config": run["detector_config"], "metrics": metrics, "runtime": run["runtime"],
        "deployment": {"local_inference": True, "requires_cloud_api": False, "requires_api_token": False, "image_leaves_machine": False, "model_license": "UNKNOWN (local cache contains no model card)"},
    }
    reports = ROOT / "reports"; reports.mkdir(exist_ok=True)
    (reports / "grounding_dino_base_v1.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")

    # Markdown：顶部醒目状态横幅（provisional 时）
    banner = []
    if not state["official_baseline"]:
        banner = [
            "> \u26a0\ufe0f STATUS: **PROVISIONAL / NOT FROZEN**",
            "> Candidate Review: assistant_vision_draft（24/24 IN_PROGRESS，待人工确认）",
            "> DO NOT USE FOR FORMAL DETECTOR A/B",
            ">",
            "> 这些指标基于 assistant_vision_draft Candidate Review 计算，不是正式基线。",
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
        f"- Downstream Usability: {metrics['downstream_usability']['rate']}",
        "",
        "See `grounding_dino_base_v1.json` for complete machine-readable results.",
    ]
    (reports / "grounding_dino_base_v1.md").write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    print(json.dumps({"status": state["status"], "official_baseline": state["official_baseline"], "review_source": state["review_source"], "benchmark_fingerprint": fingerprint, "metrics": metrics}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
