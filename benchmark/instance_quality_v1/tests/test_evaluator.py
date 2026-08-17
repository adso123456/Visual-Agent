import copy
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmark.instance_quality_v1.evaluator import evaluate
from benchmark.instance_quality_v1.schema import validate_ground_truth, validate_manifest


def fixture():
    images = []
    gt_images = []
    runs = []
    reviews = []
    scenarios = [
        "sparse_easy", "adjacent_instances", "dense_instances", "small_distant",
        "occlusion", "scale_variation", "cross_object_interference", "domain_long_tail",
    ]
    for index, scenario in enumerate(scenarios, 1):
        image_id = f"T{index}"
        images.append({
            "image_id": image_id, "split": "test", "scenario": scenario,
            "target_object": "person", "relative_path": f"assets/{image_id}.jpg",
            "width": 100, "height": 100, "sha256": f"hash{index}",
            "source": "fixture", "source_url": "https://example.invalid",
            "license": "CC0", "attribution": "fixture", "original_filename": f"{image_id}.jpg",
            "acquisition_note": "fixture",
        })
        gt_images.append({"image_id": image_id, "instances": [{
            "instance_id": "P1", "bbox": [10, 10, 50, 90], "target_object": "person",
            "visibility": "heavily_occluded" if index == 5 else "full",
            "scale": "small" if index == 4 else "medium", "crowding": "isolated",
            "semantic_visibility": "sufficient", "evaluable": True,
        }]})
        candidates = [{"id": "A", "bbox": [10, 10, 50, 90], "confidence": 0.9, "text_label": "person"}]
        runs.append({
            "image_id": image_id, "source_image_sha256": f"hash{index}",
            "source_width": 100, "source_height": 100, "candidates": candidates,
        })
        reviews.append({"image_id": image_id, "candidates": [{
            "candidate_id": "A", "mapped_gt_instance_id": "P1", "classification": "VALID_INSTANCE",
            "completeness": "COMPLETE", "review_notes": "fixture valid",
        }]})
    images.append({**images[0], "image_id": "C1", "split": "calibration", "relative_path": "assets/C1.jpg", "sha256": "calhash"})
    return {"benchmark_version": "1.0", "images": images}, {"images": gt_images}, runs, reviews


def must_fail(function):
    try:
        function()
    except ValueError:
        return
    raise AssertionError("必须拒绝非法数据")


def main():
    manifest, gt, runs, reviews = fixture()
    perfect = evaluate(manifest, gt, runs, reviews)
    assert perfect["instance_recall"] == 1 and perfect["instance_purity"] == 1
    assert perfect["small_instance_recall"] == 1 and perfect["heavy_occlusion_recall"] == 1
    assert json.dumps(perfect, sort_keys=True) == json.dumps(evaluate(manifest, gt, runs, reviews), sort_keys=True)

    changed = copy.deepcopy(reviews); changed[0]["candidates"][0]["classification"] = "PARTIAL_INSTANCE"; changed[0]["candidates"][0]["completeness"] = "UNUSABLE_PARTIAL"
    assert evaluate(manifest, gt, runs, changed)["recalled_gt_count"] == 7
    for classification in ("DUPLICATE_INSTANCE", "MIXED_INSTANCE", "FALSE_DETECTION", "AMBIGUOUS"):
        local = copy.deepcopy(reviews); local[0]["candidates"][0]["classification"] = classification
        if classification in {"FALSE_DETECTION", "MIXED_INSTANCE", "AMBIGUOUS"}: local[0]["candidates"][0]["mapped_gt_instance_id"] = None
        result = evaluate(manifest, gt, runs, local)
        assert result["review_counts"][classification] == 1

    zero_runs = copy.deepcopy(runs); zero_reviews = copy.deepcopy(reviews)
    zero_runs[0]["candidates"] = []; zero_reviews[0]["candidates"] = []
    assert evaluate(manifest, gt, zero_runs, zero_reviews)["recalled_gt_count"] == 7
    no_eval = copy.deepcopy(gt); no_eval["images"][0]["instances"][0]["evaluable"] = False
    assert evaluate(manifest, no_eval, runs, reviews)["evaluable_gt_count"] == 7

    bad = copy.deepcopy(reviews); bad[0]["candidates"][0]["mapped_gt_instance_id"] = "MISSING"
    must_fail(lambda: evaluate(manifest, gt, runs, bad))
    bad = copy.deepcopy(reviews)
    bad[0]["candidates"][0].update({
        "classification": "AMBIGUOUS", "mapped_gt_instance_id": None,
        "review_notes": "visible person is absent from frozen GT",
    })
    must_fail(lambda: evaluate(manifest, gt, runs, bad))
    bad = copy.deepcopy(manifest); bad["images"][-1]["sha256"] = bad["images"][0]["sha256"]
    must_fail(lambda: validate_manifest(bad))
    bad = copy.deepcopy(manifest); bad["images"][-1]["relative_path"] = bad["images"][0]["relative_path"]
    must_fail(lambda: validate_manifest(bad))
    bad = copy.deepcopy(gt); bad["images"][0]["instances"][0]["bbox"] = [0, 0, 0, 5]
    must_fail(lambda: validate_ground_truth(manifest, bad))
    bad = copy.deepcopy(gt); bad["images"][0]["instances"][0]["visibility"] = "invalid"
    must_fail(lambda: validate_ground_truth(manifest, bad))
    empty_gt = copy.deepcopy(gt); empty_gt["images"][0]["instances"] = []
    empty_runs = copy.deepcopy(runs); empty_runs[0]["candidates"] = []
    empty_reviews = copy.deepcopy(reviews); empty_reviews[0]["candidates"] = []
    assert evaluate(manifest, empty_gt, empty_runs, empty_reviews)["evaluable_gt_count"] == 7
    print("Instance Quality evaluator tests: PASS")


def test_ambiguous_cannot_hide_confirmed_gt_omission():
    manifest, gt, runs, reviews = fixture()
    reviews[0]["candidates"][0].update({
        "classification": "AMBIGUOUS", "mapped_gt_instance_id": None,
        "review_notes": "visible person is absent from frozen GT",
    })
    must_fail(lambda: evaluate(manifest, gt, runs, reviews))


if __name__ == "__main__":
    main()
