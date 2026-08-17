"""一次性修复 Candidate Review 证明的 37 个 GT omission，并冻结 benchmark v1.1。"""

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmark.instance_quality_v1.annotation_tool.gt_store import GroundTruthStore, atomic_write_json, utc_now


ROOT = Path(__file__).resolve().parents[1]
OLD_FINGERPRINT = "110a9dda47c1c4adbbfdb4a5b151fa0ef8efaa1acc7b5ede37f10fa658320931"
SOURCE_COMMIT = "a65c207e3c65ce8523109b01eef251f419a42d78"


def instance(instance_id, bbox, visibility, scale, crowding, candidate_id, note):
    return {
        "candidate_id": candidate_id,
        "gt": {
            "instance_id": instance_id,
            "bbox": bbox,
            "target_object": None,
            "visibility": visibility,
            "scale": scale,
            "crowding": crowding,
            "semantic_visibility": "insufficient",
            "evaluable": True,
            "notes": "v1.1 GT omission repair; manually bounded from the original image. " + note,
        },
    }


ADDITIONS = {
    "TST_SPARSE_001": [instance("I04", [0, 620, 100, 1018], "partial", "small", "dense", "C004", "Far-left boundary person." )],
    "TST_SPARSE_003": [
        instance("I02", [0, 1315, 42, 1348], "partial", "small", "dense", "C004", "Far-left background boat."),
        instance("I03", [52, 1308, 170, 1345], "full", "small", "dense", "C005", "Background boat."),
        instance("I04", [210, 1303, 324, 1343], "full", "small", "dense", "C002", "Background boat."),
        instance("I05", [308, 1302, 374, 1337], "full", "small", "dense", "C006", "Background boat."),
        instance("I06", [354, 1292, 480, 1335], "full", "small", "dense", "C003", "Background boat."),
    ],
    "TST_DENSE_001": [
        instance("I02", [0, 325, 170, 854], "partial", "large", "dense", "C003", "Blurred left-background person."),
        instance("I03", [928, 412, 1138, 840], "heavily_occluded", "large", "dense", "C004", "Blurred person behind the foreground subject."),
        instance("I04", [1095, 355, 1279, 854], "partial", "large", "dense", "C002", "Blurred right-background person."),
    ],
    "TST_DENSE_002": [instance("I17", [614, 1075, 651, 1142], "full", "small", "dense", "C005", "Tiny human-shaped figure above the tent line." )],
    "TST_SMALL_003": [instance("I07", [0, 309, 56, 432], "partial", "small", "dense", "C004", "Far-left boundary boat." )],
    "TST_OCCLUSION_001": [
        instance("I04", [1196, 596, 1230, 672], "full", "small", "dense", "C004", "Upper-deck person."),
        instance("I05", [1068, 604, 1103, 680], "full", "small", "dense", "C005", "Upper-deck person."),
        instance("I06", [1230, 598, 1270, 672], "full", "small", "dense", "C006", "Upper-deck person."),
        instance("I07", [1038, 600, 1078, 681], "full", "small", "dense", "C007", "Upper-deck person."),
        instance("I08", [104, 891, 143, 961], "full", "small", "dense", "C008", "Lower-deck person."),
        instance("I09", [662, 864, 704, 906], "heavily_occluded", "small", "dense", "C009", "Lower-deck partially visible person."),
        instance("I10", [640, 622, 682, 700], "full", "small", "dense", "C010", "Upper-deck person."),
        instance("I11", [728, 624, 768, 695], "full", "small", "dense", "C011", "Upper-deck person."),
        instance("I12", [616, 625, 648, 702], "full", "small", "dense", "C012", "Upper-deck person."),
        instance("I13", [414, 870, 454, 952], "full", "small", "dense", "C013", "Lower-deck person."),
        instance("I14", [1238, 855, 1273, 936], "partial", "small", "dense", "C014", "Right lower-deck boundary person."),
        instance("I15", [796, 622, 829, 691], "full", "small", "dense", "C015", "Upper-deck person."),
        instance("I16", [546, 635, 575, 705], "full", "small", "dense", "C016", "Upper-deck person."),
        instance("I17", [565, 633, 600, 704], "full", "small", "dense", "C017", "Upper-deck person."),
        instance("I18", [592, 633, 628, 703], "full", "small", "dense", "C018", "Upper-deck person."),
        instance("I19", [602, 869, 643, 907], "heavily_occluded", "small", "dense", "C019", "Lower-deck partially visible person."),
        instance("I20", [634, 865, 668, 906], "heavily_occluded", "small", "dense", "C020", "Lower-deck partially visible person."),
        instance("I21", [521, 648, 553, 705], "full", "small", "dense", "C021", "Upper-deck person."),
    ],
    "TST_OCCLUSION_002": [instance("I06", [193, 157, 211, 182], "full", "small", "adjacent", "C005", "Second distant pedestrian." )],
    "TST_SCALE_001": [
        instance("I03", [954, 346, 1136, 416], "partial", "small", "dense", "C002", "Background boat."),
        instance("I04", [1124, 348, 1279, 442], "partial", "small", "dense", "C003", "Far-right background boat."),
    ],
    "TST_SCALE_002": [
        instance("I06", [1126, 712, 1279, 960], "partial", "medium", "dense", "C004", "Right-boundary audience person."),
        instance("I07", [88, 728, 354, 960], "heavily_occluded", "large", "dense", "C005", "Lower-left audience person."),
        instance("I08", [205, 788, 434, 960], "heavily_occluded", "large", "dense", "C006", "Foreground audience person."),
    ],
    "TST_SCALE_003": [instance("I07", [752, 401, 800, 471], "heavily_occluded", "small", "dense", "C003", "Right-side car mostly hidden by vegetation." )],
    "TST_INTERFERENCE_003": [instance("I07", [20, 108, 107, 170], "partial", "small", "dense", "C006", "Far-left red car." )],
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    manifest_path = ROOT / "manifest.json"
    gt_path = ROOT / "annotations" / "ground_truth.json"
    raw_path = ROOT / "runs" / "grounding_dino_base" / "candidates.json"
    review_path = ROOT / "reviews" / "grounding_dino_base.json"
    audit_review_path = ROOT / "reviews" / "manual_visual_audit_v1.json"
    manifest, gt, raw = load(manifest_path), load(gt_path), load(raw_path)
    review, audit_review = load(review_path), load(audit_review_path)
    if gt.get("annotation_state") != "DRAFT" or manifest.get("benchmark_version") != "1.0":
        raise RuntimeError("EXPECTED_UNFROZEN_BENCHMARK_V1_0")

    for document in (manifest, gt, raw, review, audit_review):
        document["benchmark_version"] = "1.1"
    for name in ("asset_catalog.json", "provenance.json"):
        path = ROOT / name
        document = load(path)
        document["benchmark_version"] = "1.1"
        atomic_write_json(path, document)

    gt_by = {row["image_id"]: row for row in gt["images"]}
    review_by = {row["image_id"]: row for row in review["images"]}
    audit_by = {row["image_id"]: row for row in audit_review["images"]}
    manifest_by = {row["image_id"]: row for row in manifest["images"]}
    omission_rows = []
    now = utc_now()
    for image_id, additions in ADDITIONS.items():
        existing_ids = {row["instance_id"] for row in gt_by[image_id]["instances"]}
        review_candidates = {row["candidate_id"]: row for row in review_by[image_id]["candidates"]}
        audit_candidates = {row["candidate_id"]: row for row in audit_by[image_id]["candidates"]}
        for addition in additions:
            row = addition["gt"]
            if row["instance_id"] in existing_ids:
                raise RuntimeError(f"GT_INSTANCE_ALREADY_EXISTS:{image_id}:{row['instance_id']}")
            row["target_object"] = manifest_by[image_id]["target_object"]
            gt_by[image_id]["instances"].append(row)
            candidate_id = addition["candidate_id"]
            for candidate in (review_candidates[candidate_id], audit_candidates[candidate_id]):
                candidate["mapped_gt_instance_id"] = row["instance_id"]
                candidate["classification"] = "VALID_INSTANCE"
                candidate["completeness"] = "COMPLETE"
                candidate["review_notes"] = "Confirmed distinct visible target; GT omission repaired in benchmark v1.1."
            omission_rows.append({
                "image_id": image_id, "candidate_id": candidate_id,
                "new_gt_instance_id": row["instance_id"], "manual_gt_bbox": row["bbox"],
                "decision": "CONFIRMED_GT_OMISSION_REPAIRED",
            })
        gt_by[image_id]["updated_at"] = now
        gt_by[image_id]["annotation_status"] = "COMPLETE"
        gt_by[image_id]["reviewed_by"] = "human"
        review_by[image_id]["updated_at"] = now

    review["review_source"] = "human_confirmed_codex_manual_visual_audit_gt_repaired_v1_1"
    review["warning"] = None
    audit_review["review_source"] = "codex_manual_visual_audit_gt_repaired_v1_1"
    audit_review["warning"] = None
    review["confirmation"] = {
        "source": "User final audit identified GT omissions; Codex rechecked original images and repaired all 37 confirmed omissions.",
        "confirmed_at": now,
    }

    atomic_write_json(manifest_path, manifest)
    atomic_write_json(gt_path, gt)
    atomic_write_json(raw_path, raw)
    atomic_write_json(review_path, review)
    atomic_write_json(audit_review_path, audit_review)

    new_fingerprint = GroundTruthStore(ROOT).freeze()
    raw_sha = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    review_sha = hashlib.sha256(review_path.read_bytes()).hexdigest()
    spec_path = ROOT / "annotations" / "semantic_probe_v1.json"
    spec = load(spec_path)
    spec.update({
        "benchmark_version": "1.1", "gt_fingerprint": new_fingerprint,
        "raw_candidates_sha256": raw_sha, "review_sha256": review_sha,
        "frozen_at": utc_now(),
    })
    atomic_write_json(spec_path, spec)

    audit = {
        "benchmark_version": "1.1", "status": "COMPLETE",
        "source_commit": SOURCE_COMMIT, "old_gt_fingerprint": OLD_FINGERPRINT,
        "new_gt_fingerprint": new_fingerprint, "confirmed_omission_count": len(omission_rows),
        "affected_image_count": len(ADDITIONS), "review_method": "manual visual audit of original images",
        "omissions": omission_rows,
    }
    atomic_write_json(ROOT / "reports" / "gt_omission_repair_v1_1.json", audit)

    binding_audit_path = ROOT / "reports" / "raw_binding_audit_after.json"
    binding_audit = load(binding_audit_path)
    binding_audit["benchmark_version"] = "1.1"
    binding_audit["gt_fingerprint"] = new_fingerprint
    atomic_write_json(binding_audit_path, binding_audit)
    print(json.dumps({"new_gt_fingerprint": new_fingerprint, "omissions": len(omission_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
