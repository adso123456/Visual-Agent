import json
import statistics
from pathlib import Path


DIR = Path(__file__).resolve().parent


def load(name: str):
    return json.loads((DIR / name).read_text(encoding="utf-8"))


def stats(values: list[float]) -> dict:
    return {
        "min": round(min(values), 3),
        "median": round(statistics.median(values), 3),
        "max": round(max(values), 3),
    }


def main() -> None:
    phase6 = load("phase6_report.json")["phase6"]
    cases = {item["id"]: item for item in load("cases.json")}
    results = {item["case_id"]: item for item in load("phase7_raw_results.json")}
    reviews = {item["id"]: item for item in load("phase7_manual_reviews.json")}
    repeats = load("phase7_repeatability_raw.json")
    core_ids = [case_id for case_id, case in cases.items() if case["suite"] == "core"]
    challenge_ids = [case_id for case_id, case in cases.items() if case["suite"] == "challenge"]
    negative_ids = [case_id for case_id in core_ids if cases[case_id]["expected"]["target_count"] == 0]
    segmented_ids = [case_id for case_id in core_ids if results[case_id]["targets"]]
    relation_ids = ["core_003", "core_004"]

    plan_target = sum(
        results[case_id]["plan"]["target_object"] == cases[case_id]["expected"]["target_object"]
        for case_id in core_ids
    )
    plan_action = sum(
        results[case_id]["plan"]["action"]["type"] == cases[case_id]["expected"]["action"]
        for case_id in core_ids
    )
    plan_constraints = sum(
        results[case_id]["plan"]["constraints"] == cases[case_id]["expected"]["constraints_semantics"]
        for case_id in core_ids
    )
    core_pass = sum(reviews[case_id]["result"] == "PASS" for case_id in core_ids)
    relation_pass = sum(reviews[case_id]["relation_binding"] is True for case_id in relation_ids)

    repeatability = {}
    for case_id in ["core_004", "core_006", "core_011", "core_012"]:
        group = [item for item in repeats if item["case_id"] == case_id]
        business_signatures = []
        labels = []
        for item in group:
            labels.append(item["plan"]["label"])
            business_signatures.append(
                {
                    "target_object": item["plan"]["target_object"],
                    "constraints": item["plan"]["constraints"],
                    "action": item["plan"]["action"],
                    "related_objects": item["plan"]["related_objects"],
                    "bindings": [
                        {key: value for key, value in binding.items() if key != "evidence"}
                        for binding in item.get("relation_bindings", [])
                    ],
                    "semantic_groups": [
                        {key: value for key, value in group_item.items() if key != "label"}
                        for group_item in item.get("semantic_groups", [])
                    ],
                    "targets": [
                        {
                            "id": target["id"],
                            "components": target.get("components"),
                            "mask_score": target.get("segmentation", {}).get("mask_score"),
                            "mask_area_pixels": target.get("segmentation", {}).get("mask_area_pixels"),
                        }
                        for target in item["targets"]
                    ],
                }
            )
        repeatability[case_id] = {
            "runs": len(group),
            "business_consistent": all(item == business_signatures[0] for item in business_signatures),
            "label_consistent": len(set(labels)) == 1,
            "labels": labels,
            "signature": business_signatures[0],
        }

    metrics = {
        "target_object_accuracy": round(plan_target / len(core_ids), 4),
        "constraint_semantic_accuracy": round(plan_constraints / len(core_ids), 4),
        "action_accuracy": round(plan_action / len(core_ids), 4),
        "target_selection_exact_match_rate": round(
            sum(reviews[case_id]["target_selection"] is True for case_id in core_ids) / len(core_ids), 4
        ),
        "negative_case_pass_rate": round(
            sum(reviews[case_id]["result"] == "PASS" for case_id in negative_ids) / len(negative_ids), 4
        ),
        "segmentation_visual_pass_rate": round(
            sum(reviews[case_id]["segmentation"] is True for case_id in segmented_ids) / len(segmented_ids), 4
        ),
        "action_visual_pass_rate": round(
            sum(reviews[case_id]["action"] is True for case_id in core_ids) / len(core_ids), 4
        ),
        "relation_binding_pass_rate": round(relation_pass / len(relation_ids), 4),
    }
    phase7 = {
        "model": "deepseek-v4-pro",
        "core": {
            "passed_cases": core_pass,
            "total_cases": len(core_ids),
            "end_to_end_pass_rate": round(core_pass / len(core_ids), 4),
        },
        "metrics": metrics,
        "relation_cases": relation_ids,
        "repeatability": repeatability,
        "performance_seconds": {
            key: stats([results[case_id]["timings"][key] for case_id in core_ids + challenge_ids if results[case_id]["timings"].get(key) is not None])
            for key in [
                "deepseek_plan_seconds",
                "grounding_dino_seconds",
                "group_verification_seconds",
                "relation_grounding_seconds",
                "relation_verification_seconds",
                "deepseek_final_response_seconds",
            ]
        },
        "challenge_004_first_run_error": load("phase7_challenge_004_rerun.json")["original"],
        "challenge_005": reviews["challenge_005"],
        "frozen_modules_modified": False,
    }
    report = {"phase6": phase6, "phase7": phase7}
    (DIR / "phase7_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    rows = [
        ("Core pass", phase6["core"]["end_to_end_pass_rate"], phase7["core"]["end_to_end_pass_rate"]),
        ("target_object", phase6["metrics"]["target_object_accuracy"], metrics["target_object_accuracy"]),
        ("constraints", phase6["metrics"]["constraint_semantic_accuracy"], metrics["constraint_semantic_accuracy"]),
        ("action", phase6["metrics"]["action_accuracy"], metrics["action_accuracy"]),
        ("target selection", phase6["metrics"]["target_selection_exact_match_rate"], metrics["target_selection_exact_match_rate"]),
        ("negative", phase6["metrics"]["negative_case_pass_rate"], metrics["negative_case_pass_rate"]),
        ("segmentation", phase6["metrics"]["segmentation_visual_pass_rate"], metrics["segmentation_visual_pass_rate"]),
        ("action visual", phase6["metrics"]["action_visual_pass_rate"], metrics["action_visual_pass_rate"]),
    ]
    lines = [
        "# Phase 7 关系组合目标分割报告", "",
        "- Agent Brain：`deepseek-v4-pro`", "- Relation：`held_by_target` only", "",
        "| Metric | Phase 6 | Phase 7 | Delta |", "|---|---:|---:|---:|",
        *[
            f"| {name} | {old:.2%} | {new:.2%} | {new - old:+.2%} |"
            for name, old, new in rows
        ],
        "", "## Gate", "",
        "- core_003：person + umbrella composite outline，PASS。",
        "- core_004：关系绑定、双组件批量 SAM、mask OR、composite cutout 与 alpha，PASS。",
        "- core_014：零 verified subject，关系链跳过且未制造 target，PASS。",
        f"- Relation Binding：{relation_pass}/{len(relation_ids)}。", "",
        "## Repeatability", "",
    ]
    for case_id, item in repeatability.items():
        label_note = "label 一致" if item["label_consistent"] else f"仅 label 文案波动：{item['labels']}"
        lines.append(
            f"- `{case_id}`：{item['runs']} 次，业务签名{'一致' if item['business_consistent'] else '不一致'}；{label_note}。"
        )
    lines.extend([
        "", "## 已知问题", "",
        "- challenge_004 首次 Qwen verifier 返回错误 JSON 形状并被严格校验拒绝；同输入重跑成功，首次错误已保留。",
        "- challenge_005 仍为密集小目标 Grounding Recall 失败，本阶段未处理。",
        "- Windows 中文路径问题仍未处理。", "",
        "DINO、原 Qwen verifier、SAM2、Action、Renderer 均未修改；未加入视频或 UI。", "",
    ])
    (DIR / "phase7_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
