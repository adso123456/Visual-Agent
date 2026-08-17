"""Candidate review persistence. Imported only by explicit review mode."""

import hashlib
import json
from pathlib import Path

from benchmark.instance_quality_v1.annotation_tool.gt_store import GroundTruthStore, atomic_write_json, utc_now
from benchmark.instance_quality_v1.schema import COMPLETENESS, GT_OMISSION_MARKERS, REVIEW_CLASSES, validate_raw_bindings


class CandidateReviewStore:
    def __init__(self, root):
        self.root = Path(root)
        self.gt = GroundTruthStore(root)
        if not self.gt.frozen or not self.gt.all_complete():
            raise RuntimeError("GROUND_TRUTH_NOT_FROZEN")
        self.raw_path = self.root / "runs" / "grounding_dino_base" / "candidates.json"
        self.review_path = self.root / "reviews" / "grounding_dino_base.json"
        self.raw_bytes = self.raw_path.read_bytes()
        self.raw_sha256 = hashlib.sha256(self.raw_bytes).hexdigest()
        self.raw = json.loads(self.raw_bytes.decode("utf-8"))
        validate_raw_bindings(self.gt.manifest, self.raw["images"])
        if self.review_path.exists():
            self.document = json.loads(self.review_path.read_text(encoding="utf-8"))
        else:
            self.document = {
                "benchmark_version": self.raw["benchmark_version"],
                "images": [
                    {"image_id": item["image_id"], "review_status": "IN_PROGRESS", "updated_at": None, "reviewed_by": "human", "candidates": []}
                    for item in self.raw["images"]
                ],
            }

    def raw_image(self, image_id):
        return next(item for item in self.raw["images"] if item["image_id"] == image_id)

    def review_image(self, image_id):
        return next(item for item in self.document["images"] if item["image_id"] == image_id)

    def validate_review(self, image_id, review):
        if review.get("classification") not in REVIEW_CLASSES:
            raise ValueError("invalid classification")
        if review.get("completeness") not in COMPLETENESS:
            raise ValueError("invalid completeness")
        gt_ids = {item["instance_id"] for item in self.gt.image_entry(image_id)["instances"]}
        mapped = review.get("mapped_gt_instance_id")
        if mapped is not None and mapped not in gt_ids:
            raise ValueError("mapped GT does not exist")
        if review["classification"] in {"VALID_INSTANCE", "PARTIAL_INSTANCE", "DUPLICATE_INSTANCE"} and mapped is None:
            raise ValueError("this classification requires mapped GT")
        if review["classification"] in {"FALSE_DETECTION", "MIXED_INSTANCE", "AMBIGUOUS"} and mapped is not None:
            raise ValueError("this classification requires null mapped GT under the current schema")
        if not isinstance(review.get("review_notes"), str) or not review["review_notes"].strip():
            raise ValueError("review_notes must be non-empty")
        if review["classification"] == "AMBIGUOUS" and any(
            marker in review["review_notes"].lower() for marker in GT_OMISSION_MARKERS
        ):
            raise ValueError("AMBIGUOUS cannot hide a confirmed GT omission")
        candidate_ids = {item["id"] for item in self.raw_image(image_id)["candidates"]}
        if review.get("candidate_id") not in candidate_ids:
            raise ValueError("candidate does not exist")

    def save_review(self, image_id, review):
        self.validate_review(image_id, review)
        entry = self.review_image(image_id)
        rows = {item["candidate_id"]: item for item in entry["candidates"]}
        rows[review["candidate_id"]] = review
        raw_order = [item["id"] for item in self.raw_image(image_id)["candidates"]]
        entry["candidates"] = [rows[item] for item in raw_order if item in rows]
        entry["review_status"] = "IN_PROGRESS"
        entry["updated_at"] = utc_now()
        atomic_write_json(self.review_path, self.document)
        self.assert_raw_unchanged()

    def mark_complete(self, image_id):
        raw_ids = {item["id"] for item in self.raw_image(image_id)["candidates"]}
        reviewed_ids = {item["candidate_id"] for item in self.review_image(image_id)["candidates"]}
        if raw_ids != reviewed_ids:
            raise RuntimeError("UNREVIEWED_CANDIDATES_REMAIN")
        self.review_image(image_id)["review_status"] = "COMPLETE"
        self.review_image(image_id)["reviewed_by"] = "human"
        self.review_image(image_id)["updated_at"] = utc_now()
        atomic_write_json(self.review_path, self.document)
        self.assert_raw_unchanged()

    def confirm_all(self, confirmation_source):
        if not isinstance(confirmation_source, str) or not confirmation_source.strip():
            raise ValueError("confirmation_source must be non-empty")
        for entry in self.document["images"]:
            raw_ids = {item["id"] for item in self.raw_image(entry["image_id"])["candidates"]}
            reviewed_ids = {item["candidate_id"] for item in entry["candidates"]}
            if raw_ids != reviewed_ids:
                raise RuntimeError(f"UNREVIEWED_CANDIDATES_REMAIN: {entry['image_id']}")
        confirmed_at = utc_now()
        for entry in self.document["images"]:
            entry["review_status"] = "COMPLETE"
            entry["reviewed_by"] = "human"
            entry["updated_at"] = confirmed_at
        self.document["review_source"] = "human_confirmed_codex_manual_visual_audit"
        self.document["warning"] = None
        self.document["confirmation"] = {
            "source": confirmation_source.strip(),
            "confirmed_at": confirmed_at,
        }
        atomic_write_json(self.review_path, self.document)
        self.assert_raw_unchanged()

    def assert_raw_unchanged(self):
        if hashlib.sha256(self.raw_path.read_bytes()).hexdigest() != self.raw_sha256:
            raise RuntimeError("RAW_CANDIDATES_MODIFIED")
