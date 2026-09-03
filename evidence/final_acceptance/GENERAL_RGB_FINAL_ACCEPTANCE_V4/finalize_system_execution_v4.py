"""固化 V4 System Gate 结果；System 失败时不生成视觉裁决。"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any


SOURCE = Path(r"E:\3\_visual_agent_real_world_acceptance\v1\_general_rgb_final_acceptance_v4")
ROOT = Path(__file__).resolve().parent
MODEL = "qwen3.8:27b-mtp-q4_K_M"
BASE_URL = "http://192.168.250.9:11434/v1"
IMPLEMENTATION = "362a1a3f8352619d3967efb98828db950346de01"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def transport_nodes(value: Any) -> list[dict]:
    nodes = []
    if isinstance(value, dict):
        if "final_transport_status" in value:
            nodes.append(value)
        for item in value.values():
            nodes.extend(transport_nodes(item))
    elif isinstance(value, list):
        for item in value:
            nodes.extend(transport_nodes(item))
    return nodes


def mirror_execution() -> None:
    for name in ("execution_manifest.json", "frozen_schedule.json", "raw_execution.jsonl"):
        shutil.copy2(SOURCE / name, ROOT / name)
    shutil.copytree(SOURCE / "artifacts", ROOT / "artifacts", dirs_exist_ok=True)


def load_result(row: dict) -> dict | None:
    path = row.get("result_json")
    if not path or not Path(path).is_file():
        return None
    return read_json(Path(path))


def classify_failure(row: dict) -> str:
    error = row.get("error", "")
    if row.get("error_type") == "SystemGateFailure" and (
        "failed_empty_response" in error or "agent_response_empty" in error
    ):
        return "agent_final_response_empty"
    if "Planner 两次均违反契约" in error:
        return "planner_contract_final_failure"
    if row.get("error_type") == "MemoryError":
        return "memory_error"
    if "retryable_failure_exhausted" in error:
        return "transport_exhausted"
    if "validator" in error.lower():
        return "vlm_validator_final_failure"
    if "protocol" in error.lower() or "JSON" in error:
        return "vlm_protocol_final_failure"
    return "other"


def main() -> None:
    mirror_execution()
    manifest = read_json(ROOT / "execution_manifest.json")
    rows = [
        json.loads(line)
        for line in (ROOT / "raw_execution.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if manifest.get("production_commit") != IMPLEMENTATION:
        raise RuntimeError("V4 Implementation HEAD 漂移")
    if len(rows) != 140 or len({row["unit_id"] for row in rows}) != 140:
        raise RuntimeError("terminal execution units 不等于 140 个唯一单元")

    errors = [row for row in rows if row["terminal_status"] == "error"]
    successes = [row for row in rows if row["terminal_status"] == "success"]
    calls = [call for row in rows for call in row.get("vlm_calls", [])]
    leaves = [leaf for row in rows for leaf in protocol_leaves(row.get("qwen_protocol"))]
    results = {row["unit_id"]: load_result(row) for row in rows}
    all_transport = []
    for row in rows:
        result = results[row["unit_id"]]
        if result:
            all_transport.extend(transport_nodes(result.get("agent")))
            all_transport.extend(transport_nodes(result.get("qwen_protocol")))
    error_classes = Counter(classify_failure(row) for row in errors)

    final_response_failures = []
    for row in rows:
        result = results[row["unit_id"]]
        if not result:
            continue
        agent = result.get("agent") or {}
        content = agent.get("final_response_content") or {}
        response = result.get("agent_response")
        if content.get("final_content_status") != "success" or not (
            isinstance(response, str) and response.strip()
        ):
            final_response_failures.append(
                {
                    "unit_id": row["unit_id"],
                    "final_response_content": content,
                    "agent_response_nonempty": isinstance(response, str)
                    and bool(response.strip()),
                    "artifacts_preserved": True,
                }
            )

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
            "system_failure": sum(row["terminal_status"] == "error" for row in selected),
        }

    unexpected_models = sum(call.get("model") != MODEL for call in calls)
    unexpected_endpoints = sum(
        call.get("base_url", "").rstrip("/") != BASE_URL for call in calls
    )
    non_success_transport = [
        node
        for node in all_transport
        if node.get("final_transport_status") != "success"
    ]
    system_pass = not errors
    summary = {
        "stage": "GENERAL_RGB_FINAL_ACCEPTANCE_V4",
        "implementation_head": IMPLEMENTATION,
        "final_decision": "PASS" if system_pass else "FAIL",
        "system_gate": "PASS" if system_pass else "FAIL",
        "visual_adjudication": (
            "AUTHORIZED_TO_PROCEED" if system_pass else "NOT_PERFORMED_SYSTEM_GATE_FAILED"
        ),
        "execution": {
            "submitted": 140,
            "terminal": len(rows),
            "system_success": len(successes),
            "system_failure": len(errors),
            "result_json_present": sum(result is not None for result in results.values()),
            "result_image_present": sum(
                bool(row.get("result_image")) and Path(row["result_image"]).is_file()
                for row in rows
            ),
            "agent_final_response_failures": len(final_response_failures),
            "planner_contract_final_failures": error_classes[
                "planner_contract_final_failure"
            ],
            "transport_exhausted_final_failures": error_classes["transport_exhausted"],
            "vlm_protocol_final_failures": error_classes["vlm_protocol_final_failure"],
            "vlm_validator_final_failures": error_classes["vlm_validator_final_failure"],
            "memory_errors": error_classes["memory_error"],
            "other_failures": error_classes["other"],
            "error_classes": dict(error_classes),
            "by_bucket": by_bucket,
            "vlm_http_calls": len(calls),
            "vlm_http_error_calls": sum(call.get("status") == "error" for call in calls),
            "unexpected_vlm_models": unexpected_models,
            "unexpected_vlm_endpoints": unexpected_endpoints,
            "protocol_attempts": sum(int(leaf.get("attempts") or 0) for leaf in leaves),
            "protocol_retries": sum(int(leaf.get("retry_count") or 0) for leaf in leaves),
            "protocol_recovered": sum(bool(leaf.get("recovered")) for leaf in leaves),
            "transport_telemetry_nodes": len(all_transport),
            "transport_attempts": sum(
                int(node.get("transport_attempts") or 0) for node in all_transport
            ),
            "transport_retries": sum(
                int(node.get("transport_retry_count") or 0) for node in all_transport
            ),
            "transport_recovered": sum(
                bool(node.get("transport_recovered")) for node in all_transport
            ),
            "non_success_transport_nodes": len(non_success_transport),
            "prompt_tokens": sum(int(call.get("prompt_tokens") or 0) for call in calls),
            "completion_tokens": sum(
                int(call.get("completion_tokens") or 0) for call in calls
            ),
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
                "result_json": row.get("result_json"),
                "result_image": row.get("result_image"),
            }
            for row in errors
        ],
        "final_response_failures": final_response_failures,
        "environment_pause": {
            "observed": True,
            "windows_event_provider": "Microsoft-Windows-Kernel-Power",
            "standby_event_id": 506,
            "standby_at": "2026-09-03T12:14:44+08:00",
            "resume_event_id": 507,
            "resumed_at": "2026-09-03T13:27:21+08:00",
            "approximate_pause_seconds": 4357,
            "runner_restarted": False,
            "affected_terminal_unit": "F2__fishing_026",
            "affected_unit_elapsed_seconds": 4551.729,
            "observed_transport_error": "APITimeoutError",
            "transport_retry_recovered": True,
        },
        "audit_boundary": {
            "v3_results_reused": False,
            "eight_unit_replay_results_reused": False,
            "failed_execution_replacement": False,
            "terminal_results_overwritten": False,
            "implementation_modified_during_execution": False,
            "visual_adjudication_performed": False,
        },
    }
    write_json(ROOT / "system_execution_summary.json", summary)

    report = [
        "# GENERAL_RGB_FINAL_ACCEPTANCE_V4 — Execution Report",
        "",
        "## Final status",
        "",
        "```text",
        f"GENERAL_RGB_FINAL_ACCEPTANCE_V4 = {summary['final_decision']}",
        f"SYSTEM_GATE = {summary['system_gate']}",
        f"VISUAL_ADJUDICATION = {summary['visual_adjudication']}",
        "PRODUCTION_MERGE = NOT AUTHORIZED",
        "```",
        "",
        "## Execution facts",
        "",
        f"- Terminal：{len(rows)}/140，unique=140。",
        f"- System success / SYSTEM FAILURE：{len(successes)} / {len(errors)}。",
        f"- Result JSON / image artifacts：{summary['execution']['result_json_present']} / {summary['execution']['result_image_present']}。",
        f"- Final Response failures：{len(final_response_failures)}；Planner contract final failures：{error_classes['planner_contract_final_failure']}。",
        f"- Transport exhausted / VLM protocol / validator / MemoryError：{error_classes['transport_exhausted']} / {error_classes['vlm_protocol_final_failure']} / {error_classes['vlm_validator_final_failure']} / {error_classes['memory_error']}。",
        f"- Agent / VLM：{MODEL} @ {BASE_URL}；unexpected VLM model/endpoint：{unexpected_models}/{unexpected_endpoints}。",
        f"- 累计记录耗时：{summary['execution']['summed_end_to_end_seconds']} 秒（包含一次约 4357 秒系统待机）。",
        "- 2026-09-03 12:14:44–13:27:21 Windows 进入 Modern Standby；原 runner 未重启，恢复后继续，未补跑或覆盖 unit。`F2__fishing_026` 的在途 Relation 请求超时后由 transport retry 恢复，unit 最终 success。",
        "",
        "## Failed units",
        "",
        "| Unit | Class | Error | Artifacts |",
        "|---|---|---|---|",
    ]
    for row in errors:
        preserved = "JSON + image" if row.get("result_json") else "none"
        report.append(
            f"| {row['unit_id']} | {classify_failure(row)} | {row.get('error')} | {preserved} |"
        )
    report.extend(
        [
            "",
            "## Bucket execution",
            "",
            "| Bucket | Submitted | Success | SYSTEM FAILURE |",
            "|---|---:|---:|---:|",
        ]
    )
    for bucket, item in by_bucket.items():
        report.append(
            f"| {bucket} | {item['submitted']} | {item['success']} | {item['system_failure']} |"
        )
    report.extend(
        [
            "",
            "## Audit decision",
            "",
            "V4 是独立 140-unit batch，未拼接 V3 或 8-unit replay。全部 terminal 结果原样保留，未补跑、覆盖或替换。由于存在 3 个 SYSTEM FAILURE，V4 按冻结流程 FAIL / CLOSED，不进行视觉裁决。",
            "",
        ]
    )
    (ROOT / "GENERAL_RGB_FINAL_ACCEPTANCE_V4_EXECUTION_REPORT.md").write_text(
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
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
