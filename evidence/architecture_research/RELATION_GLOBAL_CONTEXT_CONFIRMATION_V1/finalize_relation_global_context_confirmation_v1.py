"""汇总 RELATION_GLOBAL_CONTEXT_CONFIRMATION_V1 冻结重复实验。"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import run_context_evidence_policy_hardening_v1 as base


ROOT = Path(r"E:\3\_visual_agent_real_world_acceptance\v1\_relation_global_context_confirmation_v1")
EVENTS = ROOT / "raw_call_events.jsonl"
SCHEDULE = ROOT / "frozen_schedule.json"
STATUSES = {"satisfied", "not_satisfied", "uncertain"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call_valid(event: dict | None) -> bool:
    if not event or not event.get("executed") or not event.get("call"):
        return False
    call = event["call"]
    return call.get("error") is None and call.get("result") is not None


def binding_map(event: dict) -> dict[str, str]:
    result = event["call"]["result"]
    return {f"{row['subject_id']}::{row['related_id']}": row["status"] for row in result}


def stable_state(statuses: list[str]) -> dict:
    count = len(statuses)
    if count < 4:
        return {"classification": "INCONCLUSIVE", "state": None, "paired_valid": count, "counts": dict(Counter(statuses))}
    counts = Counter(statuses)
    state, same = counts.most_common(1)[0]
    stable = (count == 5 and same >= 4) or (count == 4 and same == 4)
    return {
        "classification": "STABLE" if stable else "UNSTABLE",
        "state": state if stable else None,
        "paired_valid": count,
        "counts": dict(counts),
    }


def reliability(events: list[dict]) -> dict:
    groups = {
        "a_relation": [row for row in events if row["arm"] == "A" and row["kind"] == "relation"],
        "b_global": [row for row in events if row["arm"] == "B" and row["kind"] == "global_context"],
        "b_relation": [row for row in events if row["arm"] == "B" and row["kind"] == "relation"],
    }
    result = {}
    for name, rows in groups.items():
        executed = [row for row in rows if row.get("executed")]
        calls = [row["call"] for row in executed]
        attempts = [attempt for call in calls for attempt in call.get("attempts", [])]
        failures = sum(not call_valid(row) for row in executed)
        result[name] = {
            "scheduled": len(rows),
            "executed": len(executed),
            "skipped": len(rows) - len(executed),
            "logical_final_failures": failures,
            "logical_final_failure_rate": round(failures / len(executed), 6) if executed else None,
            "http_attempts": len(attempts),
            "retry_count": sum(int(call.get("protocol", {}).get("retry_count", 0)) for call in calls),
            "recovered": sum(bool(call.get("protocol", {}).get("recovered")) for call in calls),
            "prompt_tokens": sum(int(item.get("prompt_tokens") or 0) for item in attempts),
            "completion_tokens": sum(int(item.get("completion_tokens") or 0) for item in attempts),
            "total_tokens": sum(int(item.get("total_tokens") or 0) for item in attempts),
            "model_elapsed_seconds": round(sum(float(item.get("elapsed_seconds") or 0) for item in attempts), 4),
            "reasoning_present_attempts": sum(bool(item.get("reasoning_present")) for item in attempts),
        }
    global_rows = groups["b_global"]
    projection_failures = sum(
        call_valid(row) and set(row["call"].get("projected_payload") or {}) != {"facts", "evidence"}
        for row in global_rows
    )
    result["b_global_projection_contract_failures"] = projection_failures
    result["b_relation_skipped_due_global_failure"] = sum(
        not row.get("executed") and row.get("skip_reason") == "global_context_final_failure"
        for row in groups["b_relation"]
    )
    return result


def main() -> None:
    schedule = read_json(SCHEDULE)
    events = read_jsonl(EVENTS)
    if len(events) != 105 or len({row["event_id"] for row in events}) != 105:
        raise RuntimeError(f"原始事件必须精确为 105 个唯一 event：{len(events)}")

    expected_order = []
    for slot in schedule["rows"]:
        for kind in slot["sequence"]:
            expected_order.append(f"{slot['case_id']}::rep{slot['repetition']}::{kind}")
    actual_order = [row["event_id"] for row in events]
    if actual_order != expected_order:
        raise RuntimeError("raw_call_events.jsonl 顺序与 frozen_schedule.json 不一致")

    cases = [
        case for case in base.load_cases()
        if case["route"] == "relation" and case["subjects"] and case["related_candidates"]
    ]
    case_map = {case["case_id"]: case for case in cases}
    frozen_cases = []
    expected = {}
    for case in cases:
        bindings = []
        for subject in case["subjects"]:
            for related in case["related_candidates"]:
                binding_id = f"{subject['id']}::{related['id']}"
                status = base.expected_for(case, binding_id)
                expected[(case["case_id"], binding_id)] = status
                bindings.append({"binding_id": binding_id, "expected": status})
        frozen_cases.append({
            "case_id": case["case_id"], "prompt_id": case["prompt_id"], "prompt": case["prompt"],
            "image_path": case["image_path"], "image_sha256": case["image_sha256"],
            "related_object": case["related_object"], "subjects": case["subjects"],
            "related_candidates": case["related_candidates"], "bindings": bindings,
        })
    (ROOT / "frozen_relation_cases.json").write_text(
        json.dumps({"count": len(frozen_cases), "binding_count": len(expected), "cases": frozen_cases}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    event_map = {row["event_id"]: row for row in events}
    observations = defaultdict(lambda: {"A": [], "B": []})
    paired_slot_rows = []
    for slot in schedule["rows"]:
        prefix = f"{slot['case_id']}::rep{slot['repetition']}"
        a_event = event_map[f"{prefix}::A_RELATION"]
        global_event = event_map[f"{prefix}::B_GLOBAL"]
        b_event = event_map[f"{prefix}::B_RELATION"]
        projection_ok = call_valid(global_event) and set(global_event["call"].get("projected_payload") or {}) == {"facts", "evidence"}
        paired_valid = call_valid(a_event) and projection_ok and call_valid(b_event)
        paired_slot_rows.append({
            "case_id": slot["case_id"], "image_sha256": slot["image_sha256"], "repetition": slot["repetition"],
            "first_arm": slot["first_arm"], "paired_valid": paired_valid,
            "a_relation_valid": call_valid(a_event), "b_global_valid": call_valid(global_event),
            "b_projection_valid": projection_ok, "b_relation_valid": call_valid(b_event),
        })
        if not paired_valid:
            continue
        a_bindings = binding_map(a_event)
        b_bindings = binding_map(b_event)
        for binding_id in slot["binding_ids"]:
            observations[(slot["case_id"], binding_id)]["A"].append(a_bindings[binding_id])
            observations[(slot["case_id"], binding_id)]["B"].append(b_bindings[binding_id])

    binding_rows = []
    pure_improvements = []
    stability_improvements = []
    regressions = []
    false_assignment = {"A": 0, "B": 0}
    legitimate_uncertain_harm = []
    for (case_id, binding_id), expected_status in expected.items():
        a_stable = stable_state(observations[(case_id, binding_id)]["A"])
        b_stable = stable_state(observations[(case_id, binding_id)]["B"])
        case = case_map[case_id]
        row = {
            "case_id": case_id, "image_sha256": case["image_sha256"], "binding_id": binding_id,
            "expected": expected_status, "A": a_stable, "B": b_stable,
        }
        if a_stable["classification"] == "STABLE" and b_stable["classification"] == "STABLE":
            if a_stable["state"] != expected_status and b_stable["state"] == expected_status:
                row["outcome"] = "stable_pure_semantic_improvement"
                pure_improvements.append(row)
            elif a_stable["state"] == expected_status and b_stable["state"] != expected_status:
                row["outcome"] = "stable_semantic_regression"
                regressions.append(row)
            else:
                row["outcome"] = "no_gate_change"
        elif a_stable["classification"] != "STABLE" and b_stable["classification"] == "STABLE" and b_stable["state"] == expected_status:
            row["outcome"] = "stability_improvement"
            stability_improvements.append(row)
        else:
            row["outcome"] = "inconclusive_or_unstable"
        for arm, state in (("A", a_stable), ("B", b_stable)):
            if expected_status == "not_satisfied" and state["classification"] == "STABLE" and state["state"] == "satisfied":
                false_assignment[arm] += 1
        if expected_status == "uncertain" and b_stable["classification"] == "STABLE" and b_stable["state"] in {"satisfied", "not_satisfied"}:
            legitimate_uncertain_harm.append(row)
        binding_rows.append(row)

    reliability_result = reliability(events)
    case_reliability = []
    for case in cases:
        case_events = [row for row in events if row["case_id"] == case["case_id"]]
        a_rows = [row for row in case_events if row["arm"] == "A" and row["kind"] == "relation"]
        global_rows = [row for row in case_events if row["arm"] == "B" and row["kind"] == "global_context"]
        b_rows = [row for row in case_events if row["arm"] == "B" and row["kind"] == "relation"]
        case_reliability.append({
            "case_id": case["case_id"], "image_sha256": case["image_sha256"],
            "a_relation_final_failures": sum(not call_valid(row) for row in a_rows),
            "b_global_final_failures": sum(not call_valid(row) for row in global_rows),
            "b_relation_final_failures": sum(not call_valid(row) for row in b_rows if row.get("executed")),
            "a_relation_retries": sum(int(row["call"]["protocol"]["retry_count"]) for row in a_rows),
            "b_relation_retries": sum(int(row["call"]["protocol"]["retry_count"]) for row in b_rows if row.get("executed")),
        })
    protocol_only_observations = [
        row for row in case_reliability
        if row["a_relation_final_failures"] > 0 and row["b_relation_final_failures"] == 0
    ]
    distinct_improvement_groups = sorted({row["image_sha256"] for row in pure_improvements})
    a_failure = reliability_result["a_relation"]["logical_final_failure_rate"]
    b_failure = reliability_result["b_relation"]["logical_final_failure_rate"]
    conditions = {
        "stable_pure_semantic_improvements_gte_2": len(pure_improvements) >= 2,
        "distinct_image_sha256_groups_gte_2": len(distinct_improvement_groups) >= 2,
        "stable_semantic_regression_eq_0": len(regressions) == 0,
        "b_false_assignment_lte_a": false_assignment["B"] <= false_assignment["A"],
        "legitimate_uncertain_to_wrong_binary_eq_0": len(legitimate_uncertain_harm) == 0,
        "global_projection_contract_failure_eq_0": reliability_result["b_global_projection_contract_failures"] == 0,
        "b_relation_failure_rate_lte_a": b_failure <= a_failure,
        "global_final_failures_recorded": reliability_result["b_global"]["scheduled"] == 35,
    }
    confirmed = all(conditions.values())
    valid_observations = sum(len(value["A"]) for value in observations.values())
    summary = {
        "stage": "RELATION_GLOBAL_CONTEXT_CONFIRMATION_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "execution": {
            "code_commit": "c2a784573dea313c3f80e714fbc4b7007563f9fa",
            "model": "qwen3.8:27b-mtp-q4_K_M", "base_url": "http://192.168.250.9:11434/v1",
            "temperature": 0, "timeout_seconds": 120, "concurrency": 1,
        },
        "scheduled": {"cases": 7, "bindings": 16, "repetitions": 5, "paired_binding_slots": 80, "logical_calls": 105},
        "actual": {
            "raw_events": len(events), "executed_logical_calls": sum(row.get("executed") for row in events),
            "paired_valid_case_repetitions": sum(row["paired_valid"] for row in paired_slot_rows),
            "valid_paired_semantic_observations": valid_observations,
        },
        "reliability": reliability_result,
        "case_reliability": case_reliability,
        "protocol_only_observations": protocol_only_observations,
        "binding_stability": binding_rows,
        "stable_pure_semantic_improvements": pure_improvements,
        "stability_improvements": stability_improvements,
        "stable_semantic_regressions": regressions,
        "distinct_improvement_image_sha256_groups": distinct_improvement_groups,
        "stable_false_assignment": false_assignment,
        "legitimate_uncertain_to_wrong_binary": legitimate_uncertain_harm,
        "gate_conditions": conditions,
        "confirmed": confirmed,
        "decision": {
            "relation_global_facts_candidate": "CONFIRMED" if confirmed else "NOT_CONFIRMED",
            "relation_evidence_policy": "FULL_SCENE_MARKED_BINDING_PLUS_SIMPLIFIED_GLOBAL_FACTS" if confirmed else "KEEP_CURRENT_PRODUCTION",
            "production_modification_authorized": False,
        },
    }
    (ROOT / "paired_slot_validity.json").write_text(json.dumps(paired_slot_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "confirmation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = [
        "# RELATION_GLOBAL_CONTEXT_CONFIRMATION_V1 结果报告", "",
        "## 执行完整性", "",
        f"- 7 cases / 16 bindings / 5 repetitions。",
        f"- Scheduled paired binding slots：80；valid paired semantic observations：{valid_observations}。",
        f"- Scheduled logical calls：105；actual executed logical calls：{summary['actual']['executed_logical_calls']}。",
        f"- Paired-valid case repetitions：{summary['actual']['paired_valid_case_repetitions']}/35。",
        f"- A-first/B-first：{schedule['first_arm_counts']['A']}/{schedule['first_arm_counts']['B']}。", "",
        "## Reliability", "",
        "| Layer | Scheduled | Executed | Final failure | Rate | Retry | Recovered | Tokens | Model seconds |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, label in (("a_relation", "A relation"), ("b_global", "B global"), ("b_relation", "B relation")):
        item = reliability_result[key]
        rate = "n/a" if item["logical_final_failure_rate"] is None else f"{item['logical_final_failure_rate']:.2%}"
        report.append(f"| {label} | {item['scheduled']} | {item['executed']} | {item['logical_final_failures']} | {rate} | {item['retry_count']} | {item['recovered']} | {item['total_tokens']} | {item['model_elapsed_seconds']:.1f} |")
    report += [
        "",
        f"- B global projection contract failure：{reliability_result['b_global_projection_contract_failures']}。",
        f"- B relation skipped due global failure：{reliability_result['b_relation_skipped_due_global_failure']}。", "",
        "### Protocol-only observation", "",
    ]
    if protocol_only_observations:
        for row in protocol_only_observations:
            report.append(
                f"- `{row['case_id']}`：A relation final failure {row['a_relation_final_failures']}/5，"
                f"B relation final failure {row['b_relation_final_failures']}/5；该变化只计 reliability，不计 semantic improvement。"
            )
    else:
        report.append("- 无。")
    report += ["",
        "## Stable semantic result", "",
        f"- Stable pure semantic improvements：{len(pure_improvements)}。",
        f"- Independent improvement image SHA groups：{len(distinct_improvement_groups)}。",
        f"- Stability improvements（不计入 Gate）：{len(stability_improvements)}。",
        f"- Stable semantic regressions：{len(regressions)}。",
        f"- Stable false assignment A/B：{false_assignment['A']}/{false_assignment['B']}。",
        f"- Legitimate uncertain → wrong binary：{len(legitimate_uncertain_harm)}。", "",
    ]
    if pure_improvements:
        report.append("- Pure improvements：" + "；".join(
            f"`{row['case_id']} / {row['binding_id']}`：A={row['A']['state']} → B={row['B']['state']}（expected={row['expected']}）"
            for row in pure_improvements
        ) + "。")
    report += ["", "## Gate", "",
        "| Condition | Result |", "|---|---|",
    ]
    for key, passed in conditions.items():
        report.append(f"| `{key}` | {'PASS' if passed else 'FAIL'} |")
    report += [
        "", "## Decision", "",
        f"```text\nRELATION_GLOBAL_FACTS_CANDIDATE = {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}\n"
        f"RELATION_EVIDENCE_POLICY = {summary['decision']['relation_evidence_policy']}\n"
        "PRODUCTION MODIFICATION = NOT AUTHORIZED\n```", "",
        "逐 binding 五次状态、稳定性分类与 improvement/regression 明细见 `confirmation_summary.json`；逐 logical call 原始响应见 `raw_call_events.jsonl`。", "",
    ]
    (ROOT / "RELATION_GLOBAL_CONTEXT_CONFIRMATION_V1_REPORT.md").write_text("\n".join(report), encoding="utf-8")

    for script_name in ("run_relation_global_context_confirmation_v1.py", "finalize_relation_global_context_confirmation_v1.py"):
        shutil.copy2(SCRIPT_DIR / script_name, ROOT / script_name)
    artifact_names = [
        "RELATION_GLOBAL_CONTEXT_CONFIRMATION_V1_CONTRACT.md", "frozen_contract.json", "frozen_schedule.json",
        "frozen_relation_cases.json", "raw_call_events.jsonl", "paired_slot_validity.json", "confirmation_summary.json",
        "RELATION_GLOBAL_CONTEXT_CONFIRMATION_V1_REPORT.md", "run_relation_global_context_confirmation_v1.py",
        "finalize_relation_global_context_confirmation_v1.py",
    ]
    manifest = {"files": [{"path": name, "bytes": (ROOT / name).stat().st_size, "sha256": sha256(ROOT / name)} for name in artifact_names]}
    (ROOT / "execution_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "actual": summary["actual"], "reliability": reliability_result, "pure_improvements": len(pure_improvements),
        "improvement_sha_groups": len(distinct_improvement_groups), "regressions": len(regressions),
        "false_assignment": false_assignment, "conditions": conditions, "decision": summary["decision"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
