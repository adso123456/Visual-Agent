import json
import math
import statistics
from collections import Counter
from pathlib import Path


DIR = Path(__file__).resolve().parent
STAGES = [
    "PLAN", "GROUNDING", "VERIFICATION", "SEGMENTATION", "ACTION",
    "NEGATIVE_HANDLING", "RUNTIME", "INFRASTRUCTURE",
]


def load(name: str):
    return json.loads((DIR / name).read_text(encoding="utf-8"))


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return round(values[lower], 3)
    return round(values[lower] * (upper - index) + values[upper] * (index - lower), 3)


def stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "min": None, "median": None, "max": None, "p95": None}
    return {
        "count": len(values),
        "min": round(min(values), 3),
        "median": round(statistics.median(values), 3),
        "max": round(max(values), 3),
        "p95": percentile(values, 0.95),
    }


def main() -> None:
    cases = {item["id"]: item for item in load("cases.json")}
    results = {item["case_id"]: item for item in load("combined_results.json")}
    reviews = {item["id"]: item for item in load("manual_reviews.json")}
    repeats = load("repeatability_raw.json")
    preflight = load("unicode_path_preflight.json")

    core_ids = [case_id for case_id, case in cases.items() if case["suite"] == "core"]
    challenge_ids = [case_id for case_id, case in cases.items() if case["suite"] == "challenge"]
    core_passed = [case_id for case_id in core_ids if reviews[case_id]["result"] == "PASS"]
    failures = []
    for case_id in core_ids + challenge_ids:
        review = reviews[case_id]
        if review["result"] != "FAIL":
            continue
        result = results[case_id]
        failures.append({
            "id": case_id,
            "suite": cases[case_id]["suite"],
            "image": cases[case_id]["image"],
            "prompt": cases[case_id]["prompt"],
            "expected": cases[case_id]["expected"],
            "actual": {
                "plan": result.get("plan"),
                "candidate_count": result.get("candidate_count"),
                "target_count": len(result.get("targets", [])),
            },
            "primary_failure_stage": review["primary_failure_stage"],
            "secondary_issues": review["secondary_issues"],
            "evidence": review["evidence"],
        })

    target_object_correct = sum(
        results[case_id]["plan"]["target_object"] == cases[case_id]["expected"]["target_object"]
        for case_id in core_ids
    )
    action_correct = sum(
        results[case_id]["plan"]["action"]["type"] == cases[case_id]["expected"]["action"]
        for case_id in core_ids
    )
    constraints_correct = sum(case_id not in {"core_004", "core_015"} for case_id in core_ids)
    selection_correct = sum(reviews[case_id]["target_selection"] is True for case_id in core_ids)
    negative_ids = [case_id for case_id in core_ids if cases[case_id]["expected"]["target_count"] == 0]
    negative_pass = sum(reviews[case_id]["result"] == "PASS" for case_id in negative_ids)
    segmented_ids = [case_id for case_id in core_ids if results[case_id].get("targets")]
    segmentation_pass = sum(reviews[case_id]["segmentation"] is True for case_id in segmented_ids)
    action_pass = sum(reviews[case_id]["action"] is True for case_id in core_ids)

    breakdown = Counter(review["primary_failure_stage"] for review in reviews.values() if review["primary_failure_stage"])
    unicode_errors = [item for item in preflight if item.get("status") == "error"]
    failure_breakdown = {stage: breakdown.get(stage, 0) for stage in STAGES}
    failure_breakdown["RUNTIME"] += len(unicode_errors)

    timing_keys = {
        "qwen_plan_seconds": lambda item: item.get("timings", {}).get("qwen_plan_seconds"),
        "grounding_dino_seconds": lambda item: item.get("timings", {}).get("grounding_dino_seconds"),
        "group_verification_seconds": lambda item: item.get("timings", {}).get("group_verification_seconds"),
        "sam2_load_seconds": lambda item: (item.get("timings", {}).get("sam2") or {}).get("load_seconds"),
        "sam2_inference_seconds": lambda item: (item.get("timings", {}).get("sam2") or {}).get("inference_seconds"),
        "cli_total_seconds": lambda item: item.get("cli_total_seconds"),
    }
    performance = {}
    formal_results = [results[case_id] for case_id in core_ids + challenge_ids]
    for key, getter in timing_keys.items():
        values = [value for item in formal_results if (value := getter(item)) is not None]
        performance[key] = stats(values)

    repeatability = {}
    for case_id in ["core_006", "core_011", "core_012"]:
        group = [item for item in repeats if item["case_id"] == case_id]
        signatures = []
        for item in group:
            signatures.append({
                "plan": item.get("plan"),
                "target_ids": [target["id"] for target in item.get("targets", [])],
                "target_count": len(item.get("targets", [])),
                "mask_areas": [target.get("segmentation", {}).get("mask_area_pixels") for target in item.get("targets", [])],
                "mask_scores": [target.get("segmentation", {}).get("mask_score") for target in item.get("targets", [])],
            })
        repeatability[case_id] = {
            "runs": len(group),
            "consistent": all(signature == signatures[0] for signature in signatures),
            "signatures": signatures,
        }

    report = {
        "baseline_sha": "ead6c49912de4e168398386dfb6ce8b1a3d18b44",
        "dataset": {
            "core_cases": len(core_ids),
            "challenge_cases": len(challenge_ids),
            "different_images": len({case["image"] for case in cases.values()}),
            "negative_core_cases": len(negative_ids),
            "action_coverage_core": dict(Counter(cases[case_id]["expected"]["action"] for case_id in core_ids)),
        },
        "core": {
            "passed_cases": len(core_passed),
            "failed_cases": len(core_ids) - len(core_passed),
            "total_cases": len(core_ids),
            "end_to_end_pass_rate": round(len(core_passed) / len(core_ids), 4),
        },
        "metrics": {
            "target_object_accuracy": round(target_object_correct / len(core_ids), 4),
            "action_accuracy": round(action_correct / len(core_ids), 4),
            "constraint_semantic_accuracy": round(constraints_correct / len(core_ids), 4),
            "target_selection_exact_match_rate": round(selection_correct / len(core_ids), 4),
            "negative_case_pass_rate": round(negative_pass / len(negative_ids), 4),
            "segmentation_visual_pass_rate": round(segmentation_pass / len(segmented_ids), 4),
            "segmentation_cases": len(segmented_ids),
            "action_visual_pass_rate": round(action_pass / len(core_ids), 4),
            "runtime_failure_count_formal_ascii_cases": sum(results[case_id]["status"] == "error" for case_id in core_ids + challenge_ids),
            "runtime_failure_count_including_unicode_preflight": len(unicode_errors),
        },
        "failure_breakdown": failure_breakdown,
        "failures": failures,
        "constraint_redundancy": {
            "found": True,
            "cases": ["core_004"],
            "evidence": "core_004 返回 constraints=[手持雨伞, 人]；同图钓鱼六种 action 均稳定返回 [正在钓鱼]，未出现冗余人。",
        },
        "challenge": [
            {"id": case_id, "result": reviews[case_id]["result"], "evidence": reviews[case_id]["evidence"], "secondary_issues": reviews[case_id]["secondary_issues"]}
            for case_id in challenge_ids
        ],
        "repeatability": repeatability,
        "performance_seconds": performance,
        "known_runtime_issue": {
            "windows_unicode_path": {
                "events": len(unicode_errors),
                "stage": "RUNTIME",
                "evidence": "冻结基线 renderer 的 cv2.imread(str(path)) 在本机 Windows 无法读取中文路径；同字节 ASCII 文件名副本全部运行成功。",
                "raw_record": "benchmark/unicode_path_preflight.json",
            }
        },
        "reliable_capabilities": [
            "清晰单目标基础实体定位、分割与五种 action",
            "清晰行为语义在不同 action 句式间保持目标一致",
            "多目标属性选择并同时生成多个 mask/action",
            "明显不存在目标时不调用 SAM、不生成 mask",
            "代表性行为/属性/negative case 三次重复结果完全一致",
        ],
        "weak_capabilities": [
            "Plan 在部分关系+cutout 句式中会生成复合 target_object 和冗余实体 constraint",
            "儿童类别可能绕过人物统一 person 规划契约",
            "关系目标 cutout 的人物 mask 不包含关联工具（如雨伞）",
            "密集、小尺寸、遮挡目标的 Grounding 召回不足",
            "Windows 中文图片路径会在正式 renderer 阶段失败",
        ],
        "blocker": False,
        "production_code_modified": False,
    }
    (DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Phase 5 图片回归测试报告", "",
        f"- 冻结基线：`{report['baseline_sha']}`",
        f"- Core：{report['core']['passed_cases']}/{report['core']['total_cases']}，通过率 {report['core']['end_to_end_pass_rate']:.2%}",
        f"- Challenge：{len(challenge_ids)} 个，单独报告，不计入 Core 通过率",
        f"- 不同图片：{report['dataset']['different_images']} 张",
        f"- 正式业务代码修改：否", "",
        "## Core 指标", "",
        f"- target_object accuracy：{report['metrics']['target_object_accuracy']:.2%}",
        f"- action accuracy：{report['metrics']['action_accuracy']:.2%}",
        f"- constraint semantic accuracy：{report['metrics']['constraint_semantic_accuracy']:.2%}",
        f"- target selection exact match：{report['metrics']['target_selection_exact_match_rate']:.2%}",
        f"- negative pass：{report['metrics']['negative_case_pass_rate']:.2%}",
        f"- segmentation visual pass：{report['metrics']['segmentation_visual_pass_rate']:.2%}（{report['metrics']['segmentation_cases']} 个进入 SAM 的 Core）",
        f"- action visual pass：{report['metrics']['action_visual_pass_rate']:.2%}", "",
        "## Core 失败", "",
    ]
    for failure in failures:
        if failure["suite"] != "core":
            continue
        lines.extend([
            f"### {failure['id']} — {failure['primary_failure_stage']}", "",
            f"- 图片：`{failure['image']}`",
            f"- Prompt：{failure['prompt']}",
            f"- Expected：`{json.dumps(failure['expected'], ensure_ascii=False)}`",
            f"- Actual：`{json.dumps(failure['actual'], ensure_ascii=False)}`",
            f"- 证据：{failure['evidence']}",
            f"- 次要问题：{'; '.join(failure['secondary_issues']) if failure['secondary_issues'] else '无'}", "",
        ])
    lines.extend(["## Challenge", ""])
    for item in report["challenge"]:
        lines.append(f"- **{item['id']} — {item['result']}**：{item['evidence']}")
    lines.extend(["", "## Constraints 冗余", "", report["constraint_redundancy"]["evidence"], "", "## Repeatability", ""])
    for case_id, item in repeatability.items():
        lines.append(f"- `{case_id}`：3 次，{'完全一致' if item['consistent'] else '存在波动'}")
    lines.extend(["", "## 性能（秒）", "", "| 阶段 | count | min | median | max | p95 |", "|---|---:|---:|---:|---:|---:|"])
    for key, value in performance.items():
        lines.append(f"| {key} | {value['count']} | {value['min']} | {value['median']} | {value['max']} | {value['p95']} |")
    lines.extend([
        "", "> Grounding DINO timing 按当前 pipeline 口径统计，包含模型初始化/加载，不是纯 inference。", "",
        "## 已知 Runtime 问题", "",
        f"中文路径预检记录到 {len(unicode_errors)} 次 renderer 失败；同字节 ASCII 副本全部成功。未修改正式代码。", "",
        "## 结论", "",
        "最可靠：清晰目标、清晰行为/属性、多目标 action、negative handling、重复稳定性。", "",
        "最薄弱：Plan 复合实体/冗余约束、关系物体随主体抠出、密集小目标召回、Windows 中文路径。", "",
        "本阶段无外部 blocker；benchmark 目标已完成。",
    ])
    (DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
