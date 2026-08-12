import argparse
import json
import shutil
import sys
import time
import traceback
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visual_agent.pipeline import run_pipeline


BENCHMARK_DIR = ROOT / "benchmark"
RESULTS_DIR = BENCHMARK_DIR / "results"


def load_cases() -> list[dict]:
    return json.loads((BENCHMARK_DIR / "cases.json").read_text(encoding="utf-8"))


def copy_outputs(case_id: str, image_output: Path, json_output: Path, data: dict) -> dict:
    case_dir = RESULTS_DIR / case_id
    if case_dir.exists():
        shutil.rmtree(case_dir)
    masks_dir = case_dir / "masks"
    masks_dir.mkdir(parents=True)

    image_suffix = image_output.suffix.lower()
    copied_image = case_dir / f"result{image_suffix}"
    copied_json = case_dir / "result.json"
    shutil.copy2(image_output, copied_image)
    shutil.copy2(json_output, copied_json)

    copied_masks = []
    for target in data.get("targets", []):
        segmentation = target.get("segmentation")
        if not segmentation:
            continue
        source_mask = ROOT / segmentation["mask_path"]
        copied_mask = masks_dir / source_mask.name
        shutil.copy2(source_mask, copied_mask)
        copied_masks.append(copied_mask.relative_to(ROOT).as_posix())
    return {
        "result_image": copied_image.relative_to(ROOT).as_posix(),
        "result_json": copied_json.relative_to(ROOT).as_posix(),
        "masks": copied_masks,
    }


def structural_checks(case: dict, data: dict, copied: dict, masks_before: set[Path], masks_after: set[Path]) -> dict:
    expected = case["expected"]
    image = cv2.imread(str(ROOT / case["image"]))
    checks = {
        "json_parseable": True,
        "target_object": data["plan"]["target_object"] == expected["target_object"],
        "action": data["plan"]["action"]["type"] == expected["action"],
        "target_count": expected["target_count"] is None or len(data["targets"]) == expected["target_count"],
        "segmentation_present": all("segmentation" in target for target in data["targets"]),
        "mask_files_exist": True,
        "mask_sizes_match": True,
        "masks_binary": True,
        "cutout_rgba": True,
        "cutout_alpha_matches": True,
        "negative_no_new_masks": True,
        "negative_sam_skipped": True,
    }
    loaded_masks = []
    for mask_path in copied["masks"]:
        full_path = ROOT / mask_path
        checks["mask_files_exist"] &= full_path.is_file()
        mask = cv2.imread(str(full_path), cv2.IMREAD_GRAYSCALE)
        loaded_masks.append(mask)
        checks["mask_sizes_match"] &= mask is not None and mask.shape == image.shape[:2]
        checks["masks_binary"] &= mask is not None and set(np.unique(mask)).issubset({0, 255})

    if expected["action"] == "cutout" and data["targets"]:
        result_image = cv2.imread(str(ROOT / copied["result_image"]), cv2.IMREAD_UNCHANGED)
        checks["cutout_rgba"] = result_image is not None and result_image.ndim == 3 and result_image.shape[2] == 4
        if checks["cutout_rgba"] and loaded_masks:
            combined = np.logical_or.reduce([mask > 0 for mask in loaded_masks]).astype(np.uint8) * 255
            checks["cutout_alpha_matches"] = np.array_equal(result_image[:, :, 3], combined)
        else:
            checks["cutout_alpha_matches"] = False

    if expected["target_count"] == 0:
        checks["negative_no_new_masks"] = masks_before == masks_after and not copied["masks"]
        checks["negative_sam_skipped"] = data.get("timings", {}).get("sam2") is None
    return checks


def run_case(case: dict, result_id: str | None = None) -> dict:
    result_id = result_id or case["id"]
    image_path = ROOT / case["image"]
    masks_before = set((ROOT / "images/output_images").glob("result_*_mask_*.png"))
    started_at = time.perf_counter()
    try:
        image_output, json_output = run_pipeline(image_path, case["prompt"])
        cli_seconds = time.perf_counter() - started_at
        image_output = ROOT / image_output
        json_output = ROOT / json_output
        data = json.loads(json_output.read_text(encoding="utf-8"))
        copied = copy_outputs(result_id, image_output, json_output, data)
        masks_after = set((ROOT / "images/output_images").glob("result_*_mask_*.png"))
        checks = structural_checks(case, data, copied, masks_before, masks_after)
        return {
            "id": result_id,
            "case_id": case["id"],
            "suite": case["suite"],
            "image": case["image"],
            "prompt": case["prompt"],
            "expected": case["expected"],
            "status": "success",
            "cli_total_seconds": round(cli_seconds, 3),
            "plan": data.get("plan"),
            "candidate_count": len(data.get("candidates", [])),
            "targets": data.get("targets", []),
            "timings": data.get("timings", {}),
            "checks": checks,
            "structural_pass": all(checks.values()),
            "artifacts": copied,
        }
    except Exception as error:
        return {
            "id": result_id,
            "case_id": case["id"],
            "suite": case["suite"],
            "image": case["image"],
            "prompt": case["prompt"],
            "expected": case["expected"],
            "status": "error",
            "cli_total_seconds": round(time.perf_counter() - started_at, 3),
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="运行冻结基线图片回归测试")
    parser.add_argument("--case", action="append", dest="case_ids", help="只运行指定 case，可重复传入")
    parser.add_argument("--suite", choices=["core", "challenge"], help="只运行指定 suite")
    parser.add_argument("--output", default="raw_results.json", help="汇总结果文件名")
    args = parser.parse_args()

    cases = load_cases()
    if args.case_ids:
        cases = [case for case in cases if case["id"] in set(args.case_ids)]
    if args.suite:
        cases = [case for case in cases if case["suite"] == args.suite]

    results = []
    for index, case in enumerate(cases, 1):
        print(f"[{index}/{len(cases)}] {case['id']} {case['prompt']}", flush=True)
        result = run_case(case)
        results.append(result)
        print(
            f"  {result['status']} {result['cli_total_seconds']}s "
            f"targets={len(result.get('targets', []))}",
            flush=True,
        )
        (BENCHMARK_DIR / args.output).write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
