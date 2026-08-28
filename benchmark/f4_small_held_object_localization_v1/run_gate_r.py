"""F4::017 Gate R benchmark-only runner；未授权时必须在任何 VLM 调用前拒绝。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable
from unittest.mock import patch

from visual_agent import relations
from visual_agent.vlm_client import VlmConfig, create_vlm_client, load_vlm_config


EVIDENCE_REVIEWED_HEAD = "3308fee09ac2d3fa827f81854c1d556a0b4c87f6"
PRODUCTION_REFERENCE = "be54f3c89171d8b16f53c82397e9f468fb4b4c97"
GATE_L_RUNNER_SHA = "984d882dd3f9246403cb10a0be4d738840511963"
FROZEN_MODEL = "qwen3.8:27b-mtp-q4_K_M"
FROZEN_BASE_URL = "http://192.168.250.9:11434/v1"
FROZEN_TIMEOUT = 120.0
FROZEN_FILE_SHA256 = {
    "contract_candidate.json": "747a65b7221c64f35141656f57028e1e6c6aa554d6ba61e7762c4157761ac03d",
    "selection_candidate.json": "7d8e89cbac9371883d2013276632965b18243cae3d57c23810c7761a2d583a22",
    "gate_l_execution/raw_result.json": "6ee778a3af13c410eeb255946460ac3fee27c2860a12f4bc9ffafc6da76244be",
    "gate_l_execution/artifact_manifest.json": "00a8532fdeaad8aaa97e004260d3feaaa537d742e6dd0c0ce105667b72b5c5d7",
}
PRODUCTION_FILE_SHA256 = {
    "visual_agent/relations.py": "293f2c983f792d541ec0c6021ef49e82ae0d0b8553963bc925424b555286f968",
    "visual_agent/qwen_protocol.py": "89ccd004b9738804ecace48478044af660d5497aafa4d7753bc5e4a4c46ebfb3",
    "visual_agent/vlm_client.py": "a36782166b41fde299cb3cd328fb145bc0597ae8bd49c0510f1eb6d832a82c88",
}
HISTORICAL_GATE2_SHA256 = "ee83183c9c919f62ad9f22f0eeee905e613e92dc3a905641bceee8cb8878fe78"


class GateRFailure(RuntimeError):
    def __init__(self, stage: str, category: str, message: str):
        super().__init__(message)
        self.stage = stage
        self.category = category


@dataclass(frozen=True)
class Slot:
    slot_id: str
    arm: str
    repetition: int


@dataclass(frozen=True)
class FrozenInputs:
    image_path: Path
    subject: dict
    candidates_by_arm: dict[str, tuple[dict, ...]]
    target_ids_by_arm: dict[str, frozenset[str]]
    slots: tuple[Slot, ...]
    evidence_head: str
    authorization_sha256: str
    runner_review_sha: str


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def localization_metrics(bbox: list[float], reference: dict) -> bool:
    x1, y1, x2, y2 = bbox
    rx1, ry1, rx2, ry2 = reference["bbox"]
    cx, cy = reference["center"]
    contains = x1 <= cx <= x2 and y1 <= cy <= y2
    candidate_center = ((x1 + x2) / 2, (y1 + y2) / 2)
    center_inside = (
        rx1 <= candidate_center[0] <= rx2 and ry1 <= candidate_center[1] <= ry2
    )
    intersection = max(0.0, min(x2, rx2) - max(x1, rx1)) * max(
        0.0, min(y2, ry2) - max(y1, ry1)
    )
    union = (x2 - x1) * (y2 - y1) + (rx2 - rx1) * (ry2 - ry1) - intersection
    return contains and center_inside and union > 0 and intersection / union >= 0.1


def frozen_slots() -> tuple[Slot, ...]:
    return tuple(
        Slot(f"GATE_R_{arm}_{repetition:02d}", arm, repetition)
        for repetition in range(1, 6)
        for arm in ("B", "C")
    )


def validate_authorization(payload: dict) -> str:
    """独立授权文件在代码审查后新增；原冻结合同字节保持不变。"""
    expected = {
        "schema_version": "GENERAL_RGB_F4_GATE_R_EXECUTION_AUTHORIZATION_V1",
        "status": "GATE_R_RELATION_VLM_EXECUTION_AUTHORIZED",
        "gate_l_evidence_head": EVIDENCE_REVIEWED_HEAD,
        "arms": ["B", "C"],
        "calls_per_arm": 5,
        "scheduled_calls": 10,
        "failed_execution_replacement": False,
        "production_modification_authorized": False,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise GateRFailure("authorization", "authorization_contract", key)
    review_sha = payload.get("runner_review_sha")
    if not isinstance(review_sha, str) or len(review_sha) != 40:
        raise GateRFailure("authorization", "runner_review_sha", str(review_sha))
    return review_sha


def _historical_candidates(path: Path) -> tuple[dict, ...]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    matches = [row for row in rows if row.get("case_id") == "F4::fishing_017.jpeg"]
    if len(matches) != 5:
        raise GateRFailure("preflight", "historical_case_count", str(len(matches)))
    canonical = matches[0]["relation_candidates"]
    if any(row["relation_candidates"] != canonical for row in matches[1:]):
        raise GateRFailure("preflight", "historical_candidate_drift", "F4::017")
    return tuple(dict(candidate) for candidate in canonical)


def build_candidate_universe(
    historical: tuple[dict, ...], gate_l_arm: dict, reference: dict
) -> tuple[tuple[dict, ...], frozenset[str]]:
    candidates = [dict(candidate) for candidate in historical]
    target_ids: set[str] = set()
    for index, detection in enumerate(gate_l_arm["deduplicated_detections"], start=1):
        candidate_id = f"R{len(historical) + index}"
        candidate = {
            "id": candidate_id,
            "object": "fish",
            "text_label": detection["text_label"],
            "bbox": list(detection["bbox"]),
            "dino_confidence": detection["confidence"],
        }
        candidates.append(candidate)
        if localization_metrics(candidate["bbox"], reference):
            target_ids.add(candidate_id)
    if not target_ids:
        raise GateRFailure("preflight", "arm_has_no_gate_l_target", "")
    return tuple(candidates), frozenset(target_ids)


def load_frozen_inputs(
    repo_root: Path, evidence_root: Path, authorization_path: Path
) -> FrozenInputs:
    """锁定代码、合同、Gate L 字节和历史 candidate universe；不创建 client。"""
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", "benchmark", "visual_agent"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode or status.stdout.strip():
        raise GateRFailure("preflight", "working_tree_dirty", status.stdout.strip())
    for relative, expected in PRODUCTION_FILE_SHA256.items():
        if sha256(repo_root / relative) != expected:
            raise GateRFailure("preflight", "production_contract_drift", relative)

    evidence_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=evidence_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", EVIDENCE_REVIEWED_HEAD, "HEAD"],
        cwd=evidence_root,
        capture_output=True,
        text=True,
        check=False,
    )
    evidence_status = subprocess.run(
        ["git", "status", "--porcelain", "--", "evidence/final_acceptance"],
        cwd=evidence_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if ancestor.returncode or evidence_status.returncode or evidence_status.stdout.strip():
        raise GateRFailure("preflight", "evidence_git_state", evidence_head)
    stage = evidence_root / "evidence/final_acceptance/GENERAL_RGB_F4_SMALL_HELD_OBJECT_LOCALIZATION_V1"
    for relative, expected in FROZEN_FILE_SHA256.items():
        if sha256(stage / relative) != expected:
            raise GateRFailure("preflight", "frozen_evidence_drift", relative)

    contract = json.loads((stage / "contract_candidate.json").read_text(encoding="utf-8"))
    if contract["gate_R"]["authorized"] is not False:
        raise GateRFailure("preflight", "frozen_contract_changed", "gate_R.authorized")
    if not authorization_path.is_file():
        raise GateRFailure("authorization", "authorization_missing", str(authorization_path))
    authorization_sha = sha256(authorization_path)
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    runner_review_sha = validate_authorization(authorization)
    review_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", runner_review_sha, "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    review_drift = subprocess.run(
        [
            "git", "diff", "--quiet", runner_review_sha, "HEAD", "--",
            "benchmark/f4_small_held_object_localization_v1/run_gate_r.py",
            "benchmark/f4_small_held_object_localization_v1/test_gate_r.py",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if review_ancestor.returncode or review_drift.returncode:
        raise GateRFailure("preflight", "runner_review_drift", runner_review_sha)

    selection = json.loads((stage / "selection_candidate.json").read_text(encoding="utf-8"))["cases"][0]
    image_path = evidence_root / selection["image_path"]
    if sha256(image_path) != selection["image_sha256"]:
        raise GateRFailure("preflight", "image_sha", str(image_path))
    gate_l = json.loads((stage / "gate_l_execution/raw_result.json").read_text(encoding="utf-8"))
    if gate_l["terminal_status"] != "success" or not gate_l["gate_L"]["B_or_C_success"]:
        raise GateRFailure("preflight", "gate_L_not_passed", "")

    historical_path = evidence_root / (
        "evidence/final_acceptance/GENERAL_RGB_FINAL_ACCEPTANCE_REMEDIATION_V1/"
        "targeted_gates/raw_execution_gate2.jsonl"
    )
    if sha256(historical_path) != HISTORICAL_GATE2_SHA256:
        raise GateRFailure("preflight", "historical_gate2_sha", str(historical_path))
    historical = _historical_candidates(historical_path)
    candidates_by_arm = {}
    target_ids_by_arm = {}
    for arm in ("B", "C"):
        candidates, target_ids = build_candidate_universe(
            historical, gate_l["arms"][arm], gate_l["reference"]
        )
        candidates_by_arm[arm] = candidates
        target_ids_by_arm[arm] = target_ids
    subject = {
        "id": "A",
        "label": "拿着鱼的人",
        "text_label": "person",
        "bbox": list(contract["subject"]["bbox"]),
        "confidence": 0.7549,
    }
    return FrozenInputs(
        image_path=image_path,
        subject=subject,
        candidates_by_arm=candidates_by_arm,
        target_ids_by_arm=target_ids_by_arm,
        slots=frozen_slots(),
        evidence_head=evidence_head,
        authorization_sha256=authorization_sha,
        runner_review_sha=runner_review_sha,
    )


class _MeteredCompletions:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.latencies: list[float] = []
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0

    def create(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            response = self.wrapped.create(*args, **kwargs)
        finally:
            self.latencies.append(time.perf_counter() - started)
        usage = getattr(response, "usage", None)
        if usage:
            self.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
            self.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
            self.total_tokens += int(getattr(usage, "total_tokens", 0) or 0)
        return response


class _MeteredClient:
    def __init__(self, wrapped):
        self.completions = _MeteredCompletions(wrapped.chat.completions)
        self.chat = SimpleNamespace(completions=self.completions)


def verify_slot(
    inputs: FrozenInputs,
    slot: Slot,
    *,
    config_loader: Callable[[], VlmConfig] = load_vlm_config,
    client_factory: Callable[[VlmConfig], object] = create_vlm_client,
    verifier: Callable[..., tuple[list[dict], dict]] = relations.verify_relations,
) -> dict:
    config = config_loader()
    if (
        config.model != FROZEN_MODEL
        or config.base_url.rstrip("/") != FROZEN_BASE_URL
        or config.timeout != FROZEN_TIMEOUT
    ):
        raise GateRFailure("preflight", "frozen_vlm_config", repr(config))
    metered = _MeteredClient(client_factory(config))
    candidates = [dict(item) for item in inputs.candidates_by_arm[slot.arm]]
    started = time.perf_counter()
    with patch.object(relations, "_client", return_value=metered):
        bindings, protocol = verifier(
            inputs.image_path,
            [dict(inputs.subject)],
            candidates,
            "fish",
            "held_by_target",
        )
    target_ids = inputs.target_ids_by_arm[slot.arm]
    target_satisfied = any(
        row["related_id"] in target_ids and row["status"] == "satisfied"
        for row in bindings
    )
    non_target_satisfied = [
        row["related_id"]
        for row in bindings
        if row["related_id"] not in target_ids and row["status"] == "satisfied"
    ]
    return {
        "bindings": bindings,
        "protocol": protocol,
        "target_ids": sorted(target_ids),
        "target_satisfied": target_satisfied,
        "non_target_satisfied_ids": non_target_satisfied,
        "subject_retained": target_satisfied,
        "model": config.model,
        "base_url": config.base_url,
        "timeout": config.timeout,
        "latency_seconds": time.perf_counter() - started,
        "request_latency_seconds": metered.completions.latencies,
        "prompt_tokens": metered.completions.prompt_tokens,
        "completion_tokens": metered.completions.completion_tokens,
        "total_tokens": metered.completions.total_tokens,
    }


def run_slots(
    inputs: FrozenInputs,
    result_path: Path,
    verifier: Callable[[FrozenInputs, Slot], dict] = verify_slot,
) -> None:
    expected_slots = frozen_slots()
    if inputs.slots != expected_slots:
        raise GateRFailure("preflight", "slot_schedule_drift", "10 frozen slots required")
    receipt = {
        "evidence_head": inputs.evidence_head,
        "authorization_sha256": inputs.authorization_sha256,
        "runner_review_sha": inputs.runner_review_sha,
        "production_reference": PRODUCTION_REFERENCE,
        "gate_l_runner_sha": GATE_L_RUNNER_SHA,
        "scheduled_slot_ids": [slot.slot_id for slot in inputs.slots],
        "candidate_ids_by_arm": {
            arm: [candidate["id"] for candidate in candidates]
            for arm, candidates in inputs.candidates_by_arm.items()
        },
        "target_ids_by_arm": {
            arm: sorted(targets) for arm, targets in inputs.target_ids_by_arm.items()
        },
    }
    receipt_bytes = (
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    receipt_path = result_path.with_suffix(".preflight.json")
    if receipt_path.exists() and receipt_path.read_bytes() != receipt_bytes:
        raise GateRFailure("preflight", "receipt_mismatch", str(receipt_path))
    if not receipt_path.exists():
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_bytes(receipt_bytes)
    existing = {}
    if result_path.exists():
        existing = {
            row["slot_id"]: row
            for row in map(json.loads, result_path.read_text(encoding="utf-8").splitlines())
        }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    for slot in inputs.slots:
        if slot.slot_id in existing:
            continue
        record = {"slot_id": slot.slot_id, "arm": slot.arm, "repetition": slot.repetition}
        try:
            record.update({"terminal_status": "success", "result": verifier(inputs, slot)})
        except GateRFailure as error:
            record.update(
                {
                    "terminal_status": "failure",
                    "failure_stage": error.stage,
                    "failure_category": error.category,
                    "failure_message": str(error),
                }
            )
        except RuntimeError as error:
            message = str(error)
            if "contract_validation_error" in message:
                category = "validator"
            elif "json_decode_error" in message or "empty_response" in message:
                category = "protocol"
            else:
                category = "provider"
            record.update(
                {
                    "terminal_status": "failure",
                    "failure_stage": category,
                    "failure_category": category,
                    "failure_message": message,
                }
            )
        except Exception as error:
            record.update(
                {
                    "terminal_status": "failure",
                    "failure_stage": "provider_or_protocol",
                    "failure_category": type(error).__name__,
                    "failure_message": str(error),
                }
            )
        with result_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    records = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines()]
    summary = summarize(records)
    result_path.with_suffix(".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def summarize(records: list[dict]) -> dict:
    expected_ids = {slot.slot_id for slot in frozen_slots()}
    if {row["slot_id"] for row in records} != expected_ids or len(records) != 10:
        raise GateRFailure("summary", "slot_coverage", str(len(records)))
    arms = {}
    for arm in ("B", "C"):
        rows = [row for row in records if row["arm"] == arm]
        successful = [row for row in rows if row["terminal_status"] == "success"]
        target_satisfied = sum(
            bool(row["result"]["target_satisfied"]) for row in successful
        )
        subject_retained = sum(
            bool(row["result"]["subject_retained"]) for row in successful
        )
        false_bindings = sum(
            len(row["result"]["non_target_satisfied_ids"]) for row in successful
        )
        failures = len(rows) - len(successful)
        arms[arm] = {
            "scheduled": len(rows),
            "success": len(successful),
            "final_failure": failures,
            "target_small_fish_satisfied": target_satisfied,
            "subject_A_retained": subject_retained,
            "non_target_satisfied": false_bindings,
            "gate_pass": (
                target_satisfied >= 4
                and subject_retained >= 4
                and false_bindings == 0
                and failures == 0
            ),
        }
    return {
        "schema_version": "GENERAL_RGB_F4_SMALL_HELD_OBJECT_GATE_R_SUMMARY_V1",
        "scheduled_calls": 10,
        "failed_execution_replacement": False,
        "arms": arms,
        "gate_R_pass": arms["B"]["gate_pass"] and arms["C"]["gate_pass"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = load_frozen_inputs(
        Path.cwd(), args.evidence_root.resolve(), args.authorization.resolve()
    )
    run_slots(inputs, args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
