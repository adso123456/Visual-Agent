"""为与历史提交同批入库的 raw candidates 补写可验证的图片绑定元数据。"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image

from benchmark.instance_quality_v1.annotation_tool.gt_store import atomic_write_json


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_digest(row):
    payload = json.dumps(row["candidates"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-commit", required=True)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    legacy = json.loads(subprocess.check_output(
        ["git", "show", f"{args.legacy_commit}:benchmark/instance_quality_v1/manifest.json"],
        cwd=ROOT.parents[1], text=True, encoding="utf-8",
    ))
    config = json.loads((ROOT / "configs" / "grounding_dino_base.json").read_text(encoding="utf-8"))
    run_root = ROOT / "runs" / "grounding_dino_base"
    aggregate_path = run_root / "candidates.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    rows = {item["image_id"]: item for item in aggregate["images"]}
    current_meta = {item["image_id"]: item for item in manifest["images"] if item["split"] == "test"}
    legacy_meta = {item["image_id"]: item for item in legacy["images"] if item["split"] == "test"}
    audit = []
    for image_id, meta in current_meta.items():
        image_path = ROOT / meta["relative_path"]
        legacy_item = legacy_meta.get(image_id)
        per_path = run_root / f"{image_id}_candidates.json"
        per_row = json.loads(per_path.read_text(encoding="utf-8"))
        row = rows[image_id]
        actual_sha = digest(image_path)
        with Image.open(image_path) as image:
            actual_size = image.size
        candidate_rows_match = candidate_digest(row) == candidate_digest(per_row)
        historical_match = bool(
            legacy_item
            and meta["sha256"] == legacy_item["sha256"] == actual_sha
            and (meta["width"], meta["height"]) == (legacy_item["width"], legacy_item["height"]) == actual_size
            and candidate_rows_match
        )
        status = "MATCH" if historical_match else "MISMATCH"
        audit.append({
            "image_id": image_id, "status": status, "evidence_commit": args.legacy_commit,
            "current_sha256": actual_sha, "current_width": actual_size[0], "current_height": actual_size[1],
            "legacy_sha256": legacy_item["sha256"] if legacy_item else None,
            "legacy_width": legacy_item["width"] if legacy_item else None,
            "legacy_height": legacy_item["height"] if legacy_item else None,
            "candidate_payload_sha256": candidate_digest(row), "aggregate_per_image_candidates_match": candidate_rows_match,
        })
        if not historical_match:
            continue
        binding = {
            "source_image_sha256": actual_sha, "source_width": actual_size[0], "source_height": actual_size[1],
            "detector_model": config["model"], "box_threshold": config["box_threshold"],
            "text_threshold": config["text_threshold"], "full_frame": config["full_frame"],
            "binding_attestation": {"method": "same_asset_and_raw_commit", "commit": args.legacy_commit},
        }
        row.update(binding)
        per_row.update(binding)
        atomic_write_json(per_path, per_row)
    atomic_write_json(aggregate_path, aggregate)
    report = {
        "legacy_commit": args.legacy_commit,
        "old_raw_candidate_count": sum(len(item["candidates"]) for item in aggregate["images"]),
        "matched_images": [item["image_id"] for item in audit if item["status"] == "MATCH"],
        "mismatched_images": [item["image_id"] for item in audit if item["status"] == "MISMATCH"],
        "unverifiable_images": [],
        "images": audit,
    }
    atomic_write_json(ROOT / "reports" / "raw_binding_audit_before.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
