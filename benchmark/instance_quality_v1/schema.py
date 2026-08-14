import hashlib
import math
from collections import Counter
from pathlib import Path

from PIL import Image


SCENARIOS = {
    "sparse_easy",
    "adjacent_instances",
    "dense_instances",
    "small_distant",
    "occlusion",
    "scale_variation",
    "cross_object_interference",
    "domain_long_tail",
}
SPLITS = {"calibration", "test"}
VISIBILITY = {"full", "partial", "heavily_occluded"}
SCALES = {"large", "medium", "small"}
CROWDING = {"isolated", "adjacent", "dense"}
SEMANTIC_VISIBILITY = {"sufficient", "insufficient"}
REVIEW_CLASSES = {
    "VALID_INSTANCE",
    "PARTIAL_INSTANCE",
    "DUPLICATE_INSTANCE",
    "MIXED_INSTANCE",
    "FALSE_DETECTION",
    "AMBIGUOUS",
}
COMPLETENESS = {"COMPLETE", "USABLE_PARTIAL", "UNUSABLE_PARTIAL"}


def _object(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name}必须是object")


def _string(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}必须是非空字符串")


def validate_bbox(box, width, height, name="bbox"):
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError(f"{name}必须是四元素数组")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box):
        raise ValueError(f"{name}坐标非法")
    if not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
        raise ValueError(f"{name}超界或面积非正")


def validate_manifest(manifest):
    _object(manifest, "manifest")
    if manifest.get("benchmark_version") != "1.0":
        raise ValueError("benchmark_version必须为1.0")
    images = manifest.get("images")
    if not isinstance(images, list):
        raise ValueError("images必须是数组")
    ids, paths, split_hashes = set(), set(), {"calibration": set(), "test": set()}
    for item in images:
        _object(item, "image")
        required = {
            "image_id", "split", "scenario", "target_object", "relative_path",
            "width", "height", "sha256", "source", "source_url", "license",
            "attribution", "original_filename", "acquisition_note",
        }
        if not required <= set(item):
            raise ValueError(f"image缺字段：{sorted(required - set(item))}")
        for key in required - {"width", "height"}:
            _string(item[key], key)
        if item["image_id"] in ids:
            raise ValueError("image_id重复")
        ids.add(item["image_id"])
        if item["relative_path"] in paths:
            raise ValueError("relative_path重复")
        paths.add(item["relative_path"])
        if item["split"] not in SPLITS or item["scenario"] not in SCENARIOS:
            raise ValueError("split或scenario无效")
        if not isinstance(item["width"], int) or not isinstance(item["height"], int) or min(item["width"], item["height"]) <= 0:
            raise ValueError("图片尺寸无效")
        other = "test" if item["split"] == "calibration" else "calibration"
        if item["sha256"] in split_hashes[other]:
            raise ValueError("Calibration/Test SHA重复")
        split_hashes[item["split"]].add(item["sha256"])
    return images


def validate_ground_truth(manifest, ground_truth):
    images = {item["image_id"]: item for item in validate_manifest(manifest)}
    _object(ground_truth, "ground_truth")
    entries = ground_truth.get("images")
    if not isinstance(entries, list):
        raise ValueError("GT images必须是数组")
    seen_images = set()
    for entry in entries:
        image_id = entry.get("image_id")
        if image_id in seen_images or image_id not in images:
            raise ValueError("GT image_id重复或不存在")
        seen_images.add(image_id)
        image = images[image_id]
        if image["split"] != "test":
            raise ValueError("Calibration不得包含GT")
        instances = entry.get("instances")
        if not isinstance(instances, list):
            raise ValueError("instances必须是数组")
        instance_ids = set()
        for instance in instances:
            required = {"instance_id", "bbox", "target_object", "visibility", "scale", "crowding", "semantic_visibility", "evaluable"}
            if not required <= set(instance):
                raise ValueError("GT instance缺字段")
            _string(instance["instance_id"], "instance_id")
            if instance["instance_id"] in instance_ids:
                raise ValueError("GT instance_id重复")
            instance_ids.add(instance["instance_id"])
            validate_bbox(instance["bbox"], image["width"], image["height"])
            if instance["target_object"] != image["target_object"]:
                raise ValueError("GT target_object与manifest不一致")
            if instance["visibility"] not in VISIBILITY or instance["scale"] not in SCALES or instance["crowding"] not in CROWDING or instance["semantic_visibility"] not in SEMANTIC_VISIBILITY:
                raise ValueError("GT enum无效")
            if not isinstance(instance["evaluable"], bool):
                raise ValueError("evaluable必须是bool")
    expected = {item["image_id"] for item in images.values() if item["split"] == "test"}
    if seen_images != expected:
        raise ValueError("Test图片GT不完整")
    return entries


