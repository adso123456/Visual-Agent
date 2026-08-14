from pathlib import Path

from .draft_store import DraftStore
from .gt_store import GroundTruthStore


def main():
    root = Path(__file__).resolve().parents[1]
    store = GroundTruthStore(root)
    drafts = DraftStore(root)
    loaded, skipped = 0, []
    for meta in store.test_images:
        entry = store.image_entry(meta["image_id"])
        if entry["instances"]:
            skipped.append(meta["image_id"])
            continue
        drafts.load_for_human_review(store, meta["image_id"])
        loaded += 1
    print(f"Loaded {loaded} assistant drafts as IN_PROGRESS/pending_human_review.")
    if skipped:
        print("Skipped images with existing boxes: " + ", ".join(skipped))


if __name__ == "__main__":
    main()
