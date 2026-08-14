from collections import Counter, defaultdict

from .schema import COMPLETENESS, REVIEW_CLASSES, SCENARIOS, validate_candidates_and_reviews


def _ratio(numerator, denominator):
    return None if denominator == 0 else round(numerator / denominator, 6)


def _evaluate_subset(image_ids, gt_by_image, run_by_image, review_by_image):
    evaluable = []
    reviewed = []
    for image_id in image_ids:
        evaluable.extend(item for item in gt_by_image[image_id]["instances"] if item["evaluable"])
        reviewed.extend(review_by_image[image_id]["candidates"])
    recalled = {
        (image_id, review["mapped_gt_instance_id"])
        for image_id in image_ids
        for review in review_by_image[image_id]["candidates"]
        if review["classification"] == "VALID_INSTANCE"
    }
    recalled_count = sum((image_id, gt["instance_id"]) in recalled for image_id in image_ids for gt in gt_by_image[image_id]["instances"] if gt["evaluable"])
    classes = Counter(item["classification"] for item in reviewed)
    completeness = Counter(item["completeness"] for item in reviewed)
    non_ambiguous = len(reviewed) - classes["AMBIGUOUS"]
    recalled_keys = {
        (image_id, review["mapped_gt_instance_id"])
        for image_id in image_ids
        for review in review_by_image[image_id]["candidates"]
        if review["classification"] == "VALID_INSTANCE"
    }
    mapped_candidate_count = Counter(
        (image_id, review["mapped_gt_instance_id"])
        for image_id in image_ids
        for review in review_by_image[image_id]["candidates"]
        if review["mapped_gt_instance_id"] is not None
    )
    multiplicity_values = [mapped_candidate_count[key] for key in recalled_keys]
    return {
        "raw_candidate_count": sum(len(run_by_image[image_id]["candidates"]) for image_id in image_ids),
        "evaluable_gt_count": len(evaluable),
        "recalled_gt_count": recalled_count,
        "instance_recall": _ratio(recalled_count, len(evaluable)),
        "review_counts": {name: classes[name] for name in sorted(REVIEW_CLASSES)},
        "instance_purity": _ratio(classes["VALID_INSTANCE"], non_ambiguous),
        "completeness": {
            name: {"count": completeness[name], "rate": _ratio(completeness[name], len(reviewed))}
            for name in sorted(COMPLETENESS)
        },
        "duplicate_candidate_rate": _ratio(classes["DUPLICATE_INSTANCE"], non_ambiguous),
        "duplicate_multiplicity": _ratio(sum(multiplicity_values), len(multiplicity_values)),
        "mixed_box_rate": _ratio(classes["MIXED_INSTANCE"], non_ambiguous),
        "false_detection_rate": _ratio(classes["FALSE_DETECTION"], non_ambiguous),
        "ambiguous_count": classes["AMBIGUOUS"],
    }


def evaluate(manifest, ground_truth, runs, reviews, semantic_results=None):
    validate_candidates_and_reviews(manifest, ground_truth, runs, reviews)
    images = {item["image_id"]: item for item in manifest["images"] if item["split"] == "test"}
    gt_by_image = {item["image_id"]: item for item in ground_truth["images"]}
    run_by_image = {item["image_id"]: item for item in runs}
    review_by_image = {item["image_id"]: item for item in reviews}
    all_ids = sorted(images)
    metrics = _evaluate_subset(all_ids, gt_by_image, run_by_image, review_by_image)
    metrics["scenario_breakdown"] = {
        scenario: _evaluate_subset(
            sorted(image_id for image_id, item in images.items() if item["scenario"] == scenario),
            gt_by_image,
            run_by_image,
            review_by_image,
        )
        for scenario in sorted(SCENARIOS)
    }
    recalled = {
        (image_id, item["mapped_gt_instance_id"])
        for image_id, entry in review_by_image.items()
        for item in entry["candidates"]
        if item["classification"] == "VALID_INSTANCE"
    }
    def gt_recall(field, value):
        selected = [(image_id, gt) for image_id, entry in gt_by_image.items() for gt in entry["instances"] if gt["evaluable"] and gt[field] == value]
        return _ratio(sum((image_id, gt["instance_id"]) in recalled for image_id, gt in selected), len(selected))
    metrics["small_instance_recall"] = gt_recall("scale", "small")
    metrics["partial_visibility_recall"] = gt_recall("visibility", "partial")
    metrics["heavy_occlusion_recall"] = gt_recall("visibility", "heavily_occluded")
    metrics["iqs"] = "NOT_DEFINED_V1"
    semantic_results = semantic_results or {"images": []}
    semantic_rows = [row for image in semantic_results.get("images", []) for row in image.get("candidates", [])]
    attribution = Counter(row["attribution"] for row in semantic_rows)
    evaluated_usable = attribution["VLM_CORRECT"] + attribution["VLM_SEMANTIC_LIMIT"]
    metrics["downstream_usability"] = {
        "probe_image_count": len(semantic_results.get("images", [])),
        "evaluated_usable_candidates": evaluated_usable,
        "vlm_correct": attribution["VLM_CORRECT"],
        "vlm_incorrect": attribution["VLM_SEMANTIC_LIMIT"],
        "detector_downstream_unusable": attribution["DETECTOR_DOWNSTREAM_UNUSABLE"],
        "vlm_semantic_limit": attribution["VLM_SEMANTIC_LIMIT"],
        "not_evaluable": attribution["NOT_EVALUABLE_SEMANTIC"],
        "rate": _ratio(attribution["VLM_CORRECT"], evaluated_usable),
    }
    return metrics