def validate_candidates_and_reviews(manifest, ground_truth, runs, reviews):
    gt_entries = {item["image_id"]: item for item in validate_ground_truth(manifest, ground_truth)}
    if not isinstance(runs, list) or not isinstance(reviews, list):
        raise ValueError("runs/reviews必须是数组")
    runs_by_image = {item.get("image_id"): item for item in runs}
    reviews_by_image = {item.get("image_id"): item for item in reviews}
    if set(runs_by_image) != set(gt_entries) or set(reviews_by_image) != set(gt_entries):
        raise ValueError("run/review图片不完整")
    for image_id, run in runs_by_image.items():
        candidates = run.get("candidates")
        image_reviews = reviews_by_image[image_id].get("candidates")
        if not isinstance(candidates, list) or not isinstance(image_reviews, list):
            raise ValueError("candidate/review必须是数组")
        candidate_ids = [item.get("id") for item in candidates]
        review_ids = [item.get("candidate_id") for item in image_reviews]
        if len(candidate_ids) != len(set(candidate_ids)) or Counter(candidate_ids) != Counter(review_ids):
            raise ValueError("candidate review不完整或重复")
        gt_ids = {item["instance_id"] for item in gt_entries[image_id]["instances"]}
        image = next(item for item in manifest["images"] if item["image_id"] == image_id)
        for candidate in candidates:
            _string(candidate.get("id"), "candidate id")
            validate_bbox(candidate.get("bbox"), image["width"], image["height"], "candidate bbox")
            confidence = candidate.get("confidence")
            if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                raise ValueError("candidate confidence必须位于[0,1]")
        for review in image_reviews:
            if review.get("classification") not in REVIEW_CLASSES or review.get("completeness") not in COMPLETENESS:
                raise ValueError("review enum无效")
            mapped = review.get("mapped_gt_instance_id")
            if mapped is not None and mapped not in gt_ids:
                raise ValueError("candidate指向不存在GT")
            if review["classification"] in {"VALID_INSTANCE", "PARTIAL_INSTANCE", "DUPLICATE_INSTANCE"} and mapped is None:
                raise ValueError("实例类review必须映射GT")
            _string(review.get("review_notes"), "review_notes")


def scenario_counts(manifest):
    return Counter(item["scenario"] for item in validate_manifest(manifest) if item["split"] == "test")


def _average_hash(path):
    image = Image.open(path).convert("L").resize((8, 8), Image.Resampling.LANCZOS)
    pixels = list(image.getdata())
    average = sum(pixels) / len(pixels)
    return sum((value >= average) << index for index, value in enumerate(pixels))


def validate_release_manifest(manifest, benchmark_root):
    """校验正式 v1.0 资产规模、来源、文件指纹与 split 隔离。"""
    images = validate_manifest(manifest)
    test = [item for item in images if item["split"] == "test"]
    calibration = [item for item in images if item["split"] == "calibration"]
    if len(test) < 24:
        raise ValueError("正式 Test Set 不得少于24张")
    if not 5 <= len(calibration) <= 10:
        raise ValueError("Calibration Set 必须为5至10张")
    counts = Counter(item["scenario"] for item in test)
    if set(counts) != SCENARIOS or any(counts[name] < 3 for name in SCENARIOS):
        raise ValueError("Test Set 必须完整覆盖8类场景且每类至少3张")
    targets = {item["target_object"] for item in test}
    if "person" not in targets or len(targets - {"person"}) < 3:
        raise ValueError("Test Set 必须包含person及至少3类其它基础实体")

    root = Path(benchmark_root)
    hashes = {"calibration": [], "test": []}
    for item in images:
        path = root / item["relative_path"]
        if not path.is_file():
            raise ValueError(f"图片不存在：{item['relative_path']}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"SHA256不一致：{item['image_id']}")
        with Image.open(path) as image:
            if image.size != (item["width"], item["height"]):
                raise ValueError(f"图片尺寸不一致：{item['image_id']}")
        hashes[item["split"]].append((item["image_id"], _average_hash(path)))
    near_duplicates = []
    for left_id, left_hash in hashes["calibration"]:
        for right_id, right_hash in hashes["test"]:
            distance = (left_hash ^ right_hash).bit_count()
            if distance <= 4:
                near_duplicates.append({"calibration": left_id, "test": right_id, "hamming": distance})
    if near_duplicates:
        raise ValueError(f"Calibration/Test疑似感知重复：{near_duplicates}")
    return {"test_count": len(test), "calibration_count": len(calibration), "scenario_counts": dict(counts), "targets": sorted(targets)}
