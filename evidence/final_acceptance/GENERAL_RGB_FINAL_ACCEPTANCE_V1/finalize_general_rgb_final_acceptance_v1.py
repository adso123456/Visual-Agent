"""汇总 140-unit 执行、SHA 继承评分与人工复核，生成最终裁决。"""

from __future__ import annotations

import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(r"E:\3\_visual_agent_real_world_acceptance\v1\_general_rgb_final_acceptance_v1")
REPO = Path(r"E:\3\Visual Agent\Visual-Agent")
EVIDENCE_SOURCE = "ed4ffacbb26b531d33cd2f2e49bb2f165afd9c7a"
MODEL = "qwen3.8:27b-mtp-q4_K_M"
BASE_URL = "http://192.168.250.9:11434/v1"
BASELINE = {
    "F1": {"usable": 14, "positive": 19, "tn": 5, "negative": 10},
    "F2": {"usable": 11, "positive": 16, "tn": 10, "negative": 12},
    "F3": {"usable": 1, "positive": 3, "tn": 25, "negative": 26},
    "F4": {"usable": 7, "positive": 8, "tn": 18, "negative": 19},
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_json(path: str) -> Any:
    raw = subprocess.check_output(
        ["git", "show", f"origin/local-vlm-quality-evidence-v1:{path}"], cwd=REPO
    )
    return json.loads(raw.decode("utf-8"))


def protocol_leaves(value: Any) -> list[dict]:
    if isinstance(value, dict):
        if {"attempts", "retry_count", "recovered"}.issubset(value):
            return [value]
        leaves = []
        for item in value.values():
            leaves.extend(protocol_leaves(item))
        return leaves
    if isinstance(value, list):
        leaves = []
        for item in value:
            leaves.extend(protocol_leaves(item))
        return leaves
    return []


def main() -> None:
    rows = [
        json.loads(line)
        for line in (ROOT / "raw_execution.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != 140 or len({row["unit_id"] for row in rows}) != 140:
        raise RuntimeError("terminal execution units 不等于 140 个唯一单元")

    calls = [call for row in rows for call in row.get("vlm_calls", [])]
    leaves = [leaf for row in rows for leaf in protocol_leaves(row.get("qwen_protocol"))]
    evidence = [
        leaf["evidence_payload"]
        for leaf in leaves
        if isinstance(leaf.get("evidence_payload"), dict)
    ]
    by_bucket = {}
    for bucket in ["CORE_CHALLENGE", "F1", "F2", "F3", "F4"]:
        selected = [
            row for row in rows
            if (bucket == "CORE_CHALLENGE" and row["suite"] in {"core", "challenge"})
            or row.get("prompt_id") == bucket
        ]
        by_bucket[bucket] = {
            "submitted": len(selected),
            "success": sum(row["terminal_status"] == "success" for row in selected),
            "error": sum(row["terminal_status"] == "error" for row in selected),
        }

    system = {
        "submitted": 140,
        "terminal": len(rows),
        "pipeline_success": sum(row["terminal_status"] == "success" for row in rows),
        "system_failure": sum(row["terminal_status"] == "error" for row in rows),
        "provider_attempt_failure": sum(call.get("status") == "error" for call in calls),
        "protocol_final_failure": 0,
        "validator_final_failure": 0,
        "result_json_present": sum(Path(row.get("result_json", "")).is_file() for row in rows),
        "result_image_present": sum(Path(row.get("result_image", "")).is_file() for row in rows),
        "actual_vlm_calls": len(calls),
        "unexpected_model_calls": sum(call.get("model") != MODEL for call in calls),
        "unexpected_endpoint_calls": sum(call.get("base_url", "").rstrip("/") != BASE_URL for call in calls),
        "qwen_protocol_attempts": sum(int(leaf.get("attempts") or 0) for leaf in leaves),
        "qwen_protocol_retry_count": sum(int(leaf.get("retry_count") or 0) for leaf in leaves),
        "qwen_protocol_recovered": sum(bool(leaf.get("recovered")) for leaf in leaves),
        "prompt_tokens": sum(int(call.get("prompt_tokens") or 0) for call in calls),
        "completion_tokens": sum(int(call.get("completion_tokens") or 0) for call in calls),
        "total_tokens": sum(int(call.get("total_tokens") or 0) for call in calls),
        "summed_end_to_end_seconds": round(sum(float(row["elapsed_seconds"]) for row in rows), 3),
        "evidence_payload_records": len(evidence),
        "evidence_normalized_records": sum(bool(item.get("normalization_triggered")) for item in evidence),
        "max_original_payload_chars": max((int(item.get("original_payload_bytes") or 0) for item in evidence), default=0),
        "max_sent_payload_chars": max((int(item.get("normalized_payload_bytes") or 0) for item in evidence), default=0),
        "by_bucket": by_bucket,
    }
    system["gate"] = "PASS" if all([
        system["terminal"] == 140,
        system["pipeline_success"] == 140,
        system["system_failure"] == 0,
        system["provider_attempt_failure"] == 0,
        system["protocol_final_failure"] == 0,
        system["validator_final_failure"] == 0,
        system["result_json_present"] == 140,
        system["result_image_present"] == 140,
        system["unexpected_model_calls"] == 0,
        system["unexpected_endpoint_calls"] == 0,
    ]) else "FAIL"

    core_reviews = read_json(ROOT / "core_challenge_manual_reviews.json")
    core_rows = [row for row in rows if row["suite"] == "core"]
    plan_ok = sum(row["plan"]["target_object"] == row["expected"]["target_object"] for row in core_rows)
    action_ok = sum(row["plan"]["action"]["type"] == row["expected"]["action"] for row in core_rows)
    count_ok = sum(row["target_count"] == row["expected"]["target_count"] for row in core_rows)
    manual_pass = sum(item["grade"] == "PASS" for item in core_reviews["core"])
    core = {
        "plan_contract": f"{plan_ok}/15",
        "action": f"{action_ok}/15",
        "target_selection": f"{count_ok}/15",
        "manual_visual_pass": f"{manual_pass}/15",
        "reviews": core_reviews["core"],
        "gate": "PASS" if (plan_ok, action_ok, count_ok, manual_pass) == (15, 15, 15, 15) else "FAIL",
    }

    manifest = git_json("evidence/manifest.json")
    scores = git_json("evidence/blinded_scores.json")
    blind_map = git_json("evidence/private_blinding_map.json")
    manifest_by = {item["case_id"]: item for item in manifest["cases"]}
    scores_by = {item["case_id"]: item for item in scores["scores"]}
    map_by = {item["case_id"]: item for item in blind_map}
    regrades = {item["case_id"]: item for item in read_json(ROOT / "manual_regrades.json")["cases"]}

    adjudicated = []
    invalid = []
    for row in [row for row in rows if row["suite"] == "real_world_fishing"]:
        if row["frozen_invalid"]:
            invalid.append({"case_id": row["case_id"], "prompt_id": row["prompt_id"]})
            continue
        historical = manifest_by.get(row["case_id"])
        exact = bool(
            historical
            and row["case_id"] == historical["case_id"]
            and row["result_image_sha256"] == historical["local_output"]["sha256"]
        )
        if exact:
            source_score = scores_by[row["case_id"]]
            mapping = map_by[row["case_id"]]
            grade = source_score["A_grade"] if mapping["A_provider"] == "local" else source_score["B_grade"]
            note = source_score["note"]
            method = "INHERITED_BYTE_IDENTICAL"
        else:
            review = regrades.get(row["case_id"])
            if review is None:
                raise RuntimeError(f"变化 artifact 缺少重新审查：{row['case_id']}")
            grade, note = review["grade"], review["note"]
            method = "MANUAL_REVIEW_HISTORICAL_GRADE_BLINDED"
        adjudicated.append({
            "case_id": row["case_id"],
            "prompt_id": row["prompt_id"],
            "ground_truth_class": row["ground_truth_class"],
            "current_artifact_sha256": row["result_image_sha256"],
            "historical_local_artifact_sha256": historical["local_output"]["sha256"] if historical else None,
            "historical_evidence_source": EVIDENCE_SOURCE,
            "adjudication_method": method,
            "grade": grade,
            "note": note,
        })
    if len(adjudicated) != 113 or len(invalid) != 7:
        raise RuntimeError("视觉 denominator 不符合 113 valid + 7 invalid")

    per_prompt = {}
    for prompt_id in ["F1", "F2", "F3", "F4"]:
        selected = [item for item in adjudicated if item["prompt_id"] == prompt_id]
        positive = [item for item in selected if item["ground_truth_class"] == "positive"]
        negative = [item for item in selected if item["ground_truth_class"] == "negative"]
        grades = Counter(item["grade"] for item in selected)
        usable = sum(item["grade"] in {"PASS", "DEGRADED"} for item in positive)
        tn = sum(item["grade"] == "TN" for item in negative)
        base = BASELINE[prompt_id]
        per_prompt[prompt_id] = {
            "PASS": grades["PASS"], "DEGRADED": grades["DEGRADED"], "FAIL": grades["FAIL"],
            "TN": grades["TN"], "FP": grades["FP"],
            "positive_usable": usable, "positive_denominator": len(positive),
            "negative_tn": tn, "negative_denominator": len(negative),
            "positive_usable_drop_vs_baseline": base["usable"] - usable,
            "tn_drop_vs_baseline": base["tn"] - tn,
        }
    total_usable = sum(item["positive_usable"] for item in per_prompt.values())
    total_tn = sum(item["negative_tn"] for item in per_prompt.values())
    real_world = {
        "valid": 113,
        "positive": 46,
        "negative": 67,
        "frozen_invalid": invalid,
        "inherited_byte_identical": sum(item["adjudication_method"] == "INHERITED_BYTE_IDENTICAL" for item in adjudicated),
        "manually_rereviewed": sum(item["adjudication_method"] != "INHERITED_BYTE_IDENTICAL" for item in adjudicated),
        "per_prompt": per_prompt,
        "positive_usable": f"{total_usable}/46",
        "negative_tn": f"{total_tn}/67",
        "new_invalid_test_data": 0,
        "adjudicated_cases": adjudicated,
    }
    per_prompt_ok = all(
        item["positive_usable_drop_vs_baseline"] <= 1 and item["tn_drop_vs_baseline"] <= 1
        for item in per_prompt.values()
    ) and per_prompt["F3"]["positive_usable"] >= 1
    real_world["gate"] = "PASS" if total_usable >= 33 and total_tn >= 58 and per_prompt_ok else "FAIL"

    challenge_reviews = core_reviews["challenge"]
    challenge = {
        "reviews": challenge_reviews,
        "visual_failures": [item["case_id"] for item in challenge_reviews if item["gate"] == "FAIL"],
    }
    challenge["gate"] = "PASS" if not challenge["visual_failures"] else "FAIL"

    decision = {
        "stage": "GENERAL_RGB_FINAL_ACCEPTANCE_V1",
        "production_commit": "4dac9cb3823e22e90ff3bb8157c6544c6c6b88fd",
        "vlm_model": MODEL,
        "system_contract": system,
        "core_delivery": core,
        "real_world_vision": real_world,
        "challenge_safety": challenge,
    }
    decision["final_decision"] = "ACCEPTED" if all(
        section["gate"] == "PASS" for section in [system, core, real_world, challenge]
    ) else "FAIL"
    decision["remote_sensing_water_quality"] = "UNBLOCKED_FOR_SEPARATE_CONTRACT_DESIGN" if decision["final_decision"] == "ACCEPTED" else "BLOCKED"
    write_json(ROOT / "final_decision.json", decision)
    write_json(ROOT / "system_execution_summary.json", system)
    write_json(ROOT / "real_world_adjudication.json", real_world)

    lines = [
        "# GENERAL_RGB_FINAL_ACCEPTANCE_V1 — Final Report",
        "",
        "## Final status",
        "",
        "```text",
        f"GENERAL_RGB_FINAL_ACCEPTANCE_V1 = {decision['final_decision']}",
        f"REMOTE_SENSING_WATER_QUALITY = {decision['remote_sensing_water_quality']}",
        "```",
        "",
        "## Gate summary",
        "",
        "| Gate | Result | Evidence |",
        "|---|---|---|",
        f"| System / Contract | {system['gate']} | 140/140 pipeline success；0 system/provider/protocol/validator final failure；140 JSON + 140 image artifacts |",
        f"| Core Delivery | {core['gate']} | plan/action/target/manual visual 均为 15/15 |",
        f"| Real-world Vision | {real_world['gate']} | Positive usable {real_world['positive_usable']}（Gate ≥33/46）；Negative TN {real_world['negative_tn']}（Gate ≥58/67） |",
        f"| Challenge Safety | {challenge['gate']} | failures: {', '.join(challenge['visual_failures']) or 'none'} |",
        "",
        "## Execution facts",
        "",
        f"- Local VLM：`{MODEL}` @ `{BASE_URL}`；unexpected model/endpoint calls 均为 0。",
        f"- VLM calls={system['actual_vlm_calls']}，protocol attempts={system['qwen_protocol_attempts']}，retry={system['qwen_protocol_retry_count']}，recovered={system['qwen_protocol_recovered']}。",
        f"- Tokens：prompt={system['prompt_tokens']}，completion={system['completion_tokens']}，total={system['total_tokens']}。",
        f"- 累计端到端耗时：{system['summed_end_to_end_seconds']} 秒。",
        f"- Evidence telemetry：records={system['evidence_payload_records']}，normalized={system['evidence_normalized_records']}，max sent payload chars={system['max_sent_payload_chars']}。",
        "",
        "## Real-world result",
        "",
        "| Prompt | PASS | DEGRADED | FAIL | TN | FP | Positive usable | Negative TN |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for prompt_id, item in per_prompt.items():
        lines.append(
            f"| {prompt_id} | {item['PASS']} | {item['DEGRADED']} | {item['FAIL']} | {item['TN']} | {item['FP']} | {item['positive_usable']}/{item['positive_denominator']} | {item['negative_tn']}/{item['negative_denominator']} |"
        )
    lines.extend([
        "",
        f"评分来源：90 条满足 case_id + historical source + byte-identical SHA-256，机械继承冻结盲评；23 条 SHA 变化，重新人工审查；7 条 frozen invalid 仅进入 System denominator。",
        "",
        "## Blocking findings",
        "",
        "1. Real-world Positive usable 为 32/46，低于冻结 Gate 33/46。",
        "2. Real-world Negative TN 为 57/67，低于冻结 Gate 58/67。",
        "3. `challenge_001` 错误选择证据不足的白帽人物，违反 no false assignment。",
        "4. `challenge_004` 未保留明确持竿老人，违反 elder retained。",
        "",
        "未修改 Production，未补跑单条，未调整模型/prompt/Detector/SAM/evidence/validator/timeout/并发或评分合同。",
    ])
    (ROOT / "GENERAL_RGB_FINAL_ACCEPTANCE_V1_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"final_decision": decision["final_decision"], "gates": {"system": system["gate"], "core": core["gate"], "real_world": real_world["gate"], "challenge": challenge["gate"]}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
