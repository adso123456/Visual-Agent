"""Targeted Remediation Gates 1-4 runner（冻结合同 919fcf2，implementation 41b7b46）。

- 只调用正式 run_pipeline()/DeepSeekAgent.plan_request()，不修改 Production 文件。
- 环境断言：implementation commit 41b7b46 + clean worktree + 冻结 Local VLM 配置、
  DEEPSEEK 可用、DASHSCOPE 不可用、concurrency=1（严格串行）。
- 每 gate 独立 raw_execution_gateN.jsonl（append + 断点续跑，跳过已 terminal 单元）；
  protocol/system failure 保留原始 error terminal，不补跑替换。
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


REPO = Path(r"E:\3\Visual Agent\_remediation_v1")
ACCEPTANCE = Path(r"E:\3\_visual_agent_real_world_acceptance\v1")
OUTPUT = ACCEPTANCE / "_general_rgb_final_acceptance_remediation_v1"
V1_OUTPUT = ACCEPTANCE / "_general_rgb_final_acceptance_v1"

EXPECTED_COMMIT = "1960505b6378024e403b2e23750dff03fc2cecbf"
EXPECTED_MODEL = "qwen3.8:27b-mtp-q4_K_M"
EXPECTED_BASE_URL = "http://192.168.250.9:11434/v1"
EXPECTED_VLM_API_KEY = "ollama"
EXPECTED_TIMEOUT = "120"
EXPECTED_PLANNER_MODEL = "qwen3.8:27b-mtp-q4_K_M"
EXPECTED_PLANNER_BASE_URL = "http://192.168.250.9:11434/v1"
EXPECTED_PLANNER_API_KEY = "ollama"

F2_PROMPT = "把拿着鱼竿的人描边"
F4_PROMPT = "把拿着鱼的人标出来"

F2_INVALID = {"fishing_021", "fishing_022"}
F4_INVALID = {"fishing_010", "fishing_022", "fishing_025"}

FISHING_DIR = ACCEPTANCE / "fishing"
CHALLENGE_IMAGES = {
    "challenge_001": REPO / "images" / "test_images" / "OIP-C.jpg",
    "challenge_003": REPO / "images" / "test_images" / "benchmark_fishing_lowlight.png",
    "challenge_004": REPO / "images" / "test_images" / "benchmark_fishing_two_people.png",
}
CHALLENGE_PROMPTS = {
    "challenge_001": "找到正在钓鱼的人",
    "challenge_003": "把正在钓鱼的人标红",
    "challenge_004": "把正在钓鱼的人以外背景变暗",
}

GATE2_SPECS = [
    {"case": "F2::fishing_001.jpeg", "prompt": F2_PROMPT, "kind": "negative"},
    {"case": "F2::fishing_024.jpeg", "prompt": F2_PROMPT, "kind": "positive"},
    {"case": "F4::fishing_017.jpeg", "prompt": F4_PROMPT, "kind": "positive"},
    {"case": "challenge_001", "prompt": CHALLENGE_PROMPTS["challenge_001"], "kind": "challenge"},
    {"case": "challenge_004", "prompt": CHALLENGE_PROMPTS["challenge_004"], "kind": "challenge"},
    {"case": "challenge_003", "prompt": CHALLENGE_PROMPTS["challenge_003"], "kind": "challenge"},
]


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


def assert_frozen_environment() -> None:
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--short"], cwd=REPO, text=True
    ).strip()
    if head != EXPECTED_COMMIT:
        raise RuntimeError(f"implementation commit 漂移：{head}")
    if status:
        raise RuntimeError(f"implementation worktree 非 clean：\n{status}")
    effective = {
        "VLM_MODEL": os.environ.get("VLM_MODEL"),
        "VLM_BASE_URL": os.environ.get("VLM_BASE_URL"),
        "VLM_API_KEY": os.environ.get("VLM_API_KEY"),
        "VLM_TIMEOUT": os.environ.get("VLM_TIMEOUT"),
        "PLANNER_MODEL": os.environ.get("PLANNER_MODEL"),
        "PLANNER_BASE_URL": os.environ.get("PLANNER_BASE_URL"),
        "PLANNER_API_KEY": os.environ.get("PLANNER_API_KEY"),
        "DASHSCOPE_API_KEY_present": bool(os.environ.get("DASHSCOPE_API_KEY")),
        "DEEPSEEK_API_KEY_present": bool(os.environ.get("DEEPSEEK_API_KEY")),
    }
    expected = {
        "VLM_MODEL": EXPECTED_MODEL,
        "VLM_BASE_URL": EXPECTED_BASE_URL,
        "VLM_API_KEY": EXPECTED_VLM_API_KEY,
        "VLM_TIMEOUT": EXPECTED_TIMEOUT,
        "PLANNER_MODEL": EXPECTED_PLANNER_MODEL,
        "PLANNER_BASE_URL": EXPECTED_PLANNER_BASE_URL,
        "PLANNER_API_KEY": EXPECTED_PLANNER_API_KEY,
        "DASHSCOPE_API_KEY_present": False,
        "DEEPSEEK_API_KEY_present": False,
    }
    if effective != expected:
        raise RuntimeError(f"环境不符合冻结合同：{effective}")


def load_frozen_fishing_schedule() -> dict[str, dict]:
    """从冻结 V1 schedule 提取每个 fishing 图像的 F2/F4 prompt/ground_truth/invalid。"""
    if not V1_OUTPUT.joinpath("frozen_schedule.json").is_file():
        raise RuntimeError("缺少冻结 V1 frozen_schedule.json")
    rows = read_json(V1_OUTPUT / "frozen_schedule.json")
    fishing = {}
    for row in rows:
        prompt_id = row.get("prompt_id")
        if prompt_id not in {"F2", "F4"}:
            continue
        stem = Path(row["image_name"]).stem
        fishing.setdefault(stem, {})[prompt_id] = {
            "unit_id": row["unit_id"],
            "case_id": row["case_id"],
            "prompt": row["prompt"],
            "ground_truth_class": row["ground_truth_class"],
            "frozen_invalid": row["frozen_invalid"],
            "image_sha256": row["image_sha256"],
            "image_name": row["image_name"],
        }
    return fishing


def build_gate1_schedule() -> list[dict]:
    units = []
    for prompt_id, prompt in [("F2", F2_PROMPT), ("F4", F4_PROMPT)]:
        for attempt in range(1, 11):
            units.append(
                {
                    "ordinal": len(units) + 1,
                    "unit_id": f"G1_{prompt_id}_{attempt:02d}",
                    "gate": 1,
                    "prompt_id": prompt_id,
                    "prompt": prompt,
                }
            )
    return units


def build_gate2_schedule() -> list[dict]:
    units = []
    for spec in GATE2_SPECS:
        if spec["case"] in {"F2::fishing_001.jpeg", "F2::fishing_024.jpeg", "F4::fishing_017.jpeg"}:
            src = FISHING_DIR / Path(spec["case"].split("::")[-1])
        else:
            src = CHALLENGE_IMAGES[spec["case"]]
        image_sha256 = sha256(src)
        for rep in range(1, 6):
            units.append(
                {
                    "ordinal": len(units) + 1,
                    "unit_id": f"G2_{spec['case'].replace('::', '__').replace('.jpeg', '')}_{rep:02d}",
                    "gate": 2,
                    "case_id": spec["case"],
                    "prompt": spec["prompt"],
                    "kind": spec["kind"],
                    "rep": rep,
                    "image_path": str(src),
                    "image_name": src.name,
                    "image_sha256": image_sha256,
                }
            )
    return units


def build_gate3_schedule() -> list[dict]:
    fishing = load_frozen_fishing_schedule()
    units = []
    for stem in sorted(fishing):
        for prompt_id in ("F2", "F4"):
            meta = fishing[stem][prompt_id]
            src = FISHING_DIR / meta["image_name"]
            if sha256(src) != meta["image_sha256"]:
                raise RuntimeError(f"fishing 图像 SHA-256 漂移：{src}")
            units.append(
                {
                    "ordinal": len(units) + 1,
                    "unit_id": meta["unit_id"],
                    "gate": 3,
                    "prompt_id": prompt_id,
                    "case_id": meta["case_id"],
                    "prompt": meta["prompt"],
                    "image_path": str(src),
                    "image_name": meta["image_name"],
                    "image_sha256": meta["image_sha256"],
                    "ground_truth_class": meta["ground_truth_class"],
                    "frozen_invalid": meta["frozen_invalid"],
                }
            )
    return units


def build_gate4_schedule() -> list[dict]:
    cases = read_json(REPO / "benchmark" / "cases.json")
    by_id = {item["id"]: item for item in cases}
    units = []
    for case_id in ("core_003", "core_004", "core_014"):
        item = by_id[case_id]
        src = REPO / item["image"]
        if not src.is_file():
            raise RuntimeError(f"core 图像缺失：{src}")
        units.append(
            {
                "ordinal": len(units) + 1,
                "unit_id": case_id,
                "gate": 4,
                "case_id": case_id,
                "prompt": item["prompt"],
                "image_path": str(src),
                "image_name": src.name,
                "image_sha256": sha256(src),
                "expected": item["expected"],
            }
        )
    return units


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


def jsonl_path(gate: int) -> Path:
    return OUTPUT / f"raw_execution_gate{gate}.jsonl"


def append_terminal(gate: int, row: dict) -> None:
    path = jsonl_path(gate)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def existing_terminal_ids(gate: int) -> set[str]:
    path = jsonl_path(gate)
    if not path.exists():
        return set()
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [row["unit_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError(f"raw_execution_gate{gate}.jsonl 存在重复 terminal unit")
    return set(ids)


def run_pipeline_unit(item: dict, terminal_ids: set[str], artifacts_dir: Path) -> None:
    unit_id = item["unit_id"]
    if unit_id in terminal_ids:
        print(f"SKIP TERMINAL [{item['ordinal']}] {unit_id}", flush=True)
        return
    from visual_agent.pipeline import run_pipeline

    print(f"START [{item['ordinal']}] {unit_id} {item['case_id']}", flush=True)
    CURRENT_VLM_CALLS.clear()
    started = time.perf_counter()
    case_output = artifacts_dir / unit_id
    case_output.mkdir(parents=True, exist_ok=True)
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
            "candidates": [
                {
                    "id": c["id"],
                    "bbox": c.get("bbox"),
                    "dino_confidence": c.get("dino_confidence"),
                    "verification_checks": c.get("verification_checks"),
                    "verified": c.get("verified"),
                }
                for c in result.get("candidates", [])
            ],
            "targets": [
                {
                    "id": t.get("id"),
                    "label": t.get("label"),
                    "bbox": t.get("bbox"),
                    "composite_bbox": t.get("composite_bbox"),
                    "reason": t.get("reason"),
                }
                for t in result.get("targets", [])
            ],
            "candidate_count": len(result.get("candidates", [])),
            "target_count": len(result.get("targets", [])),
            "relation_candidates": result.get("relation_candidates"),
            "relation_bindings": result.get("relation_bindings"),
            "semantic_groups": result.get("semantic_groups"),
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
    append_terminal(item["gate"], row)
    terminal_ids.add(unit_id)
    print(
        f"DONE  [{item['ordinal']}] {unit_id} {row['terminal_status']} "
        f"{row['elapsed_seconds']}s targets={row.get('target_count', 0)} "
        f"vlm_calls={len(CURRENT_VLM_CALLS)}",
        flush=True,
    )


def run_gate1(terminal_ids: set[str]) -> None:
    from visual_agent.deepseek_agent import DeepSeekAgent

    schedule = build_gate1_schedule()
    for item in schedule:
        unit_id = item["unit_id"]
        if unit_id in terminal_ids:
            print(f"SKIP TERMINAL [{item['ordinal']}] {unit_id}", flush=True)
            continue
        print(f"START [{item['ordinal']}] {unit_id} planner", flush=True)
        started = time.perf_counter()
        try:
            agent = DeepSeekAgent()
            plan = agent.plan_request(item["prompt"])
            row = {
                **item,
                "terminal_status": "success",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "plan": plan,
                "plan_attempts": agent.plan_attempts,
            }
        except Exception as exc:
            row = {
                **item,
                "terminal_status": "error",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        append_terminal(1, row)
        terminal_ids.add(unit_id)
        plan = row.get("plan") or {}
        route = (plan.get("constraints") or [{}])[0].get("route") if plan else None
        print(
            f"DONE  [{item['ordinal']}] {unit_id} {row['terminal_status']} "
            f"route={route} attempts={row.get('plan_attempts', 0)}",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", required=True, choices=["1", "2", "3", "4"])
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    gate = int(args.gate)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    assert_frozen_environment()
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))

    builder = {
        1: build_gate1_schedule,
        2: build_gate2_schedule,
        3: build_gate3_schedule,
        4: build_gate4_schedule,
    }[gate]
    schedule = builder()
    if args.freeze_only:
        schedule_path = OUTPUT / f"gate{gate}_frozen_schedule.json"
        write_json(schedule_path, schedule)
        print(f"{schedule_path} ({len(schedule)} units)")
        return

    terminal_ids = existing_terminal_ids(gate)
    if gate == 1:
        run_gate1(terminal_ids)
        return

    install_vlm_observer()
    artifacts_dir = OUTPUT / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    for item in schedule:
        run_pipeline_unit(item, terminal_ids, artifacts_dir)


if __name__ == "__main__":
    main()
