import ast
import hashlib
import json
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

from benchmark.instance_quality_v1.annotation_tool.geometry import normalize_clip_bbox, original_to_screen, screen_to_original
from benchmark.instance_quality_v1.annotation_tool.gt_store import GroundTruthStore
from benchmark.instance_quality_v1.annotation_tool.draft_store import DraftStore
from benchmark.instance_quality_v1.annotation_tool.review_store import CandidateReviewStore


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def fixture_root():
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    manifest = json.loads((SOURCE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return temporary, root, manifest


def instance(store, image_id, instance_id="I01", evaluable=True, notes=""):
    meta = store.image_meta(image_id)
    return {
        "instance_id": instance_id,
        "bbox": [1, 2, min(20, meta["width"]), min(30, meta["height"])],
        "target_object": meta["target_object"],
        "visibility": "full",
        "scale": "medium",
        "crowding": "isolated",
        "semantic_visibility": "sufficient",
        "evaluable": evaluable,
        "notes": notes,
    }


def expect_error(error_type, function):
    try:
        function()
    except error_type:
        return
    raise AssertionError(f"expected {error_type.__name__}")


def test_physical_isolation():
    paths = [SOURCE_ROOT / "annotation_tool" / name for name in ("geometry.py", "gt_store.py", "gt_app.py")]
    forbidden_modules = {"visual_agent", "torch", "transformers", "qwen", "sam", "review_store"}
    forbidden_paths = {"candidates.json", "grounding_dino_base", "phase9", "phase10", "phase11"}
    for path in paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): imports.update(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom): imports.add((node.module or "").lower())
        assert not any(any(name == item or name.startswith(item + ".") for item in forbidden_modules) for name in imports)
        assert not any(value in source.lower() for value in forbidden_paths)
    probe = subprocess.run(
        [sys.executable, "-c", "import sys; import benchmark.instance_quality_v1.annotation_tool.gt_app; assert 'benchmark.instance_quality_v1.annotation_tool.review_store' not in sys.modules; assert not any(name == 'visual_agent' or name.startswith('visual_agent.') for name in sys.modules)"],
        cwd=SOURCE_ROOT.parents[1], capture_output=True, text=True,
    )
    assert probe.returncode == 0, probe.stderr
    production_root = SOURCE_ROOT.parents[1] / "visual_agent"
    for path in production_root.rglob("*.py"):
        assert "benchmark.instance_quality_v1.annotation_tool" not in path.read_text(encoding="utf-8")

    temporary, root, _manifest = fixture_root()
    try:
        candidate_path = root / "runs" / "grounding_dino_base" / "candidates.json"
        candidate_path.parent.mkdir(parents=True)
        candidate_path.write_text("not valid json and must never be read in GT mode", encoding="utf-8")
        store = GroundTruthStore(root)
        assert len(store.test_images) == 24
    finally:
        temporary.cleanup()


def test_geometry():
    point = [321.25, 88.5]
    screen = original_to_screen(point, 2.5, [17, -9])
    restored = screen_to_original(screen, 2.5, [17, -9])
    assert restored == point
    assert normalize_clip_bbox([50, 70], [10, 20], 100, 100) == [10, 20, 50, 70]
    assert normalize_clip_bbox([-10, -4], [120, 130], 100, 100) == [0, 0, 100, 100]
    expect_error(ValueError, lambda: normalize_clip_bbox([5, 5], [5, 9], 100, 100))


def test_store_and_validation():
    temporary, root, manifest = fixture_root()
    try:
        store = GroundTruthStore(root)
        assert len(store.test_images) == 24 and all(item["split"] == "test" for item in store.test_images)
        image_id = store.test_images[0]["image_id"]
        value = instance(store, image_id)
        store.upsert_instance(image_id, value)
        assert (root / "annotations" / "ground_truth.json").is_file()
        assert not list((root / "annotations").glob("*.tmp"))
        reloaded = GroundTruthStore(root)
        assert reloaded.image_entry(image_id)["instances"][0]["bbox"] == value["bbox"]
        changed = deepcopy(value); changed["scale"] = "small"; changed["notes"] = "manual edit"
        reloaded.upsert_instance(image_id, changed, "I01")
        assert GroundTruthStore(root).image_entry(image_id)["instances"][0]["scale"] == "small"
        expect_error(ValueError, lambda: reloaded.upsert_instance(image_id, instance(reloaded, image_id, "I01")))
        bad = instance(reloaded, image_id, "I02"); bad["visibility"] = "invalid"
        expect_error(ValueError, lambda: reloaded.upsert_instance(image_id, bad))
        expect_error(ValueError, lambda: reloaded.upsert_instance(image_id, instance(reloaded, image_id, "I02", False, "")))
        reloaded.delete_instance(image_id, "I01")
        assert reloaded.image_entry(image_id)["instances"] == []
        expect_error(ValueError, lambda: reloaded.mark_complete(image_id, confirmed=False))
        reloaded.mark_complete(image_id, confirmed=True)
        assert GroundTruthStore(root).image_entry(image_id)["annotation_status"] == "COMPLETE"
    finally:
        temporary.cleanup()


def test_assistant_draft_requires_human_completion():
    temporary, root, _manifest = fixture_root()
    try:
        source = json.loads((SOURCE_ROOT / "annotations" / "assistant_draft.json").read_text(encoding="utf-8"))
        (root / "annotations").mkdir(parents=True)
        (root / "annotations" / "assistant_draft.json").write_text(json.dumps(source), encoding="utf-8")
        store = GroundTruthStore(root)
        drafts = DraftStore(root)
        image_id = "TST_SPARSE_002"
        drafts.load_for_human_review(store, image_id)
        entry = store.image_entry(image_id)
        assert entry["annotation_status"] == "IN_PROGRESS"
        assert entry["reviewed_by"] == "pending_human_review"
        assert len(entry["instances"]) == 1
        store.mark_complete(image_id, confirmed=True)
        assert store.image_entry(image_id)["reviewed_by"] == "human"
    finally:
        temporary.cleanup()


def complete_and_freeze(root):
    store = GroundTruthStore(root)
    for meta in store.test_images:
        store.mark_complete(meta["image_id"], confirmed=True)
    before = store.fingerprint()
    assert before == store.fingerprint()
    frozen = store.freeze()
    assert frozen == before
    return store, frozen


def test_freeze_and_review():
    temporary, root, _manifest = fixture_root()
    try:
        expect_error(RuntimeError, lambda: CandidateReviewStore(root))
        store, fingerprint = complete_and_freeze(root)
        expect_error(PermissionError, lambda: store.mark_complete(store.test_images[0]["image_id"], True))
        assert GroundTruthStore(root).fingerprint() == fingerprint

        image_id = store.test_images[0]["image_id"]
        raw_path = root / "runs" / "grounding_dino_base" / "candidates.json"
        raw_path.parent.mkdir(parents=True)
        raw = {"images": [{"image_id": image_id, "candidates": [{"id": "C001", "bbox": [1, 1, 10, 10], "confidence": 0.8, "text_label": "person"}]}]}
        raw_path.write_text(json.dumps(raw), encoding="utf-8")
        raw_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        review = CandidateReviewStore(root)
        expect_error(ValueError, lambda: review.save_review(image_id, {"candidate_id": "C001", "mapped_gt_instance_id": "MISSING", "classification": "VALID_INSTANCE", "completeness": "COMPLETE", "review_notes": "manual"}))
        expect_error(RuntimeError, lambda: review.mark_complete(image_id))
        review.save_review(image_id, {"candidate_id": "C001", "mapped_gt_instance_id": None, "classification": "FALSE_DETECTION", "completeness": "COMPLETE", "review_notes": "manual review"})
        review.mark_complete(image_id)
        assert review.review_image(image_id)["review_status"] == "COMPLETE"
        assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == raw_hash
    finally:
        temporary.cleanup()


def main():
    test_physical_isolation()
    test_geometry()
    test_store_and_validation()
    test_assistant_draft_requires_human_completion()
    test_freeze_and_review()
    print("Annotation tool tests: PASS")


if __name__ == "__main__":
    main()
