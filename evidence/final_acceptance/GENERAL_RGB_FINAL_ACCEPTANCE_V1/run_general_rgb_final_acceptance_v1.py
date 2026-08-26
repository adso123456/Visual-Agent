"""在冻结 Production 上执行 GENERAL_RGB_FINAL_ACCEPTANCE_V1 的 140 个单元。

脚本位于 Production worktree 外；只调用正式 run_pipeline()，不修改任何 Production 文件。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any


PROJECT = Path(r"E:\3\Visual Agent\_general_rgb_final_acceptance_contract")
ACCEPTANCE_ROOT = Path(r"E:\3\_visual_agent_real_world_acceptance\v1")
OUTPUT = ACCEPTANCE_ROOT / "_general_rgb_final_acceptance_v1"
EXPECTED_COMMIT = "4dac9cb3823e22e90ff3bb8157c6544c6c6b88fd"
EXPECTED_MODEL = "qwen3.8:27b-mtp-q4_K_M"
EXPECTED_BASE_URL = "http://192.168.250.9:11434/v1"
PROMPT_ORDER = ["F1", "F2", "F3", "F4"]
INVALID_UNITS = {
    "F1__fishing_022",
    "F2__fishing_021",
    "F2__fishing_022",
    "F3__fishing_022",
    "F4__fishing_010",
    "F4__fishing_022",
    "F4__fishing_025",
}
SOURCE_HASHES = {
    ACCEPTANCE_ROOT / "acceptance_contract_v1.json": "08ea636fd3335599ddb219653b3a6ac07dba6d53f87e7f7906e9ea97131d9c5d",
    ACCEPTANCE_ROOT / "manifest.json": "28a602012b06baef9fdeb798c26144fc6eca6bc1fdb4914864ac292bfdbefaa4",
    ACCEPTANCE_ROOT / "_phase2" / "adjudication.json": "7729f2103d9319078a903d72734c1765d8928947da0efd924f09bec00d03e50f",
    PROJECT / "benchmark" / "cases.json": "6f56abbca54e7da8abe589881808d32801438e5e57bc0b69aa1929ca55b00acb",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assert_frozen_environment() -> None:
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--short"], cwd=PROJECT, text=True
    ).strip()
    if head != EXPECTED_COMMIT:
        raise RuntimeError(f"Production commit 漂移：{head}")
    if status:
        raise RuntimeError(f"Production worktree 非 clean：\n{status}")
    for path, expected in SOURCE_HASHES.items():
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"冻结来源 SHA-256 漂移：{path} {actual}")

    effective = {
        "VLM_MODEL": os.environ.get("VLM_MODEL"),
        "VLM_BASE_URL": os.environ.get("VLM_BASE_URL"),
        "VLM_API_KEY": os.environ.get("VLM_API_KEY"),
        "VLM_TIMEOUT": os.environ.get("VLM_TIMEOUT"),
        "DASHSCOPE_API_KEY_present": bool(os.environ.get("DASHSCOPE_API_KEY")),
    }
    expected = {
        "VLM_MODEL": EXPECTED_MODEL,
        "VLM_BASE_URL": EXPECTED_BASE_URL,
        "VLM_API_KEY": "ollama",
        "VLM_TIMEOUT": "120",
        "DASHSCOPE_API_KEY_present": False,
    }
    if effective != expected:
        raise RuntimeError(f"Local VLM 环境不符合冻结合同：{effective}")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise RuntimeError("DEEPSEEK_API_KEY 未设置")


def build_schedule() -> list[dict]:
    benchmark_cases = read_json(PROJECT / "benchmark" / "cases.json")
    cases_by_id = {item["id"]: item for item in benchmark_cases}
    contract = read_json(ACCEPTANCE_ROOT / "acceptance_contract_v1.json")
    prompt_defs = {item["test_id"]: item for item in contract["tests"]}
    fishing_files = sorted(
        item["filename"]
        for item in read_json(ACCEPTANCE_ROOT / "manifest.json")
        if item["category"] == "fishing"
    )
    if len(fishing_files) != 30 or len(set(fishing_files)) != 30:
        raise RuntimeError("fishing 冻结图片集不是 30 张唯一图片")

    schedule = []
    for case_id in [f"core_{index:03d}" for index in range(1, 16)] + [
        f"challenge_{index:03d}" for index in range(1, 6)
    ]:
        item = cases_by_id[case_id]
        image_path = PROJECT / item["image"]
        schedule.append(
            {
                "ordinal": len(schedule) + 1,
                "unit_id": case_id,
                "suite": item["suite"],
                "case_id": case_id,
                "prompt_id": None,
                "prompt": item["prompt"],
                "image_name": image_path.name,
                "image_path": str(image_path),
                "image_sha256": sha256(image_path),
                "expected": item["expected"],
                "ground_truth_class": None,
                "frozen_invalid": False,
            }
        )

    for prompt_id in PROMPT_ORDER:
        prompt_def = prompt_defs[prompt_id]
        positives = {item.removeprefix("v1_fishing_") for item in prompt_def["applicable_image_ids"]}
        negatives = {item.removeprefix("v1_fishing_") for item in prompt_def["negative_image_ids"]}
        if positives | negatives != set(fishing_files) or positives & negatives:
            raise RuntimeError(f"{prompt_id} 正负集合不构成完整互斥 30 张")
        for filename in fishing_files:
            stem = Path(filename).stem
            unit_id = f"{prompt_id}__{stem}"
            image_path = ACCEPTANCE_ROOT / "fishing" / filename
            schedule.append(
                {
                    "ordinal": len(schedule) + 1,
                    "unit_id": unit_id,
                    "suite": "real_world_fishing",
                    "case_id": f"{prompt_id}::{filename}",
                    "prompt_id": prompt_id,
                    "prompt": prompt_def["prompt"],
                    "image_name": filename,
                    "image_path": str(image_path),
                    "image_sha256": sha256(image_path),
                    "expected": None,
                    "ground_truth_class": "positive" if filename in positives else "negative",
                    "frozen_invalid": unit_id in INVALID_UNITS,
                }
            )

    if len(schedule) != 140 or len({item["unit_id"] for item in schedule}) != 140:
        raise RuntimeError("最终 schedule 不是 140 个唯一 execution units")
    if sum(item["frozen_invalid"] for item in schedule) != 7:
        raise RuntimeError("frozen invalid 数量不是 7")
    if any((item.get("prompt_id") or "").startswith("P") for item in schedule):
        raise RuntimeError("schedule 意外包含 pollution")
    return schedule


CURRENT_VLM_CALLS: list[dict] = []


class InstrumentedCompletions:
    def __init__(self, inner: Any, route: str, base_url: str):
        self._inner = inner
        self._route = route
        self._base_url = base_url

    def create(self, *args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            response = self._inner.create(*args, **kwargs)
        except Exception as exc:
            CURRENT_VLM_CALLS.append(
                {
                    "route": self._route,
                    "model": kwargs.get("model"),
                    "base_url": self._base_url,
                    "elapsed_seconds": round(time.perf_counter() - started, 4),
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            raise
        usage = getattr(response, "usage", None)
        message = response.choices[0].message
        content = message.content or ""
        CURRENT_VLM_CALLS.append(
            {
                "route": self._route,
                "model": kwargs.get("model"),
                "base_url": self._base_url,
                "elapsed_seconds": round(time.perf_counter() - started, 4),
                "status": "success",
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
                "reasoning_present": bool(getattr(message, "reasoning_content", None)),
                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "content_length": len(content),
            }
        )
        return response


class InstrumentedChat:
    def __init__(self, inner: Any, route: str, base_url: str):
        self.completions = InstrumentedCompletions(inner.completions, route, base_url)


class InstrumentedClient:
    def __init__(self, inner: Any, route: str, base_url: str):
        self.chat = InstrumentedChat(inner.chat, route, base_url)


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


def append_terminal(row: dict) -> None:
    path = OUTPUT / "raw_execution.jsonl"
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def existing_terminal_ids() -> set[str]:
    path = OUTPUT / "raw_execution.jsonl"
    if not path.exists():
        return set()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [row["unit_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("raw_execution.jsonl 存在重复 terminal unit")
    return set(ids)


def execute(schedule: list[dict]) -> None:
    if str(PROJECT) not in sys.path:
        sys.path.insert(0, str(PROJECT))
    from visual_agent.pipeline import run_pipeline

    install_vlm_observer()
    terminal_ids = existing_terminal_ids()
    for item in schedule:
        unit_id = item["unit_id"]
        if unit_id in terminal_ids:
            print(f"SKIP TERMINAL [{item['ordinal']}/140] {unit_id}", flush=True)
            continue
        print(f"START [{item['ordinal']}/140] {unit_id}", flush=True)
        CURRENT_VLM_CALLS.clear()
        started = time.perf_counter()
        case_output = OUTPUT / "artifacts" / unit_id
        case_output.mkdir(parents=True, exist_ok=False)
        try:
            image_output, json_output = run_pipeline(
                Path(item["image_path"]), item["prompt"], output_dir=case_output
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
                "result_image_bytes": image_output.stat().st_size,
                "plan": result.get("plan"),
                "candidate_count": len(result.get("candidates", [])),
                "target_count": len(result.get("targets", [])),
                "qwen_protocol": result.get("qwen_protocol"),
                "timings": result.get("timings"),
                "relation_bindings": result.get("relation_bindings"),
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
        terminal_ids.add(unit_id)
        print(
            f"DONE  [{item['ordinal']}/140] {unit_id} {row['terminal_status']} "
            f"{row['elapsed_seconds']}s targets={row.get('target_count', 0)} "
            f"vlm_calls={len(CURRENT_VLM_CALLS)}",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    assert_frozen_environment()
    schedule = build_schedule()
    schedule_path = OUTPUT / "frozen_schedule.json"
    if schedule_path.exists() and read_json(schedule_path) != schedule:
        raise RuntimeError("已存在 frozen_schedule.json 与当前冻结集合不一致")
    if not schedule_path.exists():
        write_json(schedule_path, schedule)
    metadata = {
        "stage": "GENERAL_RGB_FINAL_ACCEPTANCE_V1",
        "contract_status": "CONTRACT_FROZEN",
        "production_commit": EXPECTED_COMMIT,
        "schedule_sha256": sha256(schedule_path),
        "scheduled_units": len(schedule),
        "system_denominator": 140,
        "real_world_visual_denominator": 113,
        "pollution_units": 0,
        "vlm_model": EXPECTED_MODEL,
        "vlm_base_url": EXPECTED_BASE_URL,
        "vlm_timeout_seconds": 120,
        "concurrency": 1,
    }
    write_json(OUTPUT / "execution_manifest.json", metadata)
    if args.freeze_only:
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
        return
    execute(schedule)


if __name__ == "__main__":
    main()
