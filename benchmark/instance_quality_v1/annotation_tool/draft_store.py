"""Assistant visual drafts. Reads only original-image-derived draft data, never detector output."""

import json
from copy import deepcopy
from pathlib import Path

from benchmark.instance_quality_v1.annotation_tool.gt_store import GroundTruthStore


class DraftStore:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "annotations" / "assistant_draft.json"
        self.document = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"images": []}

    def image_entry(self, image_id):
        return next((item for item in self.document["images"] if item["image_id"] == image_id), None)

    def load_for_human_review(self, gt_store: GroundTruthStore, image_id, replace=False):
        draft = self.image_entry(image_id)
        if not draft:
            raise ValueError("no assistant draft for this image")
        entry = gt_store.image_entry(image_id)
        if entry["instances"] and not replace:
            raise ValueError("formal GT already has instances; explicit replace confirmation required")
        document = deepcopy(gt_store.document)
        target = next(item for item in document["images"] if item["image_id"] == image_id)
        target["instances"] = deepcopy(draft["instances"])
        target["annotation_status"] = "IN_PROGRESS"
        target["reviewed_by"] = "pending_human_review"
        target["draft_source"] = "assistant_visual_draft_pending_human_review"
        target["draft_review_note"] = draft.get("review_note", "Review every bbox and scan the full image before completion.")
        gt_store._commit(document)
