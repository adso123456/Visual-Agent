import json
from pathlib import Path

from benchmark.instance_quality_v1.schema import (
    validate_candidates_and_reviews,
    validate_ground_truth,
    validate_release_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main():
    manifest = load("manifest.json")
    summary = validate_release_manifest(manifest, ROOT)
    gt_path = ROOT / "annotations" / "ground_truth.json"
    if gt_path.exists():
        ground_truth = load("annotations/ground_truth.json")
        validate_ground_truth(manifest, ground_truth)
        run_path = ROOT / "runs" / "grounding_dino_base" / "candidates.json"
        review_path = ROOT / "reviews" / "grounding_dino_base.json"
        if run_path.exists() and review_path.exists():
            validate_candidates_and_reviews(manifest, ground_truth, load("runs/grounding_dino_base/candidates.json")["images"], load("reviews/grounding_dino_base.json")["images"])
    print(json.dumps({"status": "PASS", **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
