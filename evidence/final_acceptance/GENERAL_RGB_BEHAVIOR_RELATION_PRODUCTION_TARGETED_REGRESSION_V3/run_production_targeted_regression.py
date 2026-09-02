"""在已审 Production candidate 上执行冻结 Behavior + Relation targeted regression。

这是执行脚本，不是新合同；只调用正式 run_pipeline()，输出位于项目 worktree 外。
"""

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


PROJECT = Path(r"E:\3\Visual Agent\_implementation_worktree")
ACCEPTANCE = Path(r"E:\3\_visual_agent_real_world_acceptance\v1")
FINAL_V1 = ACCEPTANCE / "_general_rgb_final_acceptance_v1"
OUTPUT = ACCEPTANCE / "general_rgb_behavior_relation_production_targeted_regression_v3"
EXPECTED_HEAD = "aed1e3e6acb537480664b89531a9bc12a29d708f"
EXPECTED_MODEL = "qwen3.8:27b-mtp-q4_K_M"
EXPECTED_BASE_URL = "http://192.168.250.9:11434/v1"

BEHAVIOR = [
    ("challenge_001", "179af15ea7f004631e99d0906e3542f81982760cc81b7320112847b54af4827c", ".jpg", 5),
    ("challenge_003", "717bf5c5f7d7509ccbc65a26fd814a58fa3b734c88f5016190f621faa802e4b6", ".png", 5),
    ("challenge_004", "45cc200746762868a2a51afafa362fb212cbfbeaa350f523f7d0a353aa044a79", ".png", 5),
    ("F1::fishing_001.jpeg", "459b89b0993cb0227aa528695ef1ef1f906507f57af5ad222ebab9ea0df9ecab", ".jpeg", 1),
    ("F1::fishing_005.jpeg", "98eba2196eef4ae557b3efb213d45adf7f3948524a60b0b9ac45ce214a3c5145", ".jpeg", 1),
    ("F1::fishing_010.jpeg", "acaa943cb04cf5a94bdf56632add1b324dbc46f9354a0b774e837936ac4653f4", ".jpeg", 1),
    ("F1::fishing_014.jpeg", "8e04ceaa925594739664cc49e1908ff2f94ba48f82badfb83592c3c5ebad7355", ".jpeg", 1),
    ("F1::fishing_004.jpeg", "b79fef93535b1eee45c9355135b3e8053a8bb0fd94be3031832e024bce0e34a9", ".jpeg", 1),
    ("F1::fishing_018.jpeg", "3db8bbbac9b1bb2c153a5194625c0121b731afea11ad94ce475605ac5673be4e", ".jpeg", 1),
]

RELATION = [
    ("F4::fishing_017.jpeg", "2ca02d15f8799d620598751ef299851915f91fe094d863a5f7cf51f6b50f0c99", ".jpeg", 5),
    ("F2::fishing_005.jpeg", "98eba2196eef4ae557b3efb213d45adf7f3948524a60b0b9ac45ce214a3c5145", ".jpeg", 5),
    ("F2::fishing_024.jpeg", "f70b44333494c9788b0747ac78847a3a8ed67692b1ff1b0edcdc6d15b32d60c6", ".jpeg", 1),
    ("core_003", "5fc835cd84d2acf4d24c15dba16d2f706df71f02cf28e3927ee2e5c7b78db4f0", ".jpg", 1),
    ("core_014", "9eeaa87013b4e800930e8a411b58ff9e2fd5383906b1a022f4a712720af34cc2", ".jpg", 1),
]

CURRENT_VLM_CALLS: list[dict] = []


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def artifact_unit(case_id: str) -> str:
    if "::" not in case_id:
        return case_id
    prompt_id, filename = case_id.split("::", 1)
    return f"{prompt_id}__{Path(filename).stem}"


def frozen_plan(case_id: str) -> tuple[str, dict]:
    source = FINAL_V1 / "artifacts" / artifact_unit(case_id) / "result_001.json"
    data = read_json(source)
    return data["prompt"], data["plan"]


def assert_preflight() -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--short"], cwd=PROJECT, text=True).strip()
    if head != EXPECTED_HEAD:
        raise RuntimeError(f"Implementation HEAD 漂移：{head}")
    if status:
        raise RuntimeError(f"Implementation worktree 非 clean：\n{status}")
    effective = {
        "VLM_MODEL": os.environ.get("VLM_MODEL"),
        "VLM_BASE_URL": os.environ.get("VLM_BASE_URL"),
        "VLM_API_KEY": os.environ.get("VLM_API_KEY"),
        "VLM_TIMEOUT": os.environ.get("VLM_TIMEOUT"),
    }
    expected = {
        "VLM_MODEL": EXPECTED_MODEL,
        "VLM_BASE_URL": EXPECTED_BASE_URL,
        "VLM_API_KEY": "ollama",
        "VLM_TIMEOUT": "120",
    }
    if effective != expected:
        raise RuntimeError(f"Local VLM 配置漂移：{effective}")


def build_schedule() -> list[dict]:
    schedule = []
    for component, definitions in (("behavior", BEHAVIOR), ("relation", RELATION)):
        for case_id, image_sha, suffix, repetitions in definitions:
            image_path = FINAL_V1 / "inputs" / "by_sha256" / f"{image_sha}{suffix}"
            if not image_path.is_file() or sha256(image_path) != image_sha:
                raise RuntimeError(f"冻结输入缺失或 SHA 漂移：{case_id} {image_path}")
            prompt, plan = frozen_plan(case_id)
            for repetition in range(1, repetitions + 1):
                schedule.append(
                    {
                        "ordinal": len(schedule) + 1,
                        "component": component,
                        "case_id": case_id,
                        "repetition": repetition,
                        "slot_id": f"{component.upper()}|{case_id}|r{repetition}",
                        "prompt": prompt,
                        "plan": plan,
                        "image_path": str(image_path),
                        "image_sha256": image_sha,
                    }
                )
    if len(schedule) != 34:
        raise RuntimeError(f"targeted schedule 应为 34 次 pipeline execution，实际 {len(schedule)}")
    return schedule


