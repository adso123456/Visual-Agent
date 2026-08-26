"""RELATION_GLOBAL_CONTEXT_CONFIRMATION_V1 冻结 paired 重复执行。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import run_context_evidence_policy_hardening_v1 as base


OUTPUT = Path(r"E:\3\_visual_agent_real_world_acceptance\v1\_relation_global_context_confirmation_v1")
EVENTS = OUTPUT / "raw_call_events.jsonl"
SCHEDULE = OUTPUT / "frozen_schedule.json"
REPETITIONS = 5


def append_event(row: dict) -> None:
    with EVENTS.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        stream.flush()


def load_events() -> dict[str, dict]:
    if not EVENTS.exists():
        return {}
    rows = [json.loads(line) for line in EVENTS.read_text(encoding="utf-8").splitlines() if line.strip()]
    result = {row["event_id"]: row for row in rows}
    if len(result) != len(rows):
        raise RuntimeError("raw_call_events.jsonl 存在重复 event_id")
    return result


def relation_cases() -> list[dict]:
    cases = [
        case for case in base.load_cases()
        if case["route"] == "relation" and case["subjects"] and case["related_candidates"]
    ]
    bindings = sum(len(case["subjects"]) * len(case["related_candidates"]) for case in cases)
    if len(cases) != 7 or bindings != 16:
        raise RuntimeError(f"冻结 relation 集合错误：cases={len(cases)} bindings={bindings}")
    return cases


def build_schedule(cases: list[dict]) -> dict:
    rows = []
    global_index = 0
    for case in cases:
        binding_ids = [
            f"{subject['id']}::{related['id']}"
            for subject in case["subjects"]
            for related in case["related_candidates"]
        ]
        for repetition in range(1, REPETITIONS + 1):
            first_arm = "A" if global_index % 2 == 0 else "B"
            sequence = (
                ["A_RELATION", "B_GLOBAL", "B_RELATION"]
                if first_arm == "A"
                else ["B_GLOBAL", "B_RELATION", "A_RELATION"]
            )
            rows.append({
                "case_id": case["case_id"],
                "image_sha256": case["image_sha256"],
                "repetition": repetition,
                "first_arm": first_arm,
                "sequence": sequence,
                "binding_ids": binding_ids,
            })
            global_index += 1
    first_counts = {arm: sum(row["first_arm"] == arm for row in rows) for arm in ("A", "B")}
    result = {
        "stage": "RELATION_GLOBAL_CONTEXT_CONFIRMATION_V1",
        "case_count": len(cases),
        "binding_count": sum(len(row["binding_ids"]) for row in rows[:1]),
        "repetitions": REPETITIONS,
        "case_repetition_count": len(rows),
        "scheduled_paired_binding_slots": sum(len(row["binding_ids"]) for row in rows),
        "scheduled_logical_calls": len(rows) * 3,
        "first_arm_counts": first_counts,
        "rows": rows,
    }
    # binding_count 需要按唯一 case 汇总，不能使用单行 binding 数量。
    result["binding_count"] = sum(
        len(case["subjects"]) * len(case["related_candidates"])
        for case in cases
    )
    if (
        result["case_repetition_count"] != 35
        or result["scheduled_paired_binding_slots"] != 80
        or result["scheduled_logical_calls"] != 105
        or first_counts != {"A": 18, "B": 17}
    ):
        raise RuntimeError(f"冻结顺序统计错误：{result}")
    return result


def event_id(case_id: str, repetition: int, kind: str) -> str:
    return f"{case_id}::rep{repetition}::{kind}"


def execute_relation(client, model: str, case: dict, repetition: int, arm: str, context: dict | None, events: dict[str, dict]) -> None:
    kind = f"{arm}_RELATION"
    identifier = event_id(case["case_id"], repetition, kind)
    if identifier in events:
        return
    call = base.call_relation(client, model, case, context)
    row = {
        "event_id": identifier,
        "case_id": case["case_id"],
        "image_sha256": case["image_sha256"],
        "repetition": repetition,
        "arm": arm,
        "kind": "relation",
        "executed": True,
        "call": call,
    }
    append_event(row)
    events[identifier] = row


def execute_b(client, model: str, case: dict, repetition: int, events: dict[str, dict]) -> None:
    global_id = event_id(case["case_id"], repetition, "B_GLOBAL")
    if global_id not in events:
        call = base.call_global(client, model, case)
        row = {
            "event_id": global_id,
            "case_id": case["case_id"],
            "image_sha256": case["image_sha256"],
            "repetition": repetition,
            "arm": "B",
            "kind": "global_context",
            "executed": True,
            "call": call,
        }
        append_event(row)
        events[global_id] = row
    projected = events[global_id]["call"].get("projected_payload")
    relation_id = event_id(case["case_id"], repetition, "B_RELATION")
    if projected is None:
        if relation_id not in events:
            row = {
                "event_id": relation_id,
                "case_id": case["case_id"],
                "image_sha256": case["image_sha256"],
                "repetition": repetition,
                "arm": "B",
                "kind": "relation",
                "executed": False,
                "skip_reason": "global_context_final_failure",
                "call": None,
            }
            append_event(row)
            events[relation_id] = row
        return
    if set(projected) != {"facts", "evidence"}:
        raise RuntimeError("B 下游 projection 必须精确为 facts/evidence")
    execute_relation(client, model, case, repetition, "B", projected, events)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cases = relation_cases()
    schedule = build_schedule(cases)
    if SCHEDULE.exists():
        if json.loads(SCHEDULE.read_text(encoding="utf-8")) != schedule:
            raise RuntimeError("现有 frozen_schedule.json 与代码生成顺序不一致")
    else:
        SCHEDULE.write_text(json.dumps(schedule, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if "--freeze-only" in sys.argv:
        print(json.dumps({key: value for key, value in schedule.items() if key != "rows"}, ensure_ascii=False, indent=2))
        return

    config = base.load_vlm_config()
    if config.base_url.rstrip("/") != "http://192.168.250.9:11434/v1" or config.model != "qwen3.8:27b-mtp-q4_K_M":
        raise RuntimeError(f"拒绝运行非冻结 Local VLM：{config}")
    case_map = {case["case_id"]: case for case in cases}
    events = load_events()
    client = base.create_vlm_client(config)
    for index, slot in enumerate(schedule["rows"], 1):
        case = case_map[slot["case_id"]]
        for kind in slot["sequence"]:
            if kind == "A_RELATION":
                execute_relation(client, config.model, case, slot["repetition"], "A", None, events)
            elif kind == "B_GLOBAL":
                execute_b(client, config.model, case, slot["repetition"], events)
            elif kind == "B_RELATION":
                # B_GLOBAL 已确定性地执行或记录 B_RELATION；这里不重复调用。
                continue
            else:
                raise RuntimeError(f"未知顺序项：{kind}")
        completed = sum(row.get("executed") for row in events.values())
        print(
            f"SLOT {index:02d}/35 {slot['case_id']} rep={slot['repetition']} first={slot['first_arm']} "
            f"executed_calls={completed}",
            flush=True,
        )


if __name__ == "__main__":
    main()
