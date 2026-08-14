"""GT-only persistence. This module never reads detector or review artifacts."""

import hashlib
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from benchmark.instance_quality_v1.schema import (
    CROWDING,
    SCALES,
    SEMANTIC_VISIBILITY,
    VISIBILITY,
    validate_ground_truth,
    validate_manifest,
)


ANNOTATION_STATUSES = {"UNSTARTED", "IN_PROGRESS", "COMPLETE"}


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def atomic_write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def new_document(manifest):
    test_images = [item for item in validate_manifest(manifest) if item["split"] == "test"]
    return {
        "benchmark_version": "1.0",
        "annotation_state": "DRAFT",
        "images": [
            {
                "image_id": item["image_id"],
                "annotation_status": "UNSTARTED",
                "updated_at": None,
                "reviewed_by": "human",
                "instances": [],
            }
            for item in test_images
        ],
    }


def validate_document(manifest, document):
    validate_ground_truth(manifest, document)
    if document.get("annotation_state") not in {"DRAFT", "FROZEN"}:
        raise ValueError("annotation_state must be DRAFT or FROZEN")
    for entry in document["images"]:
        if entry.get("annotation_status") not in ANNOTATION_STATUSES:
            raise ValueError("invalid annotation_status")
        if entry.get("reviewed_by") not in {"human", "pending_human_review"}:
            raise ValueError("invalid reviewed_by")
        if entry["annotation_status"] == "COMPLETE" and entry["reviewed_by"] != "human":
            raise ValueError("COMPLETE images must be reviewed_by=human")
        for instance in entry["instances"]:
            notes = instance.get("notes", "")
            if not isinstance(notes, str):
                raise ValueError("notes must be a string")
            if not instance["evaluable"] and not notes.strip():
                raise ValueError("evaluable=false requires non-empty notes")
    return document


class GroundTruthStore:
    def __init__(self, root):
        self.root = Path(root)
        self.manifest_path = self.root / "manifest.json"
        self.annotation_path = self.root / "annotations" / "ground_truth.json"
        self.freeze_path = self.root / "annotations" / "ground_truth.freeze.json"
        self.correction_log_path = self.root / "annotations" / "annotation_corrections.jsonl"
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        validate_manifest(self.manifest)
        self.test_images = [item for item in self.manifest["images"] if item["split"] == "test"]
        if self.annotation_path.exists():
            self.document = json.loads(self.annotation_path.read_text(encoding="utf-8"))
        else:
            self.document = new_document(self.manifest)
        validate_document(self.manifest, self.document)

    @property
    def frozen(self):
        return self.document.get("annotation_state") == "FROZEN" or self.freeze_path.exists()

    def image_entry(self, image_id):
        return next(item for item in self.document["images"] if item["image_id"] == image_id)

    def image_meta(self, image_id):
        return next(item for item in self.test_images if item["image_id"] == image_id)

    def _ensure_writable(self):
        if self.frozen:
            raise PermissionError("GROUND_TRUTH_FROZEN")

    def save(self):
        self._ensure_writable()
        validate_document(self.manifest, self.document)
        atomic_write_json(self.annotation_path, self.document)

    def _commit(self, document):
        self._ensure_writable()
        validate_document(self.manifest, document)
        atomic_write_json(self.annotation_path, document)
        self.document = document

    def next_instance_id(self, image_id):
        used = {item["instance_id"] for item in self.image_entry(image_id)["instances"]}
        index = 1
        while f"I{index:02d}" in used:
            index += 1
        return f"I{index:02d}"

    def upsert_instance(self, image_id, instance, original_id=None):
        self._ensure_writable()
        document = deepcopy(self.document)
        entry = next(item for item in document["images"] if item["image_id"] == image_id)
        meta = self.image_meta(image_id)
        value = deepcopy(instance)
        value["target_object"] = meta["target_object"]
        existing = {item["instance_id"]: item for item in entry["instances"]}
        if original_id is None and value["instance_id"] in existing:
            raise ValueError("duplicate instance_id")
        if original_id is not None and value["instance_id"] != original_id and value["instance_id"] in existing:
            raise ValueError("duplicate instance_id")
        if original_id is None:
            entry["instances"].append(value)
        else:
            index = next((i for i, item in enumerate(entry["instances"]) if item["instance_id"] == original_id), None)
            if index is None:
                raise ValueError("instance does not exist")
            entry["instances"][index] = value
        entry["annotation_status"] = "IN_PROGRESS"
        entry["updated_at"] = utc_now()
        self._commit(document)

    def delete_instance(self, image_id, instance_id):
        self._ensure_writable()
        document = deepcopy(self.document)
        entry = next(item for item in document["images"] if item["image_id"] == image_id)
        before = len(entry["instances"])
        entry["instances"] = [item for item in entry["instances"] if item["instance_id"] != instance_id]
        if len(entry["instances"]) == before:
            raise ValueError("instance does not exist")
        entry["annotation_status"] = "IN_PROGRESS"
        entry["updated_at"] = utc_now()
        self._commit(document)

    def mark_complete(self, image_id, confirmed=False):
        self._ensure_writable()
        if not confirmed:
            raise ValueError("explicit whole-image confirmation is required")
        document = deepcopy(self.document)
        entry = next(item for item in document["images"] if item["image_id"] == image_id)
        entry["annotation_status"] = "COMPLETE"
        entry["reviewed_by"] = "human"
        entry.pop("draft_source", None)
        entry.pop("draft_review_note", None)
        entry["updated_at"] = utc_now()
        self._commit(document)

    def all_complete(self):
        return all(item["annotation_status"] == "COMPLETE" for item in self.document["images"])

    def progress(self):
        return {
            "completed": sum(item["annotation_status"] == "COMPLETE" for item in self.document["images"]),
            "total": len(self.document["images"]),
        }

    def fingerprint(self):
        payload = {"manifest": self.manifest, "image_sha256": {item["image_id"]: item["sha256"] for item in self.test_images}, "ground_truth": self.document["images"]}
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def freeze(self):
        self._ensure_writable()
        if not self.all_complete():
            raise RuntimeError("GROUND_TRUTH_NOT_COMPLETE")
        validate_document(self.manifest, self.document)
        fingerprint = self.fingerprint()
        self.document["annotation_state"] = "FROZEN"
        atomic_write_json(self.annotation_path, self.document)
        atomic_write_json(self.freeze_path, {"benchmark_version": "1.0", "gt_fingerprint": fingerprint, "frozen_at": utc_now()})
        return fingerprint

    def unfreeze(self, reason, image_id, changed_fields):
        if not self.frozen:
            raise RuntimeError("GROUND_TRUTH_NOT_FROZEN")
        if not reason.strip() or image_id not in {item["image_id"] for item in self.test_images} or not changed_fields:
            raise ValueError("reason, valid image_id, and changed_fields are required")
        event = {"timestamp": utc_now(), "reviewed_by": "human", "reason": reason.strip(), "image_id": image_id, "changed_fields": list(changed_fields)}
        self.correction_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.correction_log_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.document["annotation_state"] = "DRAFT"
        if self.freeze_path.exists():
            self.freeze_path.unlink()
        atomic_write_json(self.annotation_path, self.document)


ENUMS = {"visibility": sorted(VISIBILITY), "scale": sorted(SCALES), "crowding": sorted(CROWDING), "semantic_visibility": sorted(SEMANTIC_VISIBILITY)}
