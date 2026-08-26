"""CONTEXT_EVIDENCE_POLICY_HARDENING_V1 独立 A/B/C 对照。

固定既有 Detector candidates；复用 Production evidence 构造、JSON validator 与 Local VLM。
不修改 Production，不调用 Cloud，不运行完整 Pipeline。
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from visual_agent.evidence import build_behavior_evidence, build_isolated_instance_evidence
from visual_agent.models import get_segmenter
from visual_agent.qwen_protocol import request_validated_json
from visual_agent.relations import _marked_scene_data_url
from visual_agent.vlm import _pil_image_data_url, _take_evidence_telemetry, validate_candidate_constraints
from visual_agent.vlm_client import create_vlm_client, load_vlm_config


ROOT = Path(r"E:\3\_visual_agent_real_world_acceptance\v1")
OUTPUT = ROOT / "_context_evidence_policy_hardening_v1"
SELECTION = ROOT / "_scene_context_benchmark_v1" / "SCENE_CONTEXT_BENCHMARK_V1_SELECTION.json"
DEMO_RESULTS = Path(__file__).resolve().parents[1] / "benchmark" / "phase8_results"
CASES_JSON = Path(__file__).resolve().parents[1] / "benchmark" / "cases.json"
ARM_A = OUTPUT / "arm_a.jsonl"
ARM_B = OUTPUT / "arm_b.jsonl"
ARM_C = OUTPUT / "arm_c.jsonl"
FROZEN_SELECTION = OUTPUT / "frozen_selection.json"
STATUSES = {"satisfied", "not_satisfied", "uncertain"}

DEMO_ROUTES = {
    "core_011": "attribute",
    "challenge_005": "attribute",
    "challenge_001": "behavior",
    "challenge_003": "behavior",
    "challenge_004": "behavior",
    "core_003": "relation",
    "core_014": "relation",
}

# 只冻结候选/关系证据单元的人工真值；Detector 无候选属于固定上游结果。
EXPECTED_OVERRIDES = {
    "F2::fishing_008.jpeg": {
        "A::R1": "not_satisfied", "A::R2": "satisfied",
        "B::R1": "satisfied", "B::R2": "not_satisfied",
        "C::R1": "not_satisfied", "C::R2": "not_satisfied",
    },
    "F4::fishing_003.jpeg": {"A::R1": "not_satisfied", "A::R2": "satisfied"},
    "demo::core_011": {"A": "satisfied", "B": "satisfied"},
    "demo::challenge_005": {"A": "satisfied", "B": "satisfied", "C": "satisfied", "D": "uncertain"},
    "demo::challenge_001": {"A": "not_satisfied", "B": "satisfied"},
    "demo::challenge_003": {"A": "uncertain"},
    "demo::challenge_004": {"A": "satisfied", "B": "uncertain"},
    "demo::core_003": {"A::R1": "satisfied"},
}

SIMPLIFIED_SYSTEM = """你是 task-conditioned structured scene observer。输入是原始完整图片和用户任务。
只记录与任务直接相关、图中可观察的简短事实；不生成自由 caption，不枚举无关对象，不推断不可见事实，不输出思维链。
task_status 只表示完整场景中是否至少存在一个满足用户目标语义的对象。
必须区分当前动作与携带工具、展示渔获、走路、徒手捕鱼、网捕鱼；数量不清楚时不得虚构数量。
只返回严格 JSON，顶层只能包含 task_status、facts、evidence。"""


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def response_meta(response: Any, elapsed: float) -> dict:
    usage = getattr(response, "usage", None)
    message = response.choices[0].message
    return {
        "elapsed_seconds": round(elapsed, 4),
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
        "reasoning_present": bool(getattr(message, "reasoning_content", None)),
        "content": message.content,
    }


def validated_call(client, model: str, messages: list[dict], validator: Callable[[dict], Any], name: str, hint: str) -> dict:
    attempts = []

    def request_once(correction: str | None) -> str | None:
        request_messages = [*messages]
        if correction:
            request_messages.append({"role": "user", "content": correction})
        started = time.perf_counter()
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=request_messages,
        )
        attempts.append(response_meta(response, time.perf_counter() - started))
        return response.choices[0].message.content

    try:
        result, protocol = request_validated_json(request_once, validator, name, hint)
        error = None
    except Exception as exc:  # 原始失败必须留在对照结果中，不补跑或调参。
        result = None
        protocol = {
            "attempts": len(attempts), "retry_count": max(0, len(attempts) - 1),
            "recovered": False, "first_error_code": type(exc).__name__,
        }
        error = f"{type(exc).__name__}: {exc}"
    return {
        "result": result,
        "protocol": protocol,
        "attempts": attempts,
        "error": error,
        "elapsed_seconds": round(sum(item["elapsed_seconds"] for item in attempts), 4),
    }


def validate_global(data: dict) -> dict:
    if not isinstance(data, dict) or set(data) != {"task_status", "facts", "evidence"}:
        raise RuntimeError("Global Context 顶层字段不正确")
    if data["task_status"] not in STATUSES:
        raise RuntimeError("Global Context task_status 非法")
    if not isinstance(data["facts"], list) or len(data["facts"]) > 8 or any(not isinstance(x, str) or not x.strip() for x in data["facts"]):
        raise RuntimeError("Global Context facts 非法")
    if not isinstance(data["evidence"], str) or not data["evidence"].strip():
        raise RuntimeError("Global Context evidence 非法")
    return data


def call_global(client, model: str, case: dict) -> dict:
    with Image.open(case["image_path"]) as source:
        data_url = _pil_image_data_url(source.convert("RGB"))
    messages = [
        {"role": "system", "content": SIMPLIFIED_SYSTEM},
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": (
                f"用户任务：{case['prompt']}\n"
                '返回精确合同：{"task_status":"satisfied|not_satisfied|uncertain",'
                '"facts":["可见事实"],"evidence":"简短中文证据"}'
            )},
        ]},
    ]
    call = validated_call(client, model, messages, validate_global, "simplified global context", "只返回 task_status、facts、evidence")
    if call["result"] is not None:
        call["projected_payload"] = {
            "facts": call["result"]["facts"],
            "evidence": call["result"]["evidence"],
        }
        assert set(call["projected_payload"]) == {"facts", "evidence"}
    else:
        call["projected_payload"] = None
    return call


def candidate_messages(candidate: dict, constraints: list[dict], route: str, evidence: Image.Image, context: dict | None) -> list[dict]:
    route_instruction = {
        "attribute": "图像只保留当前候选实例像素。只根据候选本人的外观、衣着、颜色、装备判断，不得使用灰色区域或想象相邻人物属性。",
        "behavior": "图中轮廓标出当前人物。行为只能归属于该轮廓人物；可使用局部图中直接相关的物体、姿态和交互，不得借用附近人物行为。",
    }[route]
    context_instruction = ""
    context_text = ""
    if context is not None:
        assert set(context) == {"facts", "evidence"}
        context_instruction = (
            "你还会收到不含候选 ID 的辅助场景事实。它只可补充局部证据缺失的 scene-level context；"
            "候选身份和事实归属必须由当前候选图像锚定，不得仅凭全局事实把动作或属性分配给当前候选。"
        )
        context_text = "\n辅助场景上下文：" + json.dumps(context, ensure_ascii=False)
    texts = [item["text"] for item in constraints]
    return [
        {"role": "system", "content": (
            f"你是单候选 {route} 语义验证器。{route_instruction}{context_instruction}"
            "逐条判断 constraints，顺序和原文必须完全一致。status 只能是 satisfied、not_satisfied、uncertain；"
            "证据不足或归属不清必须 uncertain。只返回 candidate_id、checks；check 只能包含 constraint、status、evidence。"
        )},
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": _pil_image_data_url(evidence)}},
            {"type": "text", "text": (
                f"candidate_id：{candidate['id']}\nroute：{route}\n"
                f"constraints：{json.dumps(texts, ensure_ascii=False)}{context_text}\n请返回每条约束的独立三态判断。"
            )},
        ]},
    ]


def call_candidate(client, model: str, candidate: dict, constraints: list[dict], route: str, evidence: Image.Image, context: dict | None) -> dict:
    call = validated_call(
        client, model, candidate_messages(candidate, constraints, route, evidence, context),
        lambda result: validate_candidate_constraints(result, candidate, constraints, route),
        f"{route} candidate verification",
        '{"candidate_id":"A","checks":[{"constraint":"原文","status":"三态","evidence":"非空"}]}',
    )
    telemetry = _take_evidence_telemetry()
    if telemetry is not None:
        call["evidence_payload"] = telemetry
    return call


def validate_selected_bindings(data: dict, expected_pairs: set[tuple[str, str]]) -> list[dict]:
    bindings = data.get("bindings") if isinstance(data, dict) else None
    if not isinstance(bindings, list) or len(bindings) != len(expected_pairs):
        raise RuntimeError("relation binding 数量错误")
    found = set()
    for item in bindings:
        if not isinstance(item, dict) or set(item) != {"subject_id", "related_id", "relation", "status", "evidence"}:
            raise RuntimeError("relation binding 字段错误")
        pair = (item["subject_id"], item["related_id"])
        if pair not in expected_pairs or pair in found or item["relation"] != "held_by_target" or item["status"] not in STATUSES or not str(item["evidence"]).strip():
            raise RuntimeError("relation binding 值错误")
        found.add(pair)
    if found != expected_pairs:
        raise RuntimeError("relation binding 组合缺失")
    return bindings


def call_relation(client, model: str, case: dict, context: dict | None, selected_pairs: set[tuple[str, str]] | None = None) -> dict:
    subjects = case["subjects"]
    related = case["related_candidates"]
    all_pairs = {(s["id"], r["id"]) for s in subjects for r in related}
    pairs = selected_pairs or all_pairs
    context_instruction = ""
    context_text = ""
    if context is not None:
        assert set(context) == {"facts", "evidence"}
        context_instruction = (
            "辅助场景事实不含候选 ID，只可补充 scene-level context；每个 subject-related 归属必须由标框完整场景中的手部、接触和空间证据锚定。"
        )
        context_text = "\n辅助场景上下文：" + json.dumps(context, ensure_ascii=False)
    pair_rows = [{"subject_id": a, "related_id": b} for a, b in sorted(pairs)]
    messages = [
        {"role": "system", "content": (
            "你是群组视觉关系验证器。红框是主体，蓝框是关联对象。held_by_target 表示蓝框物体确实由指定红框主体持有。"
            "必须关注手部、手柄、直接抓握或接触和明确归属；仅靠近不得判 satisfied，证据不足必须 uncertain。"
            f"{context_instruction}只返回 bindings 数组，并且只返回用户列出的待判断组合。"
        )},
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": _marked_scene_data_url(Path(case["image_path"]), subjects, related)}},
            {"type": "text", "text": (
                f"relation：held_by_target\n关联实体：{case['related_object']}\n"
                f"待判断组合：{json.dumps(pair_rows, ensure_ascii=False)}{context_text}\n"
                "每个组合恰好返回一次。"
            )},
        ]},
    ]
    return validated_call(
        client, model, messages, lambda result: validate_selected_bindings(result, pairs),
        "selected relation bindings", '{"bindings":[{"subject_id":"A","related_id":"R1","relation":"held_by_target","status":"三态","evidence":"非空"}]}',
    )


def expected_for(case: dict, unit_id: str) -> str:
    override = EXPECTED_OVERRIDES.get(case["case_id"], {})
    if unit_id in override:
        return override[unit_id]
    return case["expected_task_status"]


def load_cases() -> list[dict]:
    selection = read_json(SELECTION)["cases"]
    cases = []
    for source in selection:
        if source["prompt_id"] not in {"F1", "F2", "F4"}:
            continue
        result = read_json(Path(source["local_result_json_path"]))
        constraints = source["current_plan"]["constraints"]
        route = "relation" if source["current_plan"].get("related_objects") else constraints[0]["route"]
        cases.append({
            "case_id": source["case_id"], "prompt_id": source["prompt_id"], "prompt": source["prompt_text"],
            "image_path": source["original_image_path"], "image_sha256": sha256(Path(source["original_image_path"])),
            "route": route, "constraints": constraints, "expected_task_status": source["expected_task_status"],
            "candidates": [{"id": x["id"], "bbox": x["bbox"]} for x in result.get("candidates", [])],
            "subjects": [{"id": x["id"], "bbox": x["bbox"]} for x in result.get("candidates", [])],
            "related_candidates": [{"id": x["id"], "bbox": x["bbox"]} for x in result.get("relation_candidates", [])],
            "related_object": (source["current_plan"].get("related_objects") or [{}])[0].get("object"),
        })
    demo_specs = {row["id"]: row for row in read_json(CASES_JSON)}
    for case_id, route in DEMO_ROUTES.items():
        source = demo_specs[case_id]
        result = read_json(DEMO_RESULTS / case_id / "result.json")
        image_path = Path(__file__).resolve().parents[1] / source["image"]
        constraint_text = result["plan"]["constraints"][0]
        constraints = [{"text": constraint_text, "route": route}]
        expected_task = "not_satisfied" if case_id == "core_014" else ("uncertain" if case_id == "challenge_003" else "satisfied")
        cases.append({
            "case_id": f"demo::{case_id}", "prompt_id": case_id, "prompt": source["prompt"],
            "image_path": str(image_path), "image_sha256": sha256(image_path), "route": route,
            "constraints": constraints, "expected_task_status": expected_task,
            "candidates": [{"id": x["id"], "bbox": x["bbox"]} for x in result.get("candidates", [])],
            "subjects": [{"id": x["id"], "bbox": x["bbox"]} for x in result.get("candidates", [])],
            "related_candidates": [{"id": x["id"], "bbox": x["bbox"]} for x in result.get("relation_candidates", [])],
            "related_object": "umbrella" if route == "relation" else None,
        })
    if len(cases) != 25 or any(case["prompt_id"].startswith("P") for case in cases):
        raise RuntimeError("冻结选择集必须精确为 25 个非 pollution case")
    return cases


def make_evidence(case: dict) -> dict[str, Image.Image]:
    if case["route"] == "relation" or not case["candidates"]:
        return {}
    segmenter, _ = get_segmenter()
    outputs, _ = segmenter.segment(Path(case["image_path"]), [x["bbox"] for x in case["candidates"]])
    evidence = {}
    for candidate, segmentation in zip(case["candidates"], outputs):
        evidence[candidate["id"]] = (
            build_isolated_instance_evidence(Path(case["image_path"]), segmentation["mask"])
            if case["route"] == "attribute"
            else build_behavior_evidence(Path(case["image_path"]), candidate["bbox"], segmentation["mask"])
        )
    return evidence


def run_units(client, model: str, case: dict, evidence: dict[str, Image.Image], context: dict | None, selected: set[str] | None = None) -> list[dict]:
    if case["route"] == "relation":
        if not case["subjects"] or not case["related_candidates"]:
            return []
        pairs = {(s["id"], r["id"]) for s in case["subjects"] for r in case["related_candidates"]}
        if selected is not None:
            pairs = {tuple(unit.split("::", 1)) for unit in selected}
        call = call_relation(client, model, case, context, pairs)
        bindings = call["result"] or []
        return [{
            "unit_id": f"{x['subject_id']}::{x['related_id']}", "expected": expected_for(case, f"{x['subject_id']}::{x['related_id']}"),
            "status": x["status"], "evidence": x["evidence"], "call": call,
        } for x in bindings] if bindings else [{"unit_id": unit, "expected": expected_for(case, unit), "status": "protocol_failure", "evidence": call["error"], "call": call} for unit in sorted(selected or {f"{a}::{b}" for a, b in pairs})]
    rows = []
    for candidate in case["candidates"]:
        unit = candidate["id"]
        if selected is not None and unit not in selected:
            continue
        call = call_candidate(client, model, candidate, case["constraints"], case["route"], evidence[unit], context)
        check = call["result"][0] if call["result"] else None
        rows.append({
            "unit_id": unit, "expected": expected_for(case, unit),
            "status": check["status"] if check else "protocol_failure",
            "evidence": check["evidence"] if check else call["error"], "call": call,
        })
    return rows


def task_status(units: list[dict], no_unit_expected: str) -> str:
    statuses = [row["status"] for row in units]
    if not statuses:
        return "not_satisfied"
    if "protocol_failure" in statuses:
        return "protocol_failure"
    if "satisfied" in statuses:
        return "satisfied"
    if "uncertain" in statuses:
        return "uncertain"
    return "not_satisfied"


def run_arm_a(client, model: str, cases: list[dict], evidence_cache: dict[str, dict[str, Image.Image]]) -> None:
    completed = {row["case_id"] for row in read_jsonl(ARM_A)}
    for index, case in enumerate(cases, 1):
        if case["case_id"] in completed:
            continue
        units = run_units(client, model, case, evidence_cache[case["case_id"]], None)
        row = {"case_id": case["case_id"], "route": case["route"], "units": units, "task_status": task_status(units, case["expected_task_status"]), "expected_task_status": case["expected_task_status"]}
        append_jsonl(ARM_A, row)
        print(f"A {index:02d}/25 {case['case_id']} => {row['task_status']}", flush=True)


def run_arm_c(client, model: str, cases: list[dict], evidence_cache: dict[str, dict[str, Image.Image]]) -> None:
    a_rows = {row["case_id"]: row for row in read_jsonl(ARM_A)}
    completed = {row["case_id"] for row in read_jsonl(ARM_C)}
    for index, case in enumerate(cases, 1):
        if case["case_id"] in completed:
            continue
        first = a_rows[case["case_id"]]
        selected = {row["unit_id"] for row in first["units"] if row["status"] == "uncertain"}
        global_call = None
        fallback = []
        if selected:
            global_call = call_global(client, model, case)
            if global_call["projected_payload"] is not None:
                fallback = run_units(client, model, case, evidence_cache[case["case_id"]], global_call["projected_payload"], selected)
        fallback_map = {row["unit_id"]: row for row in fallback}
        final_units = [fallback_map.get(row["unit_id"], row) for row in first["units"]]
        row = {
            "case_id": case["case_id"], "route": case["route"], "fallback_triggered": bool(selected),
            "fallback_unit_ids": sorted(selected), "global_context_call": global_call, "fallback_results": fallback,
            "units": final_units, "task_status": task_status(final_units, case["expected_task_status"]), "expected_task_status": case["expected_task_status"],
        }
        append_jsonl(ARM_C, row)
        print(f"C {index:02d}/25 {case['case_id']} lazy={bool(selected)} => {row['task_status']}", flush=True)


def run_arm_b(client, model: str, cases: list[dict], evidence_cache: dict[str, dict[str, Image.Image]]) -> None:
    completed = {row["case_id"] for row in read_jsonl(ARM_B)}
    for index, case in enumerate(cases, 1):
        if case["case_id"] in completed:
            continue
        global_call = call_global(client, model, case)
        units = [] if global_call["projected_payload"] is None else run_units(client, model, case, evidence_cache[case["case_id"]], global_call["projected_payload"])
        row = {
            "case_id": case["case_id"], "route": case["route"], "global_context_call": global_call,
            "units": units, "task_status": task_status(units, case["expected_task_status"]) if global_call["projected_payload"] is not None else "protocol_failure",
            "expected_task_status": case["expected_task_status"],
        }
        append_jsonl(ARM_B, row)
        print(f"B {index:02d}/25 {case['case_id']} => {row['task_status']}", flush=True)


def main() -> None:
    config = load_vlm_config()
    if config.base_url.rstrip("/") != "http://192.168.250.9:11434/v1" or config.model != "qwen3.8:27b-mtp-q4_K_M":
        raise RuntimeError(f"拒绝运行非冻结 Local VLM：{config}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cases = load_cases()
    if not FROZEN_SELECTION.exists():
        FROZEN_SELECTION.write_text(json.dumps({"count": 25, "cases": cases}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence_cache = {}
    for index, case in enumerate(cases, 1):
        evidence_cache[case["case_id"]] = make_evidence(case)
        print(f"EVIDENCE {index:02d}/25 {case['case_id']}", flush=True)
    client = create_vlm_client(config)
    run_arm_a(client, config.model, cases, evidence_cache)
    run_arm_c(client, config.model, cases, evidence_cache)
    run_arm_b(client, config.model, cases, evidence_cache)


if __name__ == "__main__":
    main()
