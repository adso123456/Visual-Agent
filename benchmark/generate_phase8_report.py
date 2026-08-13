import json
from pathlib import Path


DIR = Path(__file__).resolve().parent


def load(name: str):
    return json.loads((DIR / name).read_text(encoding="utf-8"))


def protocol_stats(rows: list[dict]) -> dict:
    return {
        "total_calls": len(rows),
        "first_attempt_success": sum(
            row.get("status") == "success" and row.get("protocol", {}).get("attempts") == 1
            for row in rows
        ),
        "contract_retries": sum(row.get("protocol", {}).get("retry_count", 0) for row in rows),
        "recovered_retries": sum(bool(row.get("protocol", {}).get("recovered")) for row in rows),
        "unrecovered_structured_failures": sum(row.get("status") != "success" for row in rows),
    }


def main() -> None:
    phase7 = load("phase7_report.json")["phase7"]
    cases = {item["id"]: item for item in load("cases.json")}
    results = {item["case_id"]: item for item in load("phase8_raw_results.json")}
    reviews = {item["id"]: item for item in load("phase7_manual_reviews.json")}
    candidate = protocol_stats(load("phase8_candidate_stability.json"))
    relation = protocol_stats(load("phase8_relation_stability.json"))
    core_ids = [case_id for case_id, case in cases.items() if case["suite"] == "core"]
    negative_ids = [
        case_id for case_id in core_ids if cases[case_id]["expected"]["target_count"] == 0
    ]
    segmented_ids = [case_id for case_id in core_ids if results[case_id]["targets"]]

    core_pass = sum(
        results[case_id]["status"] == "success"
        and results[case_id]["structural_pass"]
        and reviews[case_id]["result"] == "PASS"
        for case_id in core_ids
    )
    metrics = {
        "target_selection_exact_match_rate": round(
            sum(reviews[case_id]["target_selection"] is True for case_id in core_ids)
            / len(core_ids),
            4,
        ),
        "negative_case_pass_rate": round(
            sum(reviews[case_id]["result"] == "PASS" for case_id in negative_ids)
            / len(negative_ids),
            4,
        ),
        "segmentation_visual_pass_rate": round(
            sum(reviews[case_id]["segmentation"] is True for case_id in segmented_ids)
            / len(segmented_ids),
            4,
        ),
        "action_visual_pass_rate": round(
            sum(reviews[case_id]["action"] is True for case_id in core_ids) / len(core_ids),
            4,
        ),
    }
    runtime_failures = sum(item["status"] != "success" for item in results.values())
    structured_failures = sum(
        item["status"] == "error" and "structured output failed" in item.get("error", "")
        for item in results.values()
    )
    phase8 = {
        "qwen_model": "qwen3-vl-flash",
        "deepseek_model": "deepseek-v4-pro",
        "max_attempts": 2,
        "candidate_verification_stability": candidate,
        "relation_verification_stability": relation,
        "core": {
            "passed_cases": core_pass,
            "total_cases": len(core_ids),
            "end_to_end_pass_rate": round(core_pass / len(core_ids), 4),
        },
        "metrics": metrics,
        "runtime_failure_count": runtime_failures,
        "structured_output_runtime_failure_count": structured_failures,
        "challenge_004": {
            "status": "PASS",
            "attempts": results["challenge_004"]["qwen_protocol"]["candidate_verification"]["attempts"],
            "targets": len(results["challenge_004"]["targets"]),
            "note": "已知 dict shape 未复现；首次合法数组响应通过，完整链路正常完成。",
        },
        "challenge_005": {
            "status": "FAIL",
            "primary_failure_stage": "GROUNDING",
            "targets": len(results["challenge_005"]["targets"]),
            "note": "仍只覆盖 3 个前景红衣目标，密集小目标召回问题未处理。",
        },
        "frozen_modules_modified": False,
    }
    report = {"phase7": phase7, "phase8": phase8}
    (DIR / "phase8_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# Phase 8 Qwen 结构化输出协议可靠性报告",
        "",
        f"- Core：{core_pass}/{len(core_ids)}",
        f"- Candidate 专项：{candidate}",
        f"- Relation 专项：{relation}",
        f"- structured_output_runtime_failure_count：{structured_failures}",
        "- challenge_004：PASS，首次响应通过，2 个目标，完整链路正常完成。",
        "- challenge_005：FAIL，仍为密集小目标 Grounding Recall 问题。",
        "",
        "## 契约结论",
        "",
        "- 最大 2 次尝试；只对空响应、非法 JSON、严格契约校验失败重试。",
        "- correction 只包含格式错误、原结构提示及禁止改变语义的约束。",
        "- 合法 uncertain/not_satisfied 不重试；Python 不做 dict 到 list 的宽容转换。",
        "- 两次失败后抛出带错误分类的 RuntimeError；API/网络异常不由本机制重试。",
        "- DINO、SAM2、Action、Renderer、Qwen 视觉判断语义、Relation 判断语义均未修改。",
        "",
    ]
    (DIR / "phase8_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
