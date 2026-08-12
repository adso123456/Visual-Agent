import json
import statistics
from pathlib import Path


DIR = Path(__file__).resolve().parent


def load(name: str):
    return json.loads((DIR / name).read_text(encoding="utf-8"))


def timing(values: list[float]) -> dict:
    return {
        "min": round(min(values), 3),
        "median": round(statistics.median(values), 3),
        "max": round(max(values), 3),
    }


def main() -> None:
    phase5 = load("report.json")
    cases = {case["id"]: case for case in load("cases.json")}
    results = {item["case_id"]: item for item in load("phase6_raw_results.json")}
    repeats = load("phase6_repeatability_raw.json")
    reviews = {item["id"]: item for item in load("phase6_manual_reviews.json")}
    core_ids = [case_id for case_id, case in cases.items() if case["suite"] == "core"]
    expected_constraints = {
        case_id: cases[case_id]["expected"]["constraints_semantics"] for case_id in core_ids
    }

    target_object_correct = sum(
        results[case_id]["plan"]["target_object"] == cases[case_id]["expected"]["target_object"]
        for case_id in core_ids
    )
    action_correct = sum(
        results[case_id]["plan"]["action"]["type"] == cases[case_id]["expected"]["action"]
        for case_id in core_ids
    )
    constraints_correct = sum(
        results[case_id]["plan"]["constraints"] == expected_constraints[case_id]
        for case_id in core_ids
    )
    target_selection = sum(reviews[case_id]["target_selection"] is True for case_id in core_ids)
    negative_ids = [case_id for case_id in core_ids if cases[case_id]["expected"]["target_count"] == 0]
    negative_pass = sum(reviews[case_id]["result"] == "PASS" for case_id in negative_ids)
    segmented_ids = [case_id for case_id in core_ids if results[case_id]["targets"]]
    segmentation_pass = sum(reviews[case_id]["segmentation"] is True for case_id in segmented_ids)
    action_pass = sum(reviews[case_id]["action"] is True for case_id in core_ids)
    core_pass = sum(reviews[case_id]["result"] == "PASS" for case_id in core_ids)
    retries = sum(item["agent"]["plan_attempts"] - 1 for item in results.values())

    repeatability = {}
    for case_id in ["core_006", "core_011", "core_012"]:
        group = [item for item in repeats if item["case_id"] == case_id]
        signatures = [
            {
                "plan": item["plan"],
                "target_count": len(item["targets"]),
                "mask_areas": [target.get("segmentation", {}).get("mask_area_pixels") for target in item["targets"]],
                "mask_scores": [target.get("segmentation", {}).get("mask_score") for target in item["targets"]],
            }
            for item in group
        ]
        repeatability[case_id] = {
            "runs": len(group),
            "consistent": all(signature == signatures[0] for signature in signatures),
            "signatures": signatures,
        }

    p6 = {
        "model": "deepseek-v4-flash",
        "core": {
            "passed_cases": core_pass,
            "total_cases": len(core_ids),
            "end_to_end_pass_rate": core_pass / len(core_ids),
        },
        "metrics": {
            "target_object_accuracy": round(target_object_correct / len(core_ids), 4),
            "action_accuracy": round(action_correct / len(core_ids), 4),
            "constraint_semantic_accuracy": round(constraints_correct / len(core_ids), 4),
            "target_selection_exact_match_rate": round(target_selection / len(core_ids), 4),
            "negative_case_pass_rate": round(negative_pass / len(negative_ids), 4),
            "segmentation_visual_pass_rate": round(segmentation_pass / len(segmented_ids), 4),
            "action_visual_pass_rate": round(action_pass / len(core_ids), 4),
        },
        "planner_contract_retries": retries,
        "repeatability": repeatability,
        "performance_seconds": {
            key: timing([item["timings"][key] for item in results.values()])
            for key in ["deepseek_plan_seconds", "deepseek_final_response_seconds"]
        },
        "focus_cases": {
            "core_004": "PLAN 已修复；E2E 仍因 SAM 人体 mask 不包含雨伞而失败。",
            "core_015": "PLAN 已修复，target_object=person、constraints=[儿童]，两名儿童均正确模糊。",
            "challenge_005": "仍只产生并保留 3 个前景红衣目标，密集小目标召回问题仍属 GROUNDING。",
        },
    }
    report = {"phase5": phase5, "phase6": p6}
    (DIR / "phase6_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    rows = [
        ("Core pass", phase5["core"]["end_to_end_pass_rate"], p6["core"]["end_to_end_pass_rate"]),
        ("target_object", phase5["metrics"]["target_object_accuracy"], p6["metrics"]["target_object_accuracy"]),
        ("constraints", phase5["metrics"]["constraint_semantic_accuracy"], p6["metrics"]["constraint_semantic_accuracy"]),
        ("action", phase5["metrics"]["action_accuracy"], p6["metrics"]["action_accuracy"]),
        ("target selection", phase5["metrics"]["target_selection_exact_match_rate"], p6["metrics"]["target_selection_exact_match_rate"]),
        ("negative", phase5["metrics"]["negative_case_pass_rate"], p6["metrics"]["negative_case_pass_rate"]),
        ("segmentation", phase5["metrics"]["segmentation_visual_pass_rate"], p6["metrics"]["segmentation_visual_pass_rate"]),
        ("action visual", phase5["metrics"]["action_visual_pass_rate"], p6["metrics"]["action_visual_pass_rate"]),
    ]
    lines = [
        "# Phase 6 DeepSeek Agent Brain 对照报告", "",
        "- 模型：`deepseek-v4-flash`", "- 数据集：与 Phase 5 完全相同的 15 Core + 5 Challenge", "",
        "| Metric | Phase 5 | Phase 6 | Delta |", "|---|---:|---:|---:|",
    ]
    lines.extend(
        f"| {name} | {p5:.2%} | {p6_value:.2%} | {p6_value - p5:+.2%} |"
        for name, p5, p6_value in rows
    )
    lines.extend([
        "", "## 重点结果", "",
        f"- core_004：{p6['focus_cases']['core_004']}",
        f"- core_015：{p6['focus_cases']['core_015']}",
        f"- challenge_005：{p6['focus_cases']['challenge_005']}",
        "", "## Repeatability", "",
    ])
    lines.extend(
        f"- `{case_id}`：{item['runs']} 次，{'完全一致' if item['consistent'] else '存在波动'}"
        for case_id, item in repeatability.items()
    )
    lines.extend([
        "", "## Agent 统计", "",
        f"- Planner contract retry：{retries}/20",
        f"- DeepSeek plan latency：{p6['performance_seconds']['deepseek_plan_seconds']}",
        f"- DeepSeek final latency：{p6['performance_seconds']['deepseek_final_response_seconds']}",
        "", "Phase 5 原始产物未覆盖；DINO、Qwen verifier、SAM2 和 Action 实现均未修改。", "",
    ])
    (DIR / "phase6_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