class InstrumentedCompletions:
    def __init__(self, inner: Any, route: str, base_url: str):
        self.inner = inner
        self.route = route
        self.base_url = base_url

    def create(self, *args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            response = self.inner.create(*args, **kwargs)
        except Exception as exc:
            CURRENT_VLM_CALLS.append(
                {"route": self.route, "model": kwargs.get("model"), "base_url": self.base_url,
                 "status": "error", "elapsed_seconds": round(time.perf_counter() - started, 4),
                 "error_type": type(exc).__name__, "error": str(exc)}
            )
            raise
        usage = getattr(response, "usage", None)
        CURRENT_VLM_CALLS.append(
            {"route": self.route, "model": kwargs.get("model"), "base_url": self.base_url,
             "status": "success", "elapsed_seconds": round(time.perf_counter() - started, 4),
             "prompt_tokens": getattr(usage, "prompt_tokens", None),
             "completion_tokens": getattr(usage, "completion_tokens", None),
             "total_tokens": getattr(usage, "total_tokens", None)}
        )
        return response


class InstrumentedClient:
    def __init__(self, inner: Any, route: str, base_url: str):
        completions = InstrumentedCompletions(inner.chat.completions, route, base_url)
        self.chat = type("InstrumentedChat", (), {"completions": completions})()


def install_vlm_observer() -> None:
    import visual_agent.relations as relations
    import visual_agent.vlm as vlm
    from visual_agent.vlm_client import create_vlm_client, load_vlm_config

    def factory(route: str):
        def create():
            config = load_vlm_config()
            return InstrumentedClient(create_vlm_client(config), route, config.base_url)
        return create

    vlm.create_vlm_client = factory("vlm")
    relations.create_vlm_client = factory("relations")


def terminal_ids() -> set[str]:
    raw = OUTPUT / "raw_execution.jsonl"
    if not raw.exists():
        return set()
    rows = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [row["slot_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("raw_execution.jsonl 存在重复 terminal slot")
    return set(ids)


def append_terminal(row: dict) -> None:
    with (OUTPUT / "raw_execution.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def execute(schedule: list[dict]) -> None:
    if str(PROJECT) not in sys.path:
        sys.path.insert(0, str(PROJECT))
    from visual_agent.pipeline import run_pipeline

    install_vlm_observer()
    completed = terminal_ids()
    for item in schedule:
        if item["slot_id"] in completed:
            print(f"SKIP [{item['ordinal']}/34] {item['slot_id']}", flush=True)
            continue
        print(f"START [{item['ordinal']}/34] {item['slot_id']}", flush=True)
        CURRENT_VLM_CALLS.clear()
        started = time.perf_counter()
        case_dir = OUTPUT / "artifacts" / item["slot_id"].replace(":", "_").replace("|", "_")
        case_dir.mkdir(parents=True, exist_ok=False)
        try:
            image_output, json_output = run_pipeline(
                Path(item["image_path"]), item["prompt"], plan=item["plan"],
                verify=True, final_response=False, output_dir=case_dir,
            )
            result = read_json(json_output)
            row = {
                **item,
                "terminal_status": "success",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "result_json": str(json_output),
                "result_json_sha256": sha256(json_output),
                "result_image": str(image_output),
                "result_image_sha256": sha256(image_output),
                "candidate_count": len(result.get("candidates", [])),
                "target_count": len(result.get("targets", [])),
                "candidates": result.get("candidates", []),
                "behavior_routing": result.get("behavior_routing"),
                "relation_hand_fallback": result.get("relation_hand_fallback"),
                "relation_bindings": result.get("relation_bindings"),
                "qwen_protocol": result.get("qwen_protocol"),
                "timings": result.get("timings"),
                "vlm_calls": list(CURRENT_VLM_CALLS),
            }
        except Exception as exc:
            row = {
                **item,
                "terminal_status": "error",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "vlm_calls": list(CURRENT_VLM_CALLS),
            }
        append_terminal(row)
        completed.add(item["slot_id"])
        print(
            f"DONE  [{item['ordinal']}/34] {item['slot_id']} {row['terminal_status']} "
            f"{row['elapsed_seconds']}s targets={row.get('target_count', 0)} "
            f"vlm_calls={len(CURRENT_VLM_CALLS)}",
            flush=True,
        )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    assert_preflight()
    schedule = build_schedule()
    schedule_path = OUTPUT / "frozen_execution_schedule.json"
    if schedule_path.exists() and read_json(schedule_path) != schedule:
        raise RuntimeError("既有执行 schedule 与当前不一致")
    if not schedule_path.exists():
        write_json(schedule_path, schedule)
    write_json(
        OUTPUT / "execution_manifest.json",
        {"stage": "GENERAL_RGB_BEHAVIOR_RELATION_PRODUCTION_TARGETED_REGRESSION_V3",
         "implementation_head": EXPECTED_HEAD, "model": EXPECTED_MODEL,
         "base_url": EXPECTED_BASE_URL, "timeout_seconds": 120, "concurrency": 1,
         "pipeline_executions": 34, "behavior_executions": 21,
         "relation_executions": 13, "failed_execution_replacement": False,
         "schedule_sha256": sha256(schedule_path)},
    )
    execute(schedule)


if __name__ == "__main__":
    main()
