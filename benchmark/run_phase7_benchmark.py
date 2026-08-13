import argparse
import json

import cv2
import numpy as np

import run_benchmark as baseline


PHASE7_RESULTS_DIR = baseline.BENCHMARK_DIR / "phase7_results"


def phase7_checks(case: dict, data: dict, copied: dict) -> dict:
    checks = {
        "related_objects_present": isinstance(data["plan"].get("related_objects"), list),
        "result_layers_present": all(
            key in data
            for key in [
                "verified_subjects",
                "relation_candidates",
                "relation_bindings",
                "semantic_groups",
                "targets",
            ]
        ),
        "targets_complete": all(
            any(group["id"] == target["id"] and group["composite_complete"] for group in data["semantic_groups"])
            for target in data["targets"]
        ),
        "bbox_contract": all(target["bbox"] != [] and target["composite_bbox"] != [] for target in data["targets"]),
        "components_present": all(bool(target.get("components")) for target in data["targets"]),
        "composite_score_min": all(
            abs(target["segmentation"]["mask_score"] - min(item["mask_score"] for item in target["components"])) < 1e-4
            for target in data["targets"]
        ),
    }
    if case["id"] in {"core_003", "core_004"}:
        target = data["targets"][0] if data["targets"] else None
        checks["relation_gate"] = bool(
            target
            and data["plan"]["related_objects"]
            == [{"object": "umbrella", "relation": "held_by_target"}]
            and len(data["verified_subjects"]) == 1
            and len(data["relation_candidates"]) >= 1
            and any(item["status"] == "satisfied" for item in data["relation_bindings"])
            and {item["role"] for item in target["components"]} == {"subject", "related"}
        )
    if case["id"] == "core_004" and data["targets"]:
        result_image = cv2.imread(str(baseline.ROOT / copied["result_image"]), cv2.IMREAD_UNCHANGED)
        mask = cv2.imread(str(baseline.ROOT / copied["masks"][0]), cv2.IMREAD_GRAYSCALE)
        checks["cutout_composite_alpha"] = bool(
            result_image is not None
            and result_image.ndim == 3
            and result_image.shape[2] == 4
            and mask is not None
            and np.array_equal(result_image[:, :, 3], mask)
        )
    if case["id"] == "core_014":
        checks["zero_subject_relation_skipped"] = bool(
            not data["verified_subjects"]
            and not data["relation_candidates"]
            and not data["relation_bindings"]
            and not data["semantic_groups"]
            and not data["targets"]
            and data["timings"]["relation_grounding_seconds"] == 0.0
            and data["timings"]["relation_verification_seconds"] == 0.0
        )
    return checks


def run_phase7_case(case: dict, result_id: str | None = None) -> dict:
    result = baseline.run_case(case, result_id)
    if result.get("status") == "success":
        data = json.loads(
            (baseline.ROOT / result["artifacts"]["result_json"]).read_text(encoding="utf-8")
        )
        result["agent"] = data["agent"]
        result["agent_response"] = data["agent_response"]
        result["verified_subjects"] = data["verified_subjects"]
        result["relation_candidates"] = data["relation_candidates"]
        result["relation_bindings"] = data["relation_bindings"]
        result["semantic_groups"] = data["semantic_groups"]
        result["phase7_checks"] = phase7_checks(case, data, result["artifacts"])
        result["phase7_structural_pass"] = all(result["phase7_checks"].values())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 Phase 7 关系组合目标图片回归测试")
    parser.add_argument("--case", action="append", dest="case_ids", help="只运行指定 case，可重复传入")
    parser.add_argument("--suite", choices=["core", "challenge"], help="只运行指定 suite")
    args = parser.parse_args()
    baseline.RESULTS_DIR = PHASE7_RESULTS_DIR
    cases = baseline.load_cases()
    if args.case_ids:
        cases = [case for case in cases if case["id"] in set(args.case_ids)]
    if args.suite:
        cases = [case for case in cases if case["suite"] == args.suite]
    results = []
    for index, case in enumerate(cases, 1):
        print(f"[{index}/{len(cases)}] {case['id']} {case['prompt']}", flush=True)
        result = run_phase7_case(case)
        results.append(result)
        print(
            f"  {result['status']} {result['cli_total_seconds']}s "
            f"targets={len(result.get('targets', []))}",
            flush=True,
        )
        (baseline.BENCHMARK_DIR / "phase7_raw_results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
