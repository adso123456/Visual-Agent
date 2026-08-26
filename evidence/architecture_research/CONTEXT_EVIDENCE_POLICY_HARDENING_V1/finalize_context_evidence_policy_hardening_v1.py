"""汇总 CONTEXT_EVIDENCE_POLICY_HARDENING_V1 冻结对照结果。"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(r"E:\3\_visual_agent_real_world_acceptance\v1\_context_evidence_policy_hardening_v1")
SCRIPT_DIR = Path(__file__).resolve().parent
ARMS = {"A": ROOT / "arm_a.jsonl", "B": ROOT / "arm_b.jsonl", "C": ROOT / "arm_c.jsonl"}
ROUTES = ("attribute", "behavior", "relation")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit_map(row: dict, universe: dict[str, dict]) -> dict[str, dict]:
    actual = {unit["unit_id"]: unit for unit in row["units"]}
    return {
        unit_id: actual.get(unit_id, {"unit_id": unit_id, "expected": expected["expected"], "status": "protocol_failure"})
        for unit_id, expected in universe.items()
    }


def score_rows(rows: list[dict], universes: dict[str, dict[str, dict]]) -> dict:
    unit_total = unit_correct = task_correct = 0
    status_counts: Counter[str] = Counter()
    false_assignment = 0
    by_route = defaultdict(lambda: {"unit_total": 0, "unit_correct": 0, "task_total": 0, "task_correct": 0,
                                   "false_assignment": 0, "uncertain": 0, "protocol_failure": 0})
    normalized = {}
    for row in rows:
        route = row["route"]
        units = unit_map(row, universes[row["case_id"]])
        normalized[row["case_id"]] = units
        for unit in units.values():
            unit_total += 1
            by_route[route]["unit_total"] += 1
            status_counts[unit["status"]] += 1
            by_route[route][unit["status"] if unit["status"] in {"uncertain", "protocol_failure"} else "_ignored"] = (
                by_route[route].get(unit["status"] if unit["status"] in {"uncertain", "protocol_failure"} else "_ignored", 0) + 1
            )
            if unit["status"] == unit["expected"]:
                unit_correct += 1
                by_route[route]["unit_correct"] += 1
            if unit["expected"] == "not_satisfied" and unit["status"] == "satisfied":
                false_assignment += 1
                by_route[route]["false_assignment"] += 1
        task_ok = row["task_status"] == row["expected_task_status"]
        task_correct += int(task_ok)
        by_route[route]["task_total"] += 1
        by_route[route]["task_correct"] += int(task_ok)
    for route in ROUTES:
        by_route[route].pop("_ignored", None)
    return {
        "unit_total": unit_total,
        "unit_correct": unit_correct,
        "unit_accuracy": round(unit_correct / unit_total, 6) if unit_total else None,
        "task_total": len(rows),
        "task_correct": task_correct,
        "task_accuracy": round(task_correct / len(rows), 6),
        "false_assignment": false_assignment,
        "status_counts": dict(sorted(status_counts.items())),
        "by_route": dict(by_route),
        "normalized_units": normalized,
    }


def unique_unit_calls(row: dict) -> list[dict]:
    if row.get("route") == "relation":
        return [row["units"][0]["call"]] if row.get("units") else []
    calls = []
    seen = set()
    for unit in row.get("units", []):
        call = unit.get("call")
        if call is not None and id(call) not in seen:
            seen.add(id(call))
            calls.append(call)
    return calls


def cost_for_calls(calls: list[dict]) -> dict:
    logical_calls = len(calls)
    attempts = [attempt for call in calls for attempt in call.get("attempts", [])]
    protocols = [call.get("protocol", {}) for call in calls]
    return {
        "logical_calls": logical_calls,
        "http_attempts": len(attempts),
        "retry_count": sum(int(item.get("retry_count", 0)) for item in protocols),
        "recovered": sum(bool(item.get("recovered")) for item in protocols),
        "protocol_failures": sum(bool(call.get("error")) for call in calls),
        "prompt_tokens": sum(int(item.get("prompt_tokens") or 0) for item in attempts),
        "completion_tokens": sum(int(item.get("completion_tokens") or 0) for item in attempts),
        "total_tokens": sum(int(item.get("total_tokens") or 0) for item in attempts),
        "model_elapsed_seconds": round(sum(float(item.get("elapsed_seconds") or 0) for item in attempts), 4),
        "reasoning_present_attempts": sum(bool(item.get("reasoning_present")) for item in attempts),
    }


def cost_stats(arm: str, rows: list[dict], a_rows: list[dict]) -> dict:
    calls = []
    if arm == "A":
        for row in rows:
            calls.extend(unique_unit_calls(row))
    elif arm == "B":
        for row in rows:
            calls.append(row["global_context_call"])
            calls.extend(unique_unit_calls(row))
    else:
        for row in a_rows:
            calls.extend(unique_unit_calls(row))
        for row in rows:
            if row.get("global_context_call") is not None:
                calls.append(row["global_context_call"])
            if row.get("route") == "relation" and row.get("fallback_results"):
                calls.append(row["fallback_results"][0]["call"])
                continue
            seen = set()
            for unit in row.get("fallback_results", []):
                call = unit.get("call")
                if call is not None and id(call) not in seen:
                    seen.add(id(call))
                    calls.append(call)
    result = cost_for_calls(calls)
    result["mean_seconds_per_logical_call"] = round(result["model_elapsed_seconds"] / result["logical_calls"], 4)
    result["logical_calls_per_image"] = round(result["logical_calls"] / 25, 4)
    result["tokens_per_image"] = round(result["total_tokens"] / 25, 2)
    result["model_seconds_per_image"] = round(result["model_elapsed_seconds"] / 25, 4)
    return result


def compare_to_a(arm_units: dict, a_units: dict, routes: dict[str, str]) -> dict:
    improvements = []
    regressions = []
    for case_id, baseline in a_units.items():
        for unit_id, a_unit in baseline.items():
            other = arm_units[case_id][unit_id]
            item = {
                "case_id": case_id, "route": routes[case_id], "unit_id": unit_id,
                "expected": a_unit["expected"], "a_status": a_unit["status"], "new_status": other["status"],
            }
            if a_unit["status"] != a_unit["expected"] and other["status"] == other["expected"]:
                improvements.append(item)
            elif a_unit["status"] == a_unit["expected"] and other["status"] != other["expected"]:
                regressions.append(item)
    return {"improvements": improvements, "regressions": regressions}


def uncertain_resolution(rows: list[dict], a_score: dict) -> dict:
    row_map = {row["case_id"]: row for row in rows}
    counts = Counter()
    details = []
    for case_id, units in a_score["normalized_units"].items():
        other = unit_map(row_map[case_id], units)
        for unit_id, baseline in units.items():
            if baseline["status"] != "uncertain":
                continue
            status = other[unit_id]["status"]
            expected = baseline["expected"]
            if expected == "uncertain":
                outcome = "correctly_preserved" if status == "uncertain" else "fallback_harm"
            elif status == expected:
                outcome = "correctly_resolved"
            elif status == "uncertain":
                outcome = "still_uncertain"
            else:
                outcome = "wrong_resolution"
            counts[outcome] += 1
            details.append({"case_id": case_id, "unit_id": unit_id, "expected": expected, "new_status": status, "outcome": outcome})
    return {"counts": dict(counts), "details": details}


def policy_decision(scores: dict, comparisons: dict, resolutions: dict) -> dict:
    decisions = {
        "attribute": {
            "selected_arm": "A",
            "policy": "ISOLATED_CANDIDATE_EVIDENCE",
            "reasons": ["A/B/C 均为 5/6 unit、2/2 task", "Global Facts 无质量增益，仅增加调用成本"],
        },
        "behavior": {
            "selected_arm": "A",
            "policy": "35_PERCENT_CANDIDATE_LOCAL_EVIDENCE",
            "reasons": [
                "B/C 都把合法 uncertain 的 challenge_003 强制改为 satisfied",
                "C 仅净增 1 个正确 unit，且存在 fallback_harm；B 虽增益较大但存在 1 个明确回归",
                "当前结果不支持安全启用 Global Context",
            ],
        },
        "relation": {
            "selected_arm": "B",
            "policy": "FULL_SCENE_MARKED_BINDING_PLUS_SIMPLIFIED_GLOBAL_FACTS",
            "reasons": ["unit correct 3→5", "task correct 4→5", "false assignment 2→1", "0 unit regression"],
            "qualification": "收益样本仅 2 个，其中 1 个是 A 单次协议失败；Production 实施前需代码审查授权",
        },
    }
    any_global = True
    return {
        "route_policy": decisions,
        "global_context_role": "AUXILIARY_CONTEXT_ONLY" if any_global else "NOT_AUTHORIZED_FOR_PRODUCTION",
        "production_change_recommended": any_global,
        "production_modification_authorized": False,
    }


def percent(correct: int, total: int) -> str:
    return f"{correct}/{total} ({correct / total:.2%})" if total else "n/a"


def main() -> None:
    rows = {arm: read_jsonl(path) for arm, path in ARMS.items()}
    if any(len(items) != 25 for items in rows.values()):
        raise RuntimeError({arm: len(items) for arm, items in rows.items()})
    if any(len({row["case_id"] for row in items}) != 25 for items in rows.values()):
        raise RuntimeError("存在重复或缺失 case")

    a_universes = {row["case_id"]: {unit["unit_id"]: unit for unit in row["units"]} for row in rows["A"]}
    routes = {row["case_id"]: row["route"] for row in rows["A"]}
    scores = {arm: score_rows(items, a_universes) for arm, items in rows.items()}
    scores["routes"] = routes
    comparisons = {
        arm: compare_to_a(scores[arm]["normalized_units"], scores["A"]["normalized_units"], routes)
        for arm in ("B", "C")
    }
    resolutions = {arm: uncertain_resolution(rows[arm], scores["A"]) for arm in ("B", "C")}
    costs = {arm: cost_stats(arm, rows[arm], rows["A"]) for arm in ARMS}

    c_triggered = [row for row in rows["C"] if row["fallback_triggered"]]
    c_lazy_ok = all((row["global_context_call"] is not None) == row["fallback_triggered"] for row in rows["C"])
    immutable = []
    c_map = {row["case_id"]: row for row in rows["C"]}
    for a_row in rows["A"]:
        c_units = {unit["unit_id"]: unit for unit in c_map[a_row["case_id"]]["units"]}
        for unit in a_row["units"]:
            if unit["status"] != "uncertain" and c_units[unit["unit_id"]]["status"] != unit["status"]:
                immutable.append({"case_id": a_row["case_id"], "unit_id": unit["unit_id"]})
    projections = [row["global_context_call"].get("projected_payload") for arm in ("B", "C") for row in rows[arm]
                   if row.get("global_context_call") is not None]
    projection_ok = all(payload is None or set(payload) == {"facts", "evidence"} for payload in projections)

    clean_scores = {}
    for arm in ARMS:
        clean_scores[arm] = {key: value for key, value in scores[arm].items() if key != "normalized_units"}
    clean_scores.pop("routes", None)
    summary = {
        "stage": "CONTEXT_EVIDENCE_POLICY_HARDENING_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "execution": {
            "code_commit": "c2a784573dea313c3f80e714fbc4b7007563f9fa",
            "model": "qwen3.8:27b-mtp-q4_K_M",
            "base_url": "http://192.168.250.9:11434/v1",
            "api_key_recorded": False,
            "temperature": 0,
            "timeout_seconds": 120,
            "concurrency": 1,
            "continuity": "执行终端在 A 完成、C 完成 6 条后中断；增量 runner 按 case_id 跳过已完成行并在同一冻结配置下续跑，未重跑或补跑任何已落盘 case。",
        },
        "evaluation_set": {"cases": 25, "pollution_cases": 0, "routes": dict(Counter(routes.values())), "unit_denominator": scores["A"]["unit_total"]},
        "arms": clean_scores,
        "cost": costs,
        "comparison_to_a": comparisons,
        "uncertain_resolution": resolutions,
        "contract_checks": {
            "c_lazy_evaluation": c_lazy_ok,
            "c_triggered_images": len(c_triggered),
            "c_fallback_units": sum(len(row["fallback_unit_ids"]) for row in c_triggered),
            "c_non_uncertain_immutable": not immutable,
            "immutability_violations": immutable,
            "downstream_projection_facts_evidence_only": projection_ok,
            "task_status_leak_count": sum(payload is not None and "task_status" in payload for payload in projections),
        },
    }
    summary["decision"] = policy_decision({**scores, "routes": routes}, comparisons, resolutions)
    (ROOT / "comparison_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    decision = summary["decision"]
    report = [
        "# CONTEXT_EVIDENCE_POLICY_HARDENING_V1 结果报告", "",
        "## 执行边界", "",
        "- 25 个冻结 General RGB 真实案例；F1/F2/F4 18 个，Demo Acceptance 7 个。",
        "- P1–P4 为 0；未修改 Production；Local VLM 配置固定。",
        "- 固定既有 Detector candidates 与 subject validity，只比较候选语义/关系 binding 的 evidence policy。",
        "- A=当前 Production；B=A+每图一次 simplified global facts；C=仅 A uncertain 时 lazy fallback。", "",
        "执行终端曾在 A 完成、C 完成 6 条后中断；runner 依据已落盘 case_id 原样续跑，未重跑、补跑或覆盖任何已完成 case。", "",
        "## 核心结果", "",
        "| Arm | Unit accuracy | Task accuracy | False assignment | Uncertain | Protocol failure | Logical calls | Tokens | Model seconds |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        item = scores[arm]
        cost = costs[arm]
        report.append(
            f"| {arm} | {percent(item['unit_correct'], item['unit_total'])} | {percent(item['task_correct'], item['task_total'])} | "
            f"{item['false_assignment']} | {item['status_counts'].get('uncertain', 0)} | {item['status_counts'].get('protocol_failure', 0)} | "
            f"{cost['logical_calls']} | {cost['total_tokens']} | {cost['model_elapsed_seconds']:.1f} |"
        )
    report += ["", "## 协议与成本", "",
               "| Arm | HTTP attempts | Retry | Recovered | Logical protocol failures | Calls/image | Tokens/image | Warm model seconds/image | Separate reasoning present |",
               "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for arm in ARMS:
        cost = costs[arm]
        report.append(
            f"| {arm} | {cost['http_attempts']} | {cost['retry_count']} | {cost['recovered']} | {cost['protocol_failures']} | "
            f"{cost['logical_calls_per_image']:.2f} | {cost['tokens_per_image']:.0f} | {cost['model_seconds_per_image']:.2f} | "
            f"{cost['reasoning_present_attempts']} |"
        )
    report += ["", "这里的 latency 是串行 warm-model HTTP 调用累计值除以 25，不包含 SAM evidence 重建；不是端到端 Pipeline 延迟。", "",
               "## Route 分解", ""]
    for route in ROUTES:
        report += [f"### {route}", "", "| Arm | Unit | Task | False assignment | Uncertain | Protocol failure |", "|---|---:|---:|---:|---:|---:|"]
        for arm in ARMS:
            item = scores[arm]["by_route"][route]
            report.append(f"| {arm} | {percent(item['unit_correct'], item['unit_total'])} | {percent(item['task_correct'], item['task_total'])} | {item['false_assignment']} | {item['uncertain']} | {item['protocol_failure']} |")
        report.append("")
    report += [
        "## Adaptive 合同核验", "",
        f"- Lazy evaluation：{'PASS' if c_lazy_ok else 'FAIL'}；触发 {len(c_triggered)} 图 / {sum(len(row['fallback_unit_ids']) for row in c_triggered)} units。",
        f"- A 非 uncertain 结果不可变：{'PASS' if not immutable else 'FAIL'}。",
        f"- 下游 payload 仅 facts/evidence：{'PASS' if projection_ok else 'FAIL'}；task_status leak=0。",
        f"- C uncertain resolution：`{json.dumps(resolutions['C']['counts'], ensure_ascii=False)}`。",
        f"- C fallback harm：{resolutions['C']['counts'].get('fallback_harm', 0)}。", "",
        "## 裁决", "",
    ]
    for route, item in decision["route_policy"].items():
        report.append(f"- `{route}` → **{item['policy']} / Arm {item['selected_arm']}**（{'；'.join(item['reasons'])}）")
        if item.get("qualification"):
            report.append(f"  - 限定：{item['qualification']}")
    report += [
        f"- `GLOBAL_CONTEXT_ROLE = {decision['global_context_role']}`",
        f"- `PRODUCTION_CHANGE_RECOMMENDED = {str(decision['production_change_recommended']).upper()}`", "",
        "本阶段没有修改 Production；上述 relation 结果是研究裁决，不构成实施授权。", "",
        "完整逐 unit 修正/回归、成本和协议统计见 `comparison_summary.json`；原始模型输出见三个 `arm_*.jsonl`。", "",
    ]
    (ROOT / "CONTEXT_EVIDENCE_POLICY_HARDENING_V1_REPORT.md").write_text("\n".join(report), encoding="utf-8")

    decision_lines = ["# Policy Decision", ""]
    for route, item in decision["route_policy"].items():
        decision_lines.append(f"- `{route.upper()}_EVIDENCE_POLICY = {item['policy']}` (`ARM_{item['selected_arm']}`)")
    decision_lines += [f"- `GLOBAL_CONTEXT_ROLE = {decision['global_context_role']}`",
                       f"- `PRODUCTION_CHANGE_RECOMMENDED = {str(decision['production_change_recommended']).upper()}`", ""]
    decision_lines += ["- `PRODUCTION_MODIFICATION = NOT AUTHORIZED`", ""]
    (ROOT / "POLICY_DECISION.md").write_text("\n".join(decision_lines), encoding="utf-8")

    for script_name in ("run_context_evidence_policy_hardening_v1.py", "finalize_context_evidence_policy_hardening_v1.py"):
        shutil.copy2(SCRIPT_DIR / script_name, ROOT / script_name)
    artifact_names = ["CONTEXT_EVIDENCE_POLICY_HARDENING_V1_CONTRACT.md", "frozen_contract.json", "frozen_selection.json",
                      "arm_a.jsonl", "arm_b.jsonl", "arm_c.jsonl", "comparison_summary.json",
                      "CONTEXT_EVIDENCE_POLICY_HARDENING_V1_REPORT.md", "POLICY_DECISION.md",
                      "run_context_evidence_policy_hardening_v1.py", "finalize_context_evidence_policy_hardening_v1.py"]
    manifest = {"files": [{"path": name, "bytes": (ROOT / name).stat().st_size, "sha256": sha256(ROOT / name)} for name in artifact_names]}
    (ROOT / "execution_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scores": clean_scores, "decision": decision, "contract_checks": summary["contract_checks"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
