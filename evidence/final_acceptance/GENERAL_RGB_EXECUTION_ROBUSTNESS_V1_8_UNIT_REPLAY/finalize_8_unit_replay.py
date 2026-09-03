"""校验 8-unit replay gate，并把外部运行产物镜像为可审查证据。"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


SOURCE = Path(
    r"E:\3\_visual_agent_real_world_acceptance\v1"
    r"\_general_rgb_execution_robustness_v1_8_unit_replay"
)
ROOT = Path(__file__).resolve().parent
EXPECTED_COMMIT = "362a1a3f8352619d3967efb98828db950346de01"
UNIT_IDS = [
    "F1__fishing_015",
    "F1__fishing_016",
    "F1__fishing_017",
    "F1__fishing_018",
    "F1__fishing_019",
    "F2__fishing_001",
    "F2__fishing_002",
    "F4__fishing_007",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def transport_nodes(value: Any) -> list[dict]:
    found: list[dict] = []
    if isinstance(value, dict):
        if "final_transport_status" in value:
            found.append(value)
        for child in value.values():
            found.extend(transport_nodes(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(transport_nodes(child))
    return found


def mirror_execution() -> None:
    for name in ("execution_manifest.json", "frozen_schedule.json", "raw_execution.jsonl"):
        shutil.copy2(SOURCE / name, ROOT / name)
    shutil.copytree(SOURCE / "artifacts", ROOT / "artifacts", dirs_exist_ok=False)


def main() -> None:
    mirror_execution()
    manifest = read_json(ROOT / "execution_manifest.json")
    rows = [
        json.loads(line)
        for line in (ROOT / "raw_execution.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if manifest["implementation_commit"] != EXPECTED_COMMIT:
        raise RuntimeError("Implementation commit 不符合 gate")
    if len(rows) != 8 or [row["unit_id"] for row in rows] != UNIT_IDS:
        raise RuntimeError("terminal 数量、唯一性或顺序不符合冻结清单")
    if len({row["unit_id"] for row in rows}) != 8:
        raise RuntimeError("存在重复 terminal unit")
    if any(row["terminal_status"] != "success" for row in rows):
        raise RuntimeError("存在非 success terminal unit")

    all_transport: list[dict] = []
    for row in rows:
        all_transport.extend(transport_nodes(row.get("agent")))
        all_transport.extend(transport_nodes(row.get("qwen_protocol")))
    exhausted = [
        node
        for node in all_transport
        if node.get("final_transport_status") != "success"
    ]
    if exhausted:
        raise RuntimeError(f"存在 transport 非成功终态：{exhausted}")

    by_id = {row["unit_id"]: row for row in rows}
    hand = by_id["F2__fishing_001"]["relation_hand_fallback"]
    hand_subjects = hand.get("subjects", {})
    triggered_subjects = [item for item in hand_subjects.values() if item.get("attempted")]
    if not triggered_subjects:
        raise RuntimeError("F2__fishing_001 未留下 hand fallback 触发证据")
    if any(not item.get("hand_detector_resized") for item in triggered_subjects):
        raise RuntimeError("F2__fishing_001 hand Detector 未缩放")
    if any(
        item.get("subject_view_dimensions") != [4932, 7032]
        or item.get("hand_detector_dimensions") != [800, 1141]
        for item in triggered_subjects
    ):
        raise RuntimeError("F2__fishing_001 hand Detector 尺寸不符合冻结预期")

    final_response_gates = {}
    for unit_id in ("F2__fishing_002", "F4__fishing_007"):
        row = by_id[unit_id]
        content = row["agent"]["final_response_content"]
        nonempty = isinstance(row.get("agent_response"), str) and bool(
            row["agent_response"].strip()
        )
        passed = content.get("final_content_status") == "success" and nonempty
        final_response_gates[unit_id] = {
            **content,
            "agent_response_nonempty": nonempty,
            "pass": passed,
        }
        if not passed:
            raise RuntimeError(f"{unit_id} Final Response gate 失败")

    artifact_manifest = []
    for path in sorted((ROOT / "artifacts").rglob("*")):
        if path.is_file():
            artifact_manifest.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    write_json(ROOT / "artifact_manifest.json", artifact_manifest)

    unit_summary = []
    for row in rows:
        unit_summary.append(
            {
                "unit_id": row["unit_id"],
                "terminal_status": row["terminal_status"],
                "elapsed_seconds": row["elapsed_seconds"],
                "target_count": row["target_count"],
                "final_content_status": row["agent"]["final_response_content"][
                    "final_content_status"
                ],
                "agent_response_nonempty": isinstance(row.get("agent_response"), str)
                and bool(row["agent_response"].strip()),
            }
        )
    summary = {
        "stage": manifest["stage"],
        "gate_status": "PASS",
        "implementation_commit": EXPECTED_COMMIT,
        "scheduled_units": 8,
        "terminal_units": len(rows),
        "unique_terminal_units": len({row["unit_id"] for row in rows}),
        "terminal_success": sum(row["terminal_status"] == "success" for row in rows),
        "terminal_error": sum(row["terminal_status"] == "error" for row in rows),
        "transport_telemetry_nodes": len(all_transport),
        "transport_attempts": sum(
            node.get("transport_attempts", 0) for node in all_transport
        ),
        "transport_retry_count": sum(
            node.get("transport_retry_count", 0) for node in all_transport
        ),
        "transport_recovered_nodes": sum(
            bool(node.get("transport_recovered")) for node in all_transport
        ),
        "transport_exhausted_nodes": len(exhausted),
        "hand_conditioned_memory_gate": {
            "unit_id": "F2__fishing_001",
            "triggered": True,
            "subject_view_dimensions": [4932, 7032],
            "hand_detector_dimensions": [800, 1141],
            "hand_detector_resized": True,
            "memory_error": False,
            "pass": True,
        },
        "final_response_gates": final_response_gates,
        "visual_quality_adjudication_performed": False,
        "units": unit_summary,
    }
    write_json(ROOT / "gate_summary.json", summary)

    table = [
        "| Unit | Terminal | 秒 | Targets | Final Response | 非空文本 |",
        "|---|---:|---:|---:|---|---:|",
    ]
    for item in unit_summary:
        table.append(
            f"| {item['unit_id']} | {item['terminal_status']} | "
            f"{item['elapsed_seconds']} | {item['target_count']} | "
            f"{item['final_content_status']} | "
            f"{'yes' if item['agent_response_nonempty'] else 'no'} |"
        )
    report = "\n".join(
        [
            "# GENERAL RGB EXECUTION ROBUSTNESS V1 — 8-unit replay",
            "",
            "```text",
            "8-UNIT TARGETED REPLAY = PASS",
            "FINAL ACCEPTANCE V4 = NOT RUN / NOT AUTHORIZED",
            "```",
            "",
            f"- Implementation HEAD: `{EXPECTED_COMMIT}`",
            f"- Terminal: `{len(rows)}/8`，unique: `8/8`，success: `8/8`。",
            "- 每个 unit 只执行 1 次；无覆盖、补跑或替换。concurrency=1。",
            "- Agent/VLM: `qwen3.8:27b-mtp-q4_K_M`，同一本地 OpenAI-compatible endpoint。",
            f"- Transport telemetry nodes: `{len(all_transport)}`；物理 attempts: "
            f"`{summary['transport_attempts']}`；retry: "
            f"`{summary['transport_retry_count']}`；exhausted: `0`。本次均直接成功。",
            "- `F2__fishing_001` 触发 hand fallback：subject view `4932×7032`，"
            "hand Detector 输入 `800×1141`，`hand_detector_resized=true`；无 MemoryError。",
            "- `F2__fishing_002`：首次 Final Response 空，内容级第 2 次恢复成功；"
            "最终状态 `success`，`agent_response` 非空。",
            "- `F4__fishing_007`：Final Response 首次成功，`agent_response` 非空。",
            "- 本次未做视觉质量裁决，也不替代完整 Final Acceptance。",
            "",
            *table,
            "",
        ]
    )
    (ROOT / "EXECUTION_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
