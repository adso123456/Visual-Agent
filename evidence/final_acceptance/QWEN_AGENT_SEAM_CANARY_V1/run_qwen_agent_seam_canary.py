"""只验证本地 Qwen 的 Planner tool-call 与 Final Response seam。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from visual_agent.deepseek_agent import DeepSeekAgent


ROOT = Path(__file__).resolve().parent
PROJECT = Path(r"E:\3\Visual Agent\_implementation_worktree")
EXPECTED_HEAD = "aed1e3e6acb537480664b89531a9bc12a29d708f"
EXPECTED_MODEL = "qwen3.8:27b-mtp-q4_K_M"
EXPECTED_BASE_URL = "http://192.168.250.9:11434/v1"
CASES = [
    {
        "id": "behavior",
        "prompt": "框出正在钓鱼的人",
        "expected_route": "behavior",
        "expected_action": "box",
        "expected_related": False,
    },
    {
        "id": "relation",
        "prompt": "框出拿着鱼竿的人",
        "expected_route": "relation",
        "expected_action": "box",
        "expected_related": True,
    },
    {
        "id": "attribute",
        "prompt": "把戴红帽的人以外的背景变暗",
        "expected_route": "attribute",
        "expected_action": "dim_background",
        "expected_related": False,
    },
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append(row: dict) -> None:
    with (ROOT / "raw_execution.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def preflight() -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--short"], cwd=PROJECT, text=True).strip()
    if head != EXPECTED_HEAD or status:
        raise RuntimeError(f"implementation worktree 漂移：head={head!r}, status={status!r}")
    expected = {
        "PLANNER_MODEL": EXPECTED_MODEL,
        "PLANNER_BASE_URL": EXPECTED_BASE_URL,
        "PLANNER_API_KEY": "ollama",
    }
    actual = {key: os.environ.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"PLANNER 配置不符合 canary：{actual}")
    if os.environ.get("DEEPSEEK_API_KEY"):
        raise RuntimeError("canary 期间禁止存在 DEEPSEEK_API_KEY")


def validate_plan(plan: dict, case: dict) -> None:
    routes = [item["route"] for item in plan["constraints"]]
    if routes != [case["expected_route"]]:
        raise RuntimeError(f"route 不符合预期：{routes}")
    if plan["action"]["type"] != case["expected_action"]:
        raise RuntimeError(f"action 不符合预期：{plan['action']}")
    has_related = bool(plan["related_objects"])
    if has_related != case["expected_related"]:
        raise RuntimeError(f"related_objects 不符合预期：{plan['related_objects']}")
    if has_related and plan["related_objects"][0]["relation"] != "held_by_target":
        raise RuntimeError("relation 不是 held_by_target")


def main() -> None:
    preflight()
    raw = ROOT / "raw_execution.jsonl"
    if raw.exists():
        raise RuntimeError("canary raw 已存在，禁止覆盖或补跑")

    rows = []
    for case in CASES:
        agent = DeepSeekAgent()
        if agent.model != EXPECTED_MODEL or agent.base_url.rstrip("/") != EXPECTED_BASE_URL:
            raise RuntimeError("Agent client 未绑定本地 Qwen endpoint")
        started = time.perf_counter()
        try:
            plan = agent.plan_request(case["prompt"])
            validate_plan(plan, case)
            final = agent.build_final_response(
                case["prompt"],
                {
                    "plan": plan,
                    "verified_subjects_count": 1,
                    "complete_semantic_targets_count": 1,
                    "incomplete_semantic_groups": [],
                    "targets_count": 1,
                    "targets": [
                        {
                            "label": plan["label"],
                            "verification_reason": "canary 结构化视觉结果",
                            "verification_checks": [],
                        }
                    ],
                    "action": plan["action"],
                    "execution_success": True,
                },
            )
            row = {
                "case_id": case["id"],
                "terminal_status": "success",
                "model": agent.model,
                "base_url": agent.base_url,
                "provider": agent.provider,
                "planner_attempts": agent.plan_attempts,
                "plan": plan,
                "final_response": final,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
        except Exception as exc:
            row = {
                "case_id": case["id"],
                "terminal_status": "error",
                "model": agent.model,
                "base_url": agent.base_url,
                "provider": agent.provider,
                "planner_attempts": agent.plan_attempts,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
        append(row)
        rows.append(row)

    summary = {
        "stage": "QWEN_AGENT_SEAM_CANARY_V1",
        "implementation_head": EXPECTED_HEAD,
        "model": EXPECTED_MODEL,
        "base_url": EXPECTED_BASE_URL,
        "deepseek_api_key_present": False,
        "scheduled": len(CASES),
        "success": sum(row["terminal_status"] == "success" for row in rows),
        "error": sum(row["terminal_status"] == "error" for row in rows),
        "planner_attempts": sum(row["planner_attempts"] for row in rows),
    }
    summary["gate_pass"] = summary["success"] == len(CASES) and summary["error"] == 0
    (ROOT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "files": [
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in sorted(ROOT.iterdir())
            if path.is_file() and path.name != "manifest.json"
        ]
    }
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
