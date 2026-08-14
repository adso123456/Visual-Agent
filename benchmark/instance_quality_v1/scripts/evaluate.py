import hashlib
import json
from collections import Counter
from pathlib import Path

from benchmark.instance_quality_v1.evaluator import evaluate


ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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
    test = [item for item in manifest["images"] if item["split"] == "test"]
    report = {
        "benchmark_version": "1.0", "benchmark_fingerprint": fingerprint, "detector_config_hash": config_hash,
        "dataset": {"test_count": len(test), "calibration_count": len(manifest["images"]) - len(test), "scenario_distribution": dict(Counter(x["scenario"] for x in test)), "target_distribution": dict(Counter(x["target_object"] for x in test))},
        "detector_config": run["detector_config"], "metrics": metrics, "runtime": run["runtime"],
        "deployment": {"local_inference": True, "requires_cloud_api": False, "requires_api_token": False, "image_leaves_machine": False, "model_license": "UNKNOWN (local cache contains no model card)"},
    }
    reports = ROOT / "reports"; reports.mkdir(exist_ok=True)
    (reports / "grounding_dino_base_v1.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Grounding DINO Base — Instance Quality Benchmark v1.0", "", f"- Benchmark fingerprint: `{fingerprint}`", f"- Test / Calibration: {len(test)} / {len(manifest['images']) - len(test)}", f"- Instance Recall: {metrics['instance_recall']}", f"- Instance Purity: {metrics['instance_purity']}", f"- Downstream Usability: {metrics['downstream_usability']['rate']}", "", "See `grounding_dino_base_v1.json` for complete machine-readable results."]
    (reports / "grounding_dino_base_v1.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"benchmark_fingerprint": fingerprint, "metrics": metrics}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
