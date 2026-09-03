"""回放 V3 的 8 个原始 SYSTEM FAILURE；每个 unit 只执行一次。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any


PROJECT = Path(r"E:\3\Visual Agent\_execution_robustness_v1")
ACCEPTANCE_ROOT = Path(r"E:\3\_visual_agent_real_world_acceptance\v1")
V3_OUTPUT = ACCEPTANCE_ROOT / "_general_rgb_final_acceptance_v3"
OUTPUT = ACCEPTANCE_ROOT / "_general_rgb_execution_robustness_v1_8_unit_replay"
EXPECTED_COMMIT = "362a1a3f8352619d3967efb98828db950346de01"
EXPECTED_MODEL = "qwen3.8:27b-mtp-q4_K_M"
EXPECTED_BASE_URL = "http://192.168.250.9:11434/v1"
EXPECTED_V3_SCHEDULE_SHA256 = (
    "0a5b7c5dabafe9b1c9a9a4be65693824dff79e3b71481ebe0cb93b610960f253"
)
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def assert_frozen_environment() -> None:
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--short"], cwd=PROJECT, text=True
    ).strip()
    if head != EXPECTED_COMMIT:
        raise RuntimeError(f"Implementation commit 漂移：{head}")
    if status:
        raise RuntimeError(f"Implementation worktree 非 clean：\n{status}")

    schedule_path = V3_OUTPUT / "frozen_schedule.json"
    if sha256(schedule_path) != EXPECTED_V3_SCHEDULE_SHA256:
        raise RuntimeError("V3 frozen_schedule.json SHA-256 漂移")

    effective = {
        "VLM_MODEL": os.environ.get("VLM_MODEL"),
        "VLM_BASE_URL": os.environ.get("VLM_BASE_URL"),
        "VLM_API_KEY": os.environ.get("VLM_API_KEY"),
        "VLM_TIMEOUT": os.environ.get("VLM_TIMEOUT"),
        "PLANNER_MODEL": os.environ.get("PLANNER_MODEL"),
        "PLANNER_BASE_URL": os.environ.get("PLANNER_BASE_URL"),
        "PLANNER_API_KEY": os.environ.get("PLANNER_API_KEY"),
        "DEEPSEEK_API_KEY_present": bool(os.environ.get("DEEPSEEK_API_KEY")),
        "DASHSCOPE_API_KEY_present": bool(os.environ.get("DASHSCOPE_API_KEY")),
    }
    expected = {
        "VLM_MODEL": EXPECTED_MODEL,
        "VLM_BASE_URL": EXPECTED_BASE_URL,
        "VLM_API_KEY": "ollama",
        "VLM_TIMEOUT": "120",
        "PLANNER_MODEL": EXPECTED_MODEL,
        "PLANNER_BASE_URL": EXPECTED_BASE_URL,
        "PLANNER_API_KEY": "ollama",
        "DEEPSEEK_API_KEY_present": False,
        "DASHSCOPE_API_KEY_present": False,
    }
    if effective != expected:
        raise RuntimeError(f"Local Qwen Agent/VLM 环境不符合冻结条件：{effective}")


def build_schedule() -> list[dict]:
    rows = read_json(V3_OUTPUT / "frozen_schedule.json")
    by_id = {row["unit_id"]: row for row in rows}
    if any(unit_id not in by_id for unit_id in UNIT_IDS):
        raise RuntimeError("V3 冻结清单缺少目标 unit")
    schedule = [by_id[unit_id] for unit_id in UNIT_IDS]
    if [row["unit_id"] for row in schedule] != UNIT_IDS:
        raise RuntimeError("8-unit 顺序漂移")
    for row in schedule:
        image_path = Path(row["image_path"])
        if sha256(image_path) != row["image_sha256"]:
            raise RuntimeError(f"输入图像 SHA-256 漂移：{row['unit_id']}")
    return schedule


def append_terminal(row: dict) -> None:
    path = OUTPUT / "raw_execution.jsonl"
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def transport_from_exception(exc: Exception) -> dict | None:
    value = getattr(exc, "transport_telemetry", None)
    return value if isinstance(value, dict) else None


def execute(schedule: list[dict]) -> None:
    if str(PROJECT) not in sys.path:
        sys.path.insert(0, str(PROJECT))
    from visual_agent.pipeline import run_pipeline

    for replay_ordinal, item in enumerate(schedule, start=1):
        unit_id = item["unit_id"]
        print(f"START [{replay_ordinal}/8] {unit_id}", flush=True)
        started = time.perf_counter()
        case_output = OUTPUT / "artifacts" / unit_id
        try:
            case_output.mkdir(parents=True, exist_ok=False)
            image_output, json_output = run_pipeline(
                Path(item["image_path"]), item["prompt"], output_dir=case_output
            )
            result = read_json(json_output)
            row = {
                **item,
                "replay_ordinal": replay_ordinal,
                "terminal_status": "success",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "result_json": str(json_output),
                "result_json_sha256": sha256(json_output),
                "result_image": str(image_output),
                "result_image_sha256": sha256(image_output),
                "result_image_bytes": image_output.stat().st_size,
                "plan": result.get("plan"),
                "candidate_count": len(result.get("candidates", [])),
                "target_count": len(result.get("targets", [])),
                "agent": result.get("agent"),
                "agent_response": result.get("agent_response"),
                "qwen_protocol": result.get("qwen_protocol"),
                "relation_hand_fallback": result.get("relation_hand_fallback"),
                "timings": result.get("timings"),
            }
        except Exception as exc:
            row = {
                **item,
                "replay_ordinal": replay_ordinal,
                "terminal_status": "error",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "transport_telemetry": transport_from_exception(exc),
                "traceback": traceback.format_exc(),
            }
        append_terminal(row)
        print(
            f"DONE  [{replay_ordinal}/8] {unit_id} {row['terminal_status']} "
            f"{row['elapsed_seconds']}s targets={row.get('target_count', 0)}",
            flush=True,
        )


def main() -> None:
    assert_frozen_environment()
    schedule = build_schedule()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    write_json(OUTPUT / "frozen_schedule.json", schedule)
    write_json(
        OUTPUT / "execution_manifest.json",
        {
            "stage": "GENERAL_RGB_EXECUTION_ROBUSTNESS_V1_8_UNIT_REPLAY",
            "implementation_commit": EXPECTED_COMMIT,
            "source_schedule": str(V3_OUTPUT / "frozen_schedule.json"),
            "source_schedule_sha256": EXPECTED_V3_SCHEDULE_SHA256,
            "scheduled_units": len(schedule),
            "single_attempt_per_unit": True,
            "replacement_runs_allowed": False,
            "agent_model": EXPECTED_MODEL,
            "agent_base_url": EXPECTED_BASE_URL,
            "vlm_model": EXPECTED_MODEL,
            "vlm_base_url": EXPECTED_BASE_URL,
            "vlm_timeout_seconds": 120,
            "concurrency": 1,
            "visual_quality_adjudication": False,
        },
    )
    execute(schedule)


if __name__ == "__main__":
    main()
