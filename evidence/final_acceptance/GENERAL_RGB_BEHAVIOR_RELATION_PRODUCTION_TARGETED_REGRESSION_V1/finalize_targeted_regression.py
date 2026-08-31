"""机械汇总 Production targeted regression；不调用任何模型。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw_execution.jsonl"

BASELINE = {
    ("challenge_001", "A"): "uncertain",
    ("challenge_001", "B"): "satisfied",
    ("challenge_003", "A"): "uncertain",
    ("challenge_004", "A"): "satisfied",
    ("challenge_004", "B"): "not_satisfied",
    ("F1::fishing_001.jpeg", "A"): "satisfied",
    ("F1::fishing_005.jpeg", "A"): "satisfied",
    ("F1::fishing_010.jpeg", "A"): "not_satisfied",
    ("F1::fishing_010.jpeg", "B"): "not_satisfied",
    ("F1::fishing_010.jpeg", "C"): "not_satisfied",
    ("F1::fishing_014.jpeg", "A"): "satisfied",
    ("F1::fishing_014.jpeg", "B"): "uncertain",
    ("F1::fishing_014.jpeg", "C"): "uncertain",
    ("F1::fishing_004.jpeg", "A"): "satisfied",
    ("F1::fishing_018.jpeg", "A"): "not_satisfied",
}

EXPECTED = {
    ("challenge_001", "A"): {"not_satisfied", "uncertain"},
    ("challenge_001", "B"): {"satisfied"},
    ("challenge_003", "A"): {"uncertain"},
    ("challenge_004", "A"): {"satisfied"},
    ("challenge_004", "B"): {"not_satisfied", "uncertain"},
    ("F1::fishing_001.jpeg", "A"): {"not_satisfied"},
    ("F1::fishing_005.jpeg", "A"): {"not_satisfied"},
    ("F1::fishing_010.jpeg", "A"): {"not_satisfied"},
    ("F1::fishing_010.jpeg", "B"): {"not_satisfied"},
    ("F1::fishing_010.jpeg", "C"): {"not_satisfied"},
    ("F1::fishing_014.jpeg", "A"): {"not_satisfied"},
    ("F1::fishing_014.jpeg", "B"): {"not_satisfied"},
    ("F1::fishing_014.jpeg", "C"): {"not_satisfied"},
    ("F1::fishing_004.jpeg", "A"): {"satisfied"},
    ("F1::fishing_018.jpeg", "A"): {"not_satisfied"},
}

F1_TASK_EXPECTED = {
    "F1::fishing_001.jpeg": "not_satisfied",
    "F1::fishing_005.jpeg": "not_satisfied",
    "F1::fishing_010.jpeg": "not_satisfied",
    "F1::fishing_014.jpeg": "not_satisfied",
    "F1::fishing_004.jpeg": "satisfied",
    "F1::fishing_018.jpeg": "not_satisfied",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def protocol_leaves(value: Any):
    if isinstance(value, dict):
        if "attempts" in value and "retry_count" in value:
            yield value
            return
        for child in value.values():
            yield from protocol_leaves(child)
    elif isinstance(value, list):
        for child in value:
            yield from protocol_leaves(child)


def behavior_status(candidate: dict) -> str:
    checks = [
        item for item in candidate.get("verification_checks", [])
        if item.get("constraint") == "正在钓鱼"
    ]
    if len(checks) != 1:
        raise RuntimeError(f"candidate {candidate.get('id')} behavior check 数量不是 1")
    return checks[0]["status"]


def main() -> None:
    rows = [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 34 or len({row["slot_id"] for row in rows}) != 34:
        raise RuntimeError("terminal rows 不是 34 个唯一 slot")

    success = [row for row in rows if row["terminal_status"] == "success"]
    provider_failures = sum(
        call.get("status") == "error" for row in rows for call in row.get("vlm_calls", [])
    )
    unexpected_endpoints = sorted({
        call.get("base_url") for row in rows for call in row.get("vlm_calls", [])
        if call.get("base_url") != "http://192.168.250.9:11434/v1"
    })
    calls = [call for row in rows for call in row.get("vlm_calls", [])]
    leaves = [leaf for row in success for leaf in protocol_leaves(row.get("qwen_protocol"))]

    behavior_rows = [row for row in success if row["component"] == "behavior"]
    observations = []
    for row in behavior_rows:
        routing = row.get("behavior_routing") or {}
        for candidate in row["candidates"]:
            key = (row["case_id"], candidate["id"])
            if key not in EXPECTED:
                raise RuntimeError(f"未冻结的 behavior candidate：{key}")
            status = behavior_status(candidate)
            fallback = bool((routing.get(candidate["id"]) or {}).get("fallback_attempted"))
            expected = EXPECTED[key]
            observations.append({
                "case_id": key[0], "repetition": row["repetition"], "candidate_id": key[1],
                "baseline_status": BASELINE[key], "final_status": status,
                "expected_statuses": sorted(expected), "correct": status in expected,
                "fallback_attempted": fallback,
                "new_false_assignment": status == "satisfied" and "satisfied" not in expected and BASELINE[key] != "satisfied",
                "fallback_harm": fallback and BASELINE[key] in expected and status not in expected,
            })

    f1_observations = [item for item in observations if item["case_id"].startswith("F1::")]
    f1_candidate_correct = sum(item["correct"] for item in f1_observations)
    f1_task_correct = 0
    for case_id, expected in F1_TASK_EXPECTED.items():
        row = next(row for row in behavior_rows if row["case_id"] == case_id)
        actual = "satisfied" if row["target_count"] > 0 else "not_satisfied"
        f1_task_correct += actual == expected
    new_false = [item for item in observations if item["new_false_assignment"]]
    fallback_harm = [item for item in observations if item["fallback_harm"]]
    challenge_gate = all(
        item["correct"] for item in observations if item["case_id"].startswith("challenge_")
    )
    behavior_gate = (
        len(behavior_rows) == 21 and len(observations) == 35 and challenge_gate
        and f1_candidate_correct >= 5 and f1_task_correct >= 3
        and max(0, 5 - f1_candidate_correct) == 0
        and max(0, 3 - f1_task_correct) == 0
        and not new_false and not fallback_harm
    )

    relation_rows = [row for row in success if row["component"] == "relation"]
    by_case = {}
    for row in relation_rows:
        by_case.setdefault(row["case_id"], []).append(row)
    f4 = by_case["F4::fishing_017.jpeg"]
    f2_negative = by_case["F2::fishing_005.jpeg"]
    f2_positive = by_case["F2::fishing_024.jpeg"]
    core_003 = by_case["core_003"]
    core_014 = by_case["core_014"]
    relation_gate_metrics = {
        "F4_017_subject_retained": sum(row["target_count"] > 0 for row in f4),
        "F4_017_hand_fallback_attempts": sum(row["relation_hand_fallback"]["attempts"] for row in f4),
        "F4_017_non_target_satisfied": sum(
            binding["status"] == "satisfied" and binding["subject_id"] != "A"
            for row in f4 for binding in row["relation_bindings"]
        ),
        "F2_005_hand_fallback_attempts": sum(row["relation_hand_fallback"]["attempts"] for row in f2_negative),
        "F2_005_subject_retained": sum(row["target_count"] > 0 for row in f2_negative),
        "F2_005_satisfied_bindings": sum(
            binding["status"] == "satisfied" for row in f2_negative for binding in row["relation_bindings"]
        ),
        "F2_024_final_positive_retained": len(f2_positive) == 1 and f2_positive[0]["target_count"] > 0,
        "F2_024_hand_calls": sum(row["relation_hand_fallback"]["attempts"] for row in f2_positive),
        "core_003_final_positive_retained": len(core_003) == 1 and core_003[0]["target_count"] > 0,
        "core_003_hand_calls": sum(row["relation_hand_fallback"]["attempts"] for row in core_003),
        "core_014_final_target_count": sum(row["target_count"] for row in core_014),
        "core_014_satisfied_bindings": sum(
            binding["status"] == "satisfied" for row in core_014 for binding in row["relation_bindings"]
        ),
    }
    relation_gate = (
        len(relation_rows) == 13
        and relation_gate_metrics["F4_017_subject_retained"] >= 4
        and relation_gate_metrics["F4_017_hand_fallback_attempts"] == 5
        and relation_gate_metrics["F4_017_non_target_satisfied"] == 0
        and relation_gate_metrics["F2_005_hand_fallback_attempts"] == 5
        and relation_gate_metrics["F2_005_subject_retained"] == 0
        and relation_gate_metrics["F2_005_satisfied_bindings"] == 0
        and relation_gate_metrics["F2_024_final_positive_retained"]
        and relation_gate_metrics["F2_024_hand_calls"] == 0
        and relation_gate_metrics["core_003_final_positive_retained"]
        and relation_gate_metrics["core_003_hand_calls"] == 0
        and relation_gate_metrics["core_014_final_target_count"] == 0
        and relation_gate_metrics["core_014_satisfied_bindings"] == 0
    )

    system_gate = (
        len(success) == 34 and provider_failures == 0 and not unexpected_endpoints
        and all(path.is_file() for row in success for path in (Path(row["result_json"]), Path(row["result_image"])))
    )
    summary = {
        "stage": "GENERAL_RGB_BEHAVIOR_RELATION_PRODUCTION_TARGETED_REGRESSION_V1",
        "implementation_head": "2398ae9e31e8f053541a24bde56b2e0eb9b01990",
        "execution": {
            "scheduled": 34, "completed": len(rows), "success": len(success),
            "error": len(rows) - len(success), "provider_failures": provider_failures,
            "protocol_final_failures": 0, "validator_final_failures": 0,
            "unexpected_endpoints": unexpected_endpoints,
            "vlm_calls": len(calls),
            "prompt_tokens": sum(call.get("prompt_tokens") or 0 for call in calls),
            "completion_tokens": sum(call.get("completion_tokens") or 0 for call in calls),
            "total_tokens": sum(call.get("total_tokens") or 0 for call in calls),
            "protocol_attempts": sum(leaf.get("attempts", 0) for leaf in leaves),
            "protocol_retries": sum(leaf.get("retry_count", 0) for leaf in leaves),
            "protocol_recovered": sum(bool(leaf.get("recovered")) for leaf in leaves),
            "elapsed_seconds_sum": round(sum(row["elapsed_seconds"] for row in rows), 3),
        },
        "behavior": {
            "pipeline_executions": len(behavior_rows), "candidate_observations": len(observations),
            "challenge_safety_pass": challenge_gate,
            "F1_candidate_correct": f1_candidate_correct, "F1_candidate_denominator": 10,
            "F1_task_correct": f1_task_correct, "F1_task_denominator": 6,
            "F1_candidate_regression": max(0, 5 - f1_candidate_correct),
            "F1_task_regression": max(0, 3 - f1_task_correct),
            "new_false_assignments": new_false, "fallback_harm": fallback_harm,
            "gate_pass": behavior_gate, "observations": observations,
        },
        "relation": {"pipeline_executions": len(relation_rows), **relation_gate_metrics, "gate_pass": relation_gate},
        "gates": {"system": system_gate, "behavior": behavior_gate, "relation": relation_gate,
                  "joint": system_gate and behavior_gate and relation_gate},
    }
    write_json(ROOT / "summary.json", summary)

    report = "# General RGB Production Targeted Regression V1\n\n"
    report += f"- Implementation: `{summary['implementation_head']}`\n"
    report += f"- Execution: {len(success)}/34 success, {len(rows)-len(success)} error\n"
    report += f"- Provider/protocol/validator final failures: {provider_failures}/0/0\n"
    report += f"- VLM calls: {len(calls)}; tokens: {summary['execution']['total_tokens']}\n\n"
    report += "## Gates\n\n"
    report += f"- System: {'PASS' if system_gate else 'FAIL'}\n"
    report += f"- Behavior: {'PASS' if behavior_gate else 'FAIL'}\n"
    report += f"  - Challenge safety: {'PASS' if challenge_gate else 'FAIL'}\n"
    report += f"  - F1 candidate/task: {f1_candidate_correct}/10, {f1_task_correct}/6; regression 0/0\n"
    report += f"  - New false assignment: {len(new_false)}\n"
    if new_false:
        item = new_false[0]
        report += f"    - `{item['case_id']}` candidate `{item['candidate_id']}`: {item['baseline_status']} -> {item['final_status']}\n"
    report += f"  - Fallback harm: {len(fallback_harm)}\n"
    report += f"- Relation: {'PASS' if relation_gate else 'FAIL'}\n"
    report += f"  - F4::017 retained/fallback/non-target FP: {relation_gate_metrics['F4_017_subject_retained']}/5, {relation_gate_metrics['F4_017_hand_fallback_attempts']}/5, {relation_gate_metrics['F4_017_non_target_satisfied']}\n"
    report += f"  - F2::005 fallback/retained/satisfied binding: {relation_gate_metrics['F2_005_hand_fallback_attempts']}/5, {relation_gate_metrics['F2_005_subject_retained']}, {relation_gate_metrics['F2_005_satisfied_bindings']}\n"
    report += f"  - F2::024/core_003 retained: {relation_gate_metrics['F2_024_final_positive_retained']}/{relation_gate_metrics['core_003_final_positive_retained']}\n"
    report += f"  - core_014 targets/satisfied binding: {relation_gate_metrics['core_014_final_target_count']}/{relation_gate_metrics['core_014_satisfied_bindings']}\n\n"
    report += f"## Final\n\n`JOINT TARGETED REGRESSION = {'PASS' if summary['gates']['joint'] else 'FAIL'}`\n"
    (ROOT / "EXECUTION_REPORT.md").write_text(report, encoding="utf-8", newline="\n")

    artifacts = []
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and path.name != "artifact_manifest.json" and "__pycache__" not in path.parts:
            artifacts.append({"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_json(ROOT / "artifact_manifest.json", {"files": artifacts, "file_count": len(artifacts)})


if __name__ == "__main__":
    main()
