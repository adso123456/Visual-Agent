"""为已完成但 System Gate 失败的 V3 批次生成只读执行审计材料。"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw_execution.jsonl"
MODEL = "qwen3.8:27b-mtp-q4_K_M"
BASE_URL = "http://192.168.250.9:11434/v1"


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    rows = [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != 140 or len({row["unit_id"] for row in rows}) != 140:
        raise RuntimeError("terminal execution units 不等于 140 个唯一单元")

    errors = [row for row in rows if row["terminal_status"] == "error"]
    successes = [row for row in rows if row["terminal_status"] == "success"]
    calls = [call for row in rows for call in row.get("vlm_calls", [])]
    leaves = [leaf for row in rows for leaf in protocol_leaves(row.get("qwen_protocol"))]

    error_classes = Counter()
    for row in errors:
        error = row.get("error", "")
        traceback_text = row.get("traceback", "")
        if row.get("error_type") == "InternalServerError" and "Error code: 502" in error:
            if "visual_agent\\vlm.py" in traceback_text:
                error_classes["local_vlm_http_502"] += 1
            elif "plan_request" in traceback_text:
                error_classes["local_agent_planner_http_502"] += 1
            else:
                error_classes["local_agent_http_502_other"] += 1
        elif "Final Response 返回了空内容" in error:
            error_classes["local_agent_final_response_empty"] += 1
        elif row.get("error_type") == "MemoryError":
            error_classes["evidence_memory_allocation_failure"] += 1
        elif "Planner" in error:
            error_classes["planner_contract_final_failure"] += 1
        else:
            error_classes["other"] += 1

    by_bucket = {}
    for bucket in ["CORE_CHALLENGE", "F1", "F2", "F3", "F4"]:
        selected = [
            row
            for row in rows
            if (bucket == "CORE_CHALLENGE" and row["suite"] in {"core", "challenge"})
            or row.get("prompt_id") == bucket
        ]
        by_bucket[bucket] = {
            "submitted": len(selected),
            "success": sum(row["terminal_status"] == "success" for row in selected),
            "error": sum(row["terminal_status"] == "error" for row in selected),
        }

    agent_provider_final_failures = (
        error_classes["local_agent_planner_http_502"]
        + error_classes["local_agent_http_502_other"]
    )
    summary = {
        "stage": "GENERAL_RGB_FINAL_ACCEPTANCE_V3",
        "implementation_head": "aed1e3e6acb537480664b89531a9bc12a29d708f",
        "final_decision": "FAIL",
        "system_gate": "FAIL",
        "visual_adjudication": "NOT_PERFORMED_SYSTEM_GATE_FAILED",
        "execution": {
            "submitted": 140,
            "terminal": len(rows),
            "pipeline_success": len(successes),
            "system_failure": len(errors),
            "result_json_present": sum(Path(row.get("result_json", "")).is_file() for row in rows),
            "result_image_present": sum(Path(row.get("result_image", "")).is_file() for row in rows),
            "agent_provider_final_failures": agent_provider_final_failures,
            "agent_final_response_contract_failures": error_classes[
                "local_agent_final_response_empty"
            ],
            "planner_contract_final_failures": error_classes["planner_contract_final_failure"],
            "vlm_provider_final_failures": error_classes["local_vlm_http_502"],
            "vlm_protocol_final_failures": 0,
            "vlm_validator_final_failures": 0,
            "evidence_final_failures": error_classes[
                "evidence_memory_allocation_failure"
            ],
            "error_classes": dict(error_classes),
            "by_bucket": by_bucket,
            "vlm_calls": len(calls),
            "unexpected_vlm_models": sum(call.get("model") != MODEL for call in calls),
            "unexpected_vlm_endpoints": sum(
                call.get("base_url", "").rstrip("/") != BASE_URL for call in calls
            ),
            "agent_model": MODEL,
            "agent_base_url": BASE_URL,
            "agent_provider": "openai_compatible",
            "vlm_model": MODEL,
            "vlm_base_url": BASE_URL,
            "protocol_attempts": sum(int(leaf.get("attempts") or 0) for leaf in leaves),
            "protocol_retries": sum(int(leaf.get("retry_count") or 0) for leaf in leaves),
            "protocol_recovered": sum(bool(leaf.get("recovered")) for leaf in leaves),
            "prompt_tokens": sum(int(call.get("prompt_tokens") or 0) for call in calls),
            "completion_tokens": sum(int(call.get("completion_tokens") or 0) for call in calls),
            "total_tokens": sum(int(call.get("total_tokens") or 0) for call in calls),
            "summed_end_to_end_seconds": round(
                sum(float(row["elapsed_seconds"]) for row in rows), 3
            ),
        },
        "failed_units": [
            {
                "unit_id": row["unit_id"],
                "error_type": row.get("error_type"),
                "error": row.get("error"),
            }
            for row in errors
        ],
        "audit_boundary": {
            "failed_execution_replacement": False,
            "terminal_results_overwritten": False,
            "production_modified_during_execution": False,
            "v1_evidence_modified": False,
        },
    }
    write_json(ROOT / "system_execution_summary.json", summary)

    report = [
        "# GENERAL_RGB_FINAL_ACCEPTANCE_V3 — Execution Report",
        "",
        "## Final status",
        "",
        "```text",
        "GENERAL_RGB_FINAL_ACCEPTANCE_V3 = FAIL",
        "SYSTEM_GATE = FAIL",
        "VISUAL_ADJUDICATION = NOT_PERFORMED_SYSTEM_GATE_FAILED",
        "PRODUCTION_MERGE = NOT_AUTHORIZED",
        "```",
        "",
        "## Execution facts",
        "",
        f"- Terminal：{len(rows)}/140。",
        f"- Pipeline success / SYSTEM FAILURE：{len(successes)} / {len(errors)}。",
        f"- Result JSON / image artifacts：{summary['execution']['result_json_present']} / {summary['execution']['result_image_present']}。",
        f"- Local Qwen Agent provider final failures：{agent_provider_final_failures}（Planner HTTP 502={error_classes['local_agent_planner_http_502']}）。",
        f"- Local Qwen Agent Final Response 空内容：{error_classes['local_agent_final_response_empty']}。",
        f"- Planner contract final failures：{error_classes['planner_contract_final_failure']}。",
        f"- Local VLM provider / protocol / validator final failures：{error_classes['local_vlm_http_502']} / 0 / 0。",
        f"- Evidence memory allocation failures：{error_classes['evidence_memory_allocation_failure']}。",
        f"- Local VLM calls：{len(calls)}；retry={summary['execution']['protocol_retries']}，recovered={summary['execution']['protocol_recovered']}。",
        f"- Agent / VLM：{MODEL} @ {BASE_URL}（openai_compatible）；执行前强制要求 DEEPSEEK_API_KEY 与 DASHSCOPE_API_KEY 均不存在。",
        f"- 累计端到端耗时：{summary['execution']['summed_end_to_end_seconds']} 秒。",
        "",
        "## Bucket execution",
        "",
        "| Bucket | Submitted | Success | Error |",
        "|---|---:|---:|---:|",
    ]
    for bucket, item in by_bucket.items():
        report.append(
            f"| {bucket} | {item['submitted']} | {item['success']} | {item['error']} |"
        )
    report.extend(
        [
            "",
            "## Audit decision",
            "",
            "本批次 140 个 terminal 结果全部保留，未补跑、未覆盖、未调参。由于 System Gate 已失败，不进行无法覆盖完整 denominator 的视觉质量裁决。",
            "",
        ]
    )
    (ROOT / "GENERAL_RGB_FINAL_ACCEPTANCE_V3_EXECUTION_REPORT.md").write_text(
        "\n".join(report), encoding="utf-8", newline="\n"
    )

    files = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.name == "artifact_manifest.json":
            continue
        files.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    write_json(ROOT / "artifact_manifest.json", {"file_count": len(files), "files": files})
    print(json.dumps({"final_decision": "FAIL", "system": summary["execution"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
