"""冻结的 Behavior + Relation 联合确认 runner。

当前提交只实现 runner 与 stub/mock 测试。没有独立授权文件时，preflight 会在
任何 Detector、SAM 或 VLM 调用前拒绝执行。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Iterable
from unittest.mock import patch

from PIL import Image

from visual_agent import pipeline, relations, vlm
from visual_agent.evidence import (
    build_subject_conditioned_grounding_view,
    expanded_candidate_bbox,
)
from visual_agent.grounding import GroundingDetector
from visual_agent.vlm_client import VlmConfig, create_vlm_client, load_vlm_config


STAGE = "GENERAL_RGB_BEHAVIOR_RELATION_JOINT_TARGETED_CONFIRMATION_V1"
FROZEN_EVIDENCE_HEAD = "30fa9cddd851f376831b2bd3d940f6ab1165c084"
EXECUTION_BASE = "be54f3c89171d8b16f53c82397e9f468fb4b4c97"
FORMAL_PRODUCTION_MASTER = "4dac9cb3823e22e90ff3bb8157c6544c6c6b88fd"
FROZEN_MODEL = "qwen3.8:27b-mtp-q4_K_M"
FROZEN_BASE_URL = "http://192.168.250.9:11434/v1"
FROZEN_TIMEOUT = 120.0
FROZEN_CONCURRENCY = 1
FROZEN_MANIFEST_SHA256 = "c80996f6792df1e00982ce5c23d9c4348e040f2e3a9a29eba15a53ee029fe437"
FROZEN_CONTRACT_SHA256 = "eb2bc508a32b8e7d3ee74776ca01923d5741d6c57bf03d9faf6dd7f4f3ffd780"
FROZEN_SELECTION_SHA256 = "383b9742b31ec7c92d53f46c041bb6cdf58b92fdda8b640f62570a89a6074a2f"
R3_SELECTION_SHA256 = "37fb7fcb97e5a324a4d76d81abe805e947e220420c97102eb6d690cc64c44563"
R3_PREFLIGHT_SHA256 = "4eb00894b6fb566c7fb22b612fb762391e03badac670fd1bbf9958d6d36bdad7"
F4_CONTRACT_SHA256 = "747a65b7221c64f35141656f57028e1e6c6aa554d6ba61e7762c4157761ac03d"
FROZEN_BEHAVIOR_SLOT_SEQUENCE_SHA256 = "67dc2d897f627258354d5fe6a57656a42469b10e6393a1d1129dd47273503622"
FROZEN_RELATION_SLOT_SEQUENCE_SHA256 = "5d3bf015b8d17ec4c2806f4ea4e208cb6411147c5319a5936a1ce411d4c754c7"

PRODUCTION_FILE_SHA256 = {
    "visual_agent/pipeline.py": "531903d340e64faa6e745c9fb83d65532d553ff604a87789f2057a57aadb0452",
    "visual_agent/evidence.py": "8dc4f1d6a62f1873b1479a78c08130d0c4d79286a2afcaa24d11f93cb5749747",
    "visual_agent/vlm.py": "a2df5c9605deb3ee9d5e7803eab0effa83e5c6c21cc928633a0460f54ae6d83e",
    "visual_agent/relations.py": "293f2c983f792d541ec0c6021ef49e82ae0d0b8553963bc925424b555286f968",
    "visual_agent/grounding.py": "ac56602ecd1c4d09286784fc17eb79c18fe3ebb4c7f98f62ae96e0167c28f3be",
    "visual_agent/qwen_protocol.py": "89ccd004b9738804ecace48478044af660d5497aafa4d7753bc5e4a4c46ebfb3",
    "visual_agent/vlm_client.py": "a36782166b41fde299cb3cd328fb145bc0597ae8bd49c0510f1eb6d832a82c88",
    "visual_agent/deepseek_agent.py": "cdc6be9cdc4b518734b014ca9e44144d7b4da1895da6bdb74de9fed5290f1f12",
}
class JointFailure(RuntimeError):
    def __init__(self, stage: str, category: str, message: str, details=None):
        super().__init__(message)
        self.stage = stage
        self.category = category
        self.details = details or {}


@dataclass(frozen=True)
class BehaviorSlot:
    slot_id: str
    case_id: str
    repetition: int
    candidate: dict
    candidate_count: int
    identity_risk: bool
    semantic_constraint: str


@dataclass(frozen=True)
class RelationSlot:
    slot_id: str
    case: dict
    repetition: int


@dataclass(frozen=True)
class PreflightReceipt:
    evidence_head: str
    runner_review_sha: str
    authorization_sha256: str
    behavior_slots: tuple[BehaviorSlot, ...]
    relation_slots: tuple[RelationSlot, ...]
    behavior_manifests: dict[str, Path]
    relation_reference: dict

    def as_record(self) -> dict:
        return {
            "frozen_evidence_head": FROZEN_EVIDENCE_HEAD,
            "observed_evidence_head": self.evidence_head,
            "execution_base": EXECUTION_BASE,
            "formal_production_master": FORMAL_PRODUCTION_MASTER,
            "runner_review_sha": self.runner_review_sha,
            "authorization_sha256": self.authorization_sha256,
            "contract_sha256": FROZEN_CONTRACT_SHA256,
            "selection_sha256": FROZEN_SELECTION_SHA256,
            "behavior_slot_ids": [item.slot_id for item in self.behavior_slots],
            "relation_slot_ids": [item.slot_id for item in self.relation_slots],
            "behavior_slot_sequence_sha256": _behavior_sequence_sha(self.behavior_slots),
            "relation_slot_sequence_sha256": _relation_sequence_sha(self.relation_slots),
            "concurrency": FROZEN_CONCURRENCY,
            "failed_execution_replacement": False,
        }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sequence_sha(rows: list[dict]) -> str:
    payload = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _behavior_sequence_sha(slots: Iterable[BehaviorSlot]) -> str:
    return _sequence_sha(
        [
            {
                "slot_id": item.slot_id,
                "case_id": item.case_id,
                "repetition": item.repetition,
                "candidate_id": item.candidate["id"],
                "candidate_count": item.candidate_count,
                "identity_risk": item.identity_risk,
                "semantic_constraint": item.semantic_constraint,
            }
            for item in slots
        ]
    )


def _relation_sequence_sha(slots: Iterable[RelationSlot]) -> str:
    return _sequence_sha(
        [
            {
                "slot_id": item.slot_id,
                "case_id": item.case["case_id"],
                "repetition": item.repetition,
                "image_sha256": item.case["image_sha256"],
                "role": item.case["role"],
            }
            for item in slots
        ]
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
    )


def _require_git(repo: Path, category: str, *args: str) -> str:
    result = _git(repo, *args)
    if result.returncode:
        raise JointFailure("preflight", category, "git " + " ".join(args))
    return result.stdout.strip()


def _require_exact_reviewed_head(repo: Path, review_sha: str) -> None:
    actual = _require_git(repo, "runner_review_head", "rev-parse", "HEAD")
    if actual != review_sha:
        raise JointFailure(
            "preflight",
            "runner_review_head",
            f"HEAD={actual}, reviewed={review_sha}",
        )


def validate_authorization(payload: dict) -> str:
    expected = {
        "schema_version": "GENERAL_RGB_BEHAVIOR_RELATION_JOINT_EXECUTION_AUTHORIZATION_V1",
        "status": "MODEL_EXECUTION_AUTHORIZED",
        "frozen_evidence_head": FROZEN_EVIDENCE_HEAD,
        "execution_base": EXECUTION_BASE,
        "model": FROZEN_MODEL,
        "base_url": FROZEN_BASE_URL,
        "timeout_seconds": 120,
        "concurrency": 1,
        "failed_execution_replacement": False,
        "production_modification_authorized": False,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise JointFailure("authorization", "authorization_contract", key)
    review_sha = payload.get("runner_review_sha")
    if not isinstance(review_sha, str) or len(review_sha) != 40:
        raise JointFailure("authorization", "runner_review_sha", repr(review_sha))
    return review_sha


def _verify_file(path: Path, expected_sha: str, category: str) -> None:
    if not path.is_file() or sha256(path) != expected_sha:
        raise JointFailure("preflight", category, str(path))


def _verify_frozen_git_blob(
    repo: Path, commit: str, relative: str, expected_sha: str
) -> None:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if result.returncode or hashlib.sha256(result.stdout).hexdigest() != expected_sha:
        raise JointFailure("preflight", "frozen_git_blob_sha", relative)


def _verify_artifact_manifest(path: Path) -> dict:
    payload = _json(path)
    for row in payload.get("artifacts", []):
        artifact = Path(row["path"])
        if not artifact.is_absolute():
            artifact = path.parent / artifact
        if (
            not artifact.is_file()
            or sha256(artifact) != row["sha256"]
            or artifact.stat().st_size != row["bytes"]
        ):
            raise JointFailure("preflight", "behavior_evidence_drift", str(artifact))
    return payload


def bbox_iou(left: Iterable[float], right: Iterable[float]) -> float:
    lx1, ly1, lx2, ly2 = left
    rx1, ry1, rx2, ry2 = right
    intersection = max(0.0, min(lx2, rx2) - max(lx1, rx1)) * max(
        0.0, min(ly2, ry2) - max(ly1, ry1)
    )
    union = max(0.0, lx2 - lx1) * max(0.0, ly2 - ly1) + max(
        0.0, rx2 - rx1
    ) * max(0.0, ry2 - ry1) - intersection
    return intersection / union if union else 0.0


def _bbox_coverage(inner: Iterable[float], outer: Iterable[float]) -> float:
    ix1, iy1, ix2, iy2 = inner
    ox1, oy1, ox2, oy2 = outer
    intersection = max(0.0, min(ix2, ox2) - max(ix1, ox1)) * max(
        0.0, min(iy2, oy2) - max(iy1, oy1)
    )
    area = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    return intersection / area if area else 0.0


def identity_contamination_risk(case: dict, candidate: dict, image_size) -> bool:
    if len(case["candidates"]) < 2:
        return False
    crop = expanded_candidate_bbox(image_size, candidate["bbox"])
    for neighbor in case["candidates"]:
        if neighbor["id"] == candidate["id"]:
            continue
        x1, y1, x2, y2 = neighbor["bbox"]
        center = ((x1 + x2) / 2, (y1 + y2) / 2)
        if (
            _bbox_coverage(neighbor["bbox"], crop) >= 0.70
            and crop[0] <= center[0] <= crop[2]
            and crop[1] <= center[1] <= crop[3]
        ):
            return True
    return False


def _behavior_slots(r3_selection: dict, selected_ids: set[str], evidence_root: Path):
    slots = []
    for case in r3_selection["cases"]:
        if case["case_id"] not in selected_ids:
            continue
        image_path = evidence_root / case["image_path"]
        _verify_file(image_path, case["image_sha256"], "behavior_image_sha")
        with Image.open(image_path) as image:
            image_size = image.size
        repetitions = int(case["repetitions_per_arm"])
        for repetition in range(1, repetitions + 1):
            for candidate in case["candidates"]:
                slots.append(
                    BehaviorSlot(
                        slot_id=f"BEHAVIOR|{case['case_id']}|r{repetition}|{candidate['id']}",
                        case_id=case["case_id"],
                        repetition=repetition,
                        candidate=dict(candidate),
                        candidate_count=len(case["candidates"]),
                        identity_risk=identity_contamination_risk(
                            case, candidate, image_size
                        ),
                        semantic_constraint="正在钓鱼",
                    )
                )
    if len(slots) != 35:
        raise JointFailure("preflight", "behavior_slot_count", str(len(slots)))
    return tuple(slots)


def _relation_slots(cases: list[dict], selection_root: Path):
    slots = []
    for case in cases:
        image = selection_root / case["image_path"]
        _verify_file(image, case["image_sha256"], "relation_image_sha")
        frozen = dict(case)
        frozen["resolved_image_path"] = str(image.resolve())
        for repetition in range(1, int(case["repetitions"]) + 1):
            slots.append(
                RelationSlot(
                    f"RELATION|{case['case_id']}|r{repetition}",
                    frozen,
                    repetition,
                )
            )
    if len(slots) != 13:
        raise JointFailure("preflight", "relation_slot_count", str(len(slots)))
    return tuple(slots)


def verify_preflight(
    repo_root: Path, evidence_root: Path, authorization_path: Path
) -> PreflightReceipt:
    """在任何模型/Detector/SAM 创建前锁定代码、合同、selection 与资产。"""
    if not authorization_path.is_file():
        raise JointFailure("authorization", "authorization_missing", str(authorization_path))
    authorization_sha = sha256(authorization_path)
    review_sha = validate_authorization(_json(authorization_path))

    _require_git(repo_root, "execution_base", "merge-base", "--is-ancestor", EXECUTION_BASE, "HEAD")
    _require_exact_reviewed_head(repo_root, review_sha)
    dirty = _git(repo_root, "status", "--porcelain")
    if dirty.returncode or dirty.stdout.strip():
        raise JointFailure("preflight", "working_tree_dirty", dirty.stdout.strip())
    for relative, expected in PRODUCTION_FILE_SHA256.items():
        _verify_file(repo_root / relative, expected, "production_file_sha")

    evidence_head = _require_git(evidence_root, "evidence_git", "rev-parse", "HEAD")
    _require_git(evidence_root, "frozen_evidence_head", "merge-base", "--is-ancestor", FROZEN_EVIDENCE_HEAD, "HEAD")
    evidence_dirty = _git(evidence_root, "status", "--porcelain", "--", "evidence/final_acceptance")
    if evidence_dirty.returncode or evidence_dirty.stdout.strip():
        raise JointFailure("preflight", "evidence_working_tree_dirty", evidence_dirty.stdout.strip())

    stage = evidence_root / "evidence/final_acceptance" / STAGE
    _verify_frozen_git_blob(
        evidence_root,
        FROZEN_EVIDENCE_HEAD,
        f"evidence/final_acceptance/{STAGE}/manifest.json",
        FROZEN_MANIFEST_SHA256,
    )
    _verify_file(stage / "contract_candidate.json", FROZEN_CONTRACT_SHA256, "frozen_contract_sha")
    _verify_file(stage / "selection_candidate.json", FROZEN_SELECTION_SHA256, "frozen_selection_sha")
    contract = _json(stage / "contract_candidate.json")
    selection = _json(stage / "selection_candidate.json")
    if (
        contract.get("status") != "CONTRACT_FROZEN"
        or contract.get("contract_frozen") is not True
        or contract.get("model_execution_authorized") is not False
        or contract.get("joint_confirmation_execution_base") != EXECUTION_BASE
        or contract["evaluation"].get("concurrency") != 1
        or contract["evaluation"].get("failed_execution_replacement") is not False
    ):
        raise JointFailure("preflight", "frozen_contract_state", STAGE)

    r3_stage = evidence_root / "evidence/final_acceptance/GENERAL_RGB_R3_CANDIDATE_IDENTITY_REMEDIATION_V1"
    r3_selection_path = r3_stage / "frozen_selection.json"
    r3_preflight_path = r3_stage / "execution/results.preflight.json"
    _verify_file(r3_selection_path, R3_SELECTION_SHA256, "r3_selection_sha")
    _verify_file(r3_preflight_path, R3_PREFLIGHT_SHA256, "r3_preflight_sha")
    r3_selection = _json(r3_selection_path)
    r3_preflight = _json(r3_preflight_path)
    selected_ids = {row["case_id"] for row in selection["behavior_source"]["cases"]}
    if selected_ids != {row["case_id"] for row in r3_selection["cases"]}:
        raise JointFailure("preflight", "behavior_selection_binding", "case ids")
    manifests = {}
    for binding in r3_preflight["case_bindings"]:
        case_id = binding["case_id"]
        path = Path(binding["evidence_manifest"]["path"])
        if not path.is_file():
            path = r3_stage / "execution/evidence" / binding["image_sha256"] / "manifest.json"
        _verify_file(path, binding["evidence_manifest"]["sha256"], "behavior_manifest_sha")
        payload = _verify_artifact_manifest(path)
        if payload.get("case_id") != case_id or payload.get("source_image", {}).get("sha256") != binding["image_sha256"]:
            raise JointFailure("preflight", "behavior_manifest_binding", case_id)
        manifests[case_id] = path

    f4_contract_path = evidence_root / "evidence/final_acceptance/GENERAL_RGB_F4_SMALL_HELD_OBJECT_LOCALIZATION_V1/contract_candidate.json"
    _verify_file(f4_contract_path, F4_CONTRACT_SHA256, "f4_contract_sha")
    reference = _json(f4_contract_path)["reference"]
    return PreflightReceipt(
        evidence_head=evidence_head,
        runner_review_sha=review_sha,
        authorization_sha256=authorization_sha,
        behavior_slots=_behavior_slots(r3_selection, selected_ids, evidence_root),
        relation_slots=_relation_slots(selection["relation_cases"], stage),
        behavior_manifests=manifests,
        relation_reference=reference,
    )


class MeteredCompletions:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.latencies = []
        self.prompt_tokens = self.completion_tokens = self.total_tokens = 0

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


class MeteredClient:
    def __init__(self, wrapped):
        self.completions = MeteredCompletions(wrapped.chat.completions)
        self.chat = SimpleNamespace(completions=self.completions)


def frozen_vlm_config(loader=load_vlm_config) -> VlmConfig:
    config = loader()
    if (
        config.model != FROZEN_MODEL
        or config.base_url.rstrip("/") != FROZEN_BASE_URL
        or config.timeout != FROZEN_TIMEOUT
    ):
        raise JointFailure("preflight", "frozen_vlm_config", repr(config))
    return config


def _evidence_records(manifest_path: Path) -> dict:
    payload = _verify_artifact_manifest(manifest_path)
    return {
        (str(row["candidate_id"]), str(row["arm"]), str(row["evidence_type"])): row
        for row in payload["artifacts"]
    }


def _load_evidence(records: dict, candidate_id: str, arm: str, kind: str):
    row = records[(candidate_id, arm, kind)]
    path = Path(row["path"])
    if not path.is_file():
        raise JointFailure("evidence", "artifact_missing", str(path))
    _verify_file(path, row["sha256"], "evidence_artifact_sha")
    with Image.open(path) as image:
        return image.convert("RGB").copy(), row["sha256"]


def verify_behavior(
    slot: BehaviorSlot,
    images: tuple[Image.Image, ...],
    *,
    config_loader=load_vlm_config,
    client_factory=create_vlm_client,
    verifier=vlm.verify_candidate_constraints,
) -> dict:
    config = frozen_vlm_config(config_loader)
    metered = MeteredClient(client_factory(config))
    started = time.perf_counter()
    try:
        with patch.object(vlm, "_client", return_value=metered):
            checks, protocol = verifier(
                {"id": slot.candidate["id"], "bbox": slot.candidate["bbox"]},
                [{"text": slot.semantic_constraint, "route": "behavior"}],
                list(images),
                "behavior",
            )
        status = checks[0]["status"]
        if status not in {"satisfied", "not_satisfied", "uncertain"}:
            raise JointFailure("validator", "invalid_status", str(status))
    except JointFailure:
        raise
    except RuntimeError as error:
        message = str(error)
        stage = "validator" if "contract_validation_error" in message else "protocol" if "json_decode_error" in message or "empty_response" in message else "provider"
        raise JointFailure(stage, stage, message) from error
    return {
        "status": status,
        "evidence": checks[0]["evidence"],
        "protocol": protocol,
        "model": config.model,
        "base_url": config.base_url,
        "latency_seconds": time.perf_counter() - started,
        "request_latency_seconds": metered.completions.latencies,
        "prompt_tokens": metered.completions.prompt_tokens,
        "completion_tokens": metered.completions.completion_tokens,
        "total_tokens": metered.completions.total_tokens,
    }


def run_behavior_slot(
    slot: BehaviorSlot,
    manifest_path: Path,
    verifier: Callable[[BehaviorSlot, tuple[Image.Image, ...]], dict] = verify_behavior,
) -> dict:
    records = _evidence_records(manifest_path)
    first_arm = "B" if slot.identity_risk else "A"
    isolated, isolated_sha = _load_evidence(records, slot.candidate["id"], first_arm, "isolated")
    local, local_sha = _load_evidence(records, slot.candidate["id"], first_arm, "local")
    first = verifier(slot, (isolated, local))
    record = {
        "first_pass": first,
        "first_pass_arm": first_arm,
        "first_pass_evidence_sha256": [isolated_sha, local_sha],
        "identity_risk": slot.identity_risk,
        "candidate_count": slot.candidate_count,
        "fallback_attempted": False,
    }
    status = first["status"]
    fallback_arm = None
    route = "BINARY_IMMUTABLE"
    if status == "uncertain" and slot.candidate_count == 1:
        route = "SINGLE_CANDIDATE_UNCERTAIN_IMMUTABLE"
    elif status == "uncertain" and slot.candidate_count >= 2:
        route = "MULTI_CANDIDATE_FULL_SCENE_DISAMBIGUATION"
        fallback_arm = "C" if slot.identity_risk else "A"
    elif status == "not_satisfied" and slot.semantic_constraint == "正在钓鱼":
        route = "OBJECT_MEDIATED_NOT_SATISFIED_ESCALATION"
        fallback_arm = "C"
    final = first
    if fallback_arm:
        full_scene, full_sha = _load_evidence(records, slot.candidate["id"], fallback_arm, "full_scene")
        fallback = verifier(slot, (isolated, local, full_scene))
        record.update(
            {
                "fallback_attempted": True,
                "fallback_arm": fallback_arm,
                "fallback_evidence_sha256": full_sha,
                "fallback": fallback,
            }
        )
        final = fallback
    allowed = set(slot.candidate.get("allowed", [slot.candidate.get("expected")]))
    record.update(
        {
            "routing": route,
            "final_status": final["status"],
            "expected_statuses": sorted(item for item in allowed if item),
            "candidate_correct": final["status"] in allowed,
            "false_assignment": (
                final["status"] == "satisfied"
                and "satisfied" not in allowed
            ),
            "fallback_harm": bool(fallback_arm and final["status"] not in allowed),
        }
    )
    return record


def relation_plan(case: dict) -> dict:
    label = {
        "F4::fishing_017.jpeg": "人",
        "F2::fishing_005.jpeg": "拿鱼竿的人",
        "F2::fishing_024.jpeg": "拿着鱼竿的人",
        "core_003": "手持雨伞的人",
        "core_014": "人",
    }[case["case_id"]]
    constraint = "拿着鱼" if case["related_object"] == "fish" else "拿着鱼竿" if case["related_object"] == "fishing rod" else "手持雨伞"
    action = "highlight" if case["case_id"] == "F4::fishing_017.jpeg" else "outline"
    return {
        "target_object": "person",
        "label": label,
        "constraints": [{"text": constraint, "route": "relation"}],
        "action": {"type": action},
        "related_objects": [{"object": case["related_object"], "relation": "held_by_target"}],
    }


def remap_bbox(bbox, crop):
    return [bbox[0] + crop[0], bbox[1] + crop[1], bbox[2] + crop[0], bbox[3] + crop[1]]


def stable_admit(hand_candidates: list[dict], old_candidates: list[dict]):
    ordered = sorted(hand_candidates, key=lambda item: (-item["dino_confidence"], *item["bbox"]))
    kept = []
    for item in ordered:
        if any(bbox_iou(item["bbox"], old["bbox"]) >= 0.80 for old in old_candidates):
            continue
        if any(bbox_iou(item["bbox"], prior["bbox"]) >= 0.80 for prior in kept):
            continue
        kept.append(dict(item))
    for index, item in enumerate(kept, start=len(old_candidates) + 1):
        item["id"] = f"R{index}"
    return kept


def hand_conditioned_candidates(
    image_path: Path,
    subject: dict,
    related_object: str,
    old_candidates: list[dict],
    detector: GroundingDetector,
) -> tuple[list[dict], dict]:
    view, base = build_subject_conditioned_grounding_view(image_path, subject["bbox"])
    calls = []
    with tempfile.TemporaryDirectory(prefix="joint_relation_") as directory:
        directory = Path(directory)
        base_path = directory / "subject_context.png"
        view.save(base_path, format="PNG")
        hands = detector.detect(base_path, "hand", threshold=0.30)
        calls.append({"query": "hand", "threshold": 0.30, "count": len(hands)})
        eligible = []
        for row in hands:
            original = remap_bbox(row["bbox"], base)
            x1, y1, x2, y2 = original
            center = ((x1 + x2) / 2, (y1 + y2) / 2)
            if subject["bbox"][0] <= center[0] <= subject["bbox"][2] and subject["bbox"][1] <= center[1] <= subject["bbox"][3]:
                eligible.append({**row, "bbox": original})
        eligible.sort(key=lambda item: (-item["confidence"], *item["bbox"]))
        detections = []
        for hand_index, hand in enumerate(eligible[:2], 1):
            x1, y1, x2, y2 = hand["bbox"]
            width, height = x2 - x1, y2 - y1
            crop = [
                max(base[0], math.floor(x1 - width)),
                max(base[1], math.floor(y1 - height)),
                min(base[2], math.ceil(x2 + width)),
                min(base[3], math.ceil(y2 + height)),
            ]
            local_crop = [crop[0] - base[0], crop[1] - base[1], crop[2] - base[0], crop[3] - base[1]]
            hand_view = view.crop(tuple(local_crop))
            hand_path = directory / f"hand_{hand_index}.png"
            hand_view.save(hand_path, format="PNG")
            found = detector.detect(hand_path, related_object, threshold=0.30)
            calls.append({"query": related_object, "threshold": 0.30, "count": len(found)})
            for row in found:
                detections.append(
                    {
                        "object": related_object,
                        "text_label": row["text_label"],
                        "bbox": remap_bbox(row["bbox"], crop),
                        "dino_confidence": row["confidence"],
                    }
                )
    admitted = stable_admit(detections, old_candidates)
    return admitted, {"calls": calls, "raw_candidate_count": len(detections), "admitted_count": len(admitted)}


def _target_reference_match(candidate: dict, reference: dict) -> bool:
    x1, y1, x2, y2 = candidate["bbox"]
    rx1, ry1, rx2, ry2 = reference["bbox"]
    cx, cy = reference["center"]
    candidate_center = ((x1 + x2) / 2, (y1 + y2) / 2)
    return (
        x1 <= cx <= x2
        and y1 <= cy <= y2
        and rx1 <= candidate_center[0] <= rx2
        and ry1 <= candidate_center[1] <= ry2
        and bbox_iou(candidate["bbox"], reference["bbox"]) >= 0.10
    )


def run_relation_slot(
    slot: RelationSlot,
    output_root: Path,
    reference: dict,
    *,
    pipeline_runner=pipeline.run_pipeline,
    detector_factory=GroundingDetector,
    relation_verifier=relations.verify_relations,
    config_loader=load_vlm_config,
    client_factory=create_vlm_client,
) -> dict:
    config = frozen_vlm_config(config_loader)
    case = slot.case
    artifact_dir = output_root / slot.slot_id.replace("|", "__")
    image_path = Path(case["resolved_image_path"])
    image_output, json_output = pipeline_runner(
        image_path,
        case["prompt"],
        plan=relation_plan(case),
        final_response=False,
        output_dir=artifact_dir,
    )
    result = _json(json_output)
    plan = relation_plan(case)
    groups = list(result["semantic_groups"])
    incomplete_ids = {
        group["id"] for group in groups if not group["composite_complete"]
    }
    candidates_by_id = {row["id"]: row for row in result["candidates"]}
    relation_subjects = []
    for group in groups:
        subject_row = candidates_by_id.get(group["id"])
        if subject_row is None:
            raise JointFailure(
                "pipeline", "relation_subject_binding", str(group["id"])
            )
        relation_subjects.append(
            {
                "id": group["id"],
                "label": plan["label"],
                "text_label": subject_row["text_label"],
                "bbox": subject_row["bbox"],
                "confidence": subject_row["dino_confidence"],
            }
        )
    fallback_attempts = 0
    hand_detector_calls = 0
    hand_relation_calls = 0
    focused_ownership_calls = 0
    admitted_all = []
    global_candidates = [dict(item) for item in result["relation_candidates"]]
    metered = None
    detector = None
    for subject in relation_subjects:
        if subject["id"] not in incomplete_ids:
            continue
        fallback_attempts += 1
        if detector is None:
            detector = detector_factory()
        admitted, telemetry = hand_conditioned_candidates(
            image_path,
            subject,
            case["related_object"],
            global_candidates,
            detector,
        )
        hand_detector_calls += len(telemetry["calls"])
        admitted_all.extend(admitted)
        # 后一个 subject 的 admission 必须看到前一个 subject 已新增的全局候选，
        # 从而保证跨主体去重与 R ID 全局唯一。
        global_candidates.extend(admitted)

    relation_protocols = []
    combined_bindings = [dict(row) for row in result["relation_bindings"]]
    if admitted_all:
        if metered is None:
            metered = MeteredClient(client_factory(config))
        with patch.object(relations, "_client", return_value=metered):
            # 与 Production R2.3 相同：新增 candidates 对全部 relation-eligible
            # subjects 建立完整 binding matrix，而不是只验证产生 candidate 的主体。
            for subject in relation_subjects:
                bindings, protocol = relation_verifier(
                    image_path,
                    [subject],
                    admitted_all,
                    case["related_object"],
                    "held_by_target",
                )
                hand_relation_calls += 1
                combined_bindings.extend(bindings)
                relation_protocols.append(protocol)
            matrix_protocol_count = len(relation_protocols)
            combined_bindings = pipeline._resolve_focused_ownership(
                image_path,
                combined_bindings,
                global_candidates,
                relation_subjects,
                case["related_object"],
                "held_by_target",
                relation_protocols,
                only_related_ids={row["id"] for row in admitted_all},
            )
            focused_ownership_calls = len(relation_protocols) - matrix_protocol_count

    outcomes = pipeline.resolve_relation_outcomes(
        relation_subjects,
        global_candidates,
        combined_bindings,
        plan,
    )
    satisfied_subjects = {
        subject_id
        for subject_id, outcome in outcomes.items()
        if outcome["status"] == "satisfied"
    }
    target_ids = {
        row["id"] for row in admitted_all if case["case_id"] == "F4::fishing_017.jpeg" and _target_reference_match(row, reference)
    }
    new_ids = {row["id"] for row in admitted_all}
    fallback_bindings = [
        row for row in combined_bindings if row["related_id"] in new_ids
    ]
    hand_satisfied = [row for row in fallback_bindings if row["status"] == "satisfied"]
    return {
        "pipeline_result_json": str(json_output),
        "pipeline_result_json_sha256": sha256(json_output),
        "pipeline_artifact": str(image_output),
        "pipeline_artifact_sha256": sha256(image_output),
        "existing_final_target_count": len(result["targets"]),
        "fallback_attempts": fallback_attempts,
        "hand_detector_calls": hand_detector_calls,
        "hand_relation_calls": hand_relation_calls,
        "focused_ownership_calls": focused_ownership_calls,
        "admitted_candidates": admitted_all,
        "fallback_bindings": fallback_bindings,
        "relation_outcomes": outcomes,
        "final_retained_subject_ids": sorted(satisfied_subjects),
        "target_candidate_ids": sorted(target_ids),
        "target_satisfied": any(row["related_id"] in target_ids for row in hand_satisfied),
        "hand_satisfied_related_ids": [row["related_id"] for row in hand_satisfied],
        "request_latency_seconds": metered.completions.latencies if metered else [],
        "prompt_tokens": metered.completions.prompt_tokens if metered else 0,
        "completion_tokens": metered.completions.completion_tokens if metered else 0,
        "total_tokens": metered.completions.total_tokens if metered else 0,
    }


class ResultRecorder:
    def __init__(self, path: Path):
        self.path = path

    def existing(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]
        if len({row["slot_id"] for row in rows}) != len(rows):
            raise JointFailure("preflight", "duplicate_terminal_record", str(self.path))
        return {row["slot_id"]: row for row in rows}

    def append(self, row: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _terminal(slot_id: str, callback: Callable[[], dict]) -> dict:
    row = {"slot_id": slot_id}
    try:
        row.update({"terminal_status": "success", "result": callback()})
    except JointFailure as error:
        row.update({"terminal_status": "failure", "failure_stage": error.stage, "failure_category": error.category, "failure_message": str(error), "failure_details": error.details})
    except RuntimeError as error:
        message = str(error)
        category = "validator" if "contract_validation_error" in message else "protocol" if "json_decode_error" in message or "empty_response" in message else "provider"
        row.update({"terminal_status": "failure", "failure_stage": category, "failure_category": category, "failure_message": message})
    except Exception as error:
        row.update({"terminal_status": "failure", "failure_stage": "unexpected", "failure_category": type(error).__name__, "failure_message": str(error)})
    return row


def summarize(records: list[dict]) -> dict:
    if len(records) != 48 or len({row["slot_id"] for row in records}) != 48:
        raise JointFailure("summary", "slot_coverage", str(len(records)))
    successful = [row for row in records if row["terminal_status"] == "success"]
    behavior = [row for row in successful if row["result"]["kind"] == "behavior"]
    relation = [row for row in successful if row["result"]["kind"] == "relation"]

    def behavior_rows(case_id, candidate_id=None):
        return [
            row for row in behavior
            if row["result"]["case_id"] == case_id
            and (candidate_id is None or row["result"]["candidate_id"] == candidate_id)
        ]

    f1 = [row for row in behavior if row["result"]["case_id"].startswith("F1::")]
    f1_cases = sorted({row["result"]["case_id"] for row in f1})
    f1_task_correct = 0
    for case_id in f1_cases:
        has_satisfied = any(
            row["result"]["final_status"] == "satisfied"
            for row in behavior_rows(case_id)
        )
        f1_task_correct += has_satisfied == (case_id == "F1::fishing_004.jpeg")

    relation_by_case = {
        case_id: [row for row in relation if row["result"]["case_id"] == case_id]
        for case_id in {
            "F4::fishing_017.jpeg", "F2::fishing_005.jpeg",
            "F2::fishing_024.jpeg", "core_003", "core_014"
        }
    }
    f4 = relation_by_case["F4::fishing_017.jpeg"]
    f2_negative = relation_by_case["F2::fishing_005.jpeg"]
    existing_positive = relation_by_case["F2::fishing_024.jpeg"] + relation_by_case["core_003"]
    core_014 = relation_by_case["core_014"]
    behavior_gate = {
        "challenge_001_bystander_satisfied": sum(row["result"]["final_status"] == "satisfied" for row in behavior_rows("challenge_001", "A")),
        "challenge_001_operator_retained": sum(row["result"]["final_status"] == "satisfied" for row in behavior_rows("challenge_001", "B")),
        "challenge_003_uncertain": sum(row["result"]["final_status"] == "uncertain" for row in behavior_rows("challenge_003", "A")),
        "challenge_004_elder_retained": sum(row["result"]["final_status"] == "satisfied" for row in behavior_rows("challenge_004", "A")),
        "challenge_004_child_satisfied": sum(row["result"]["final_status"] == "satisfied" for row in behavior_rows("challenge_004", "B")),
        "F1_candidate_correct": sum(bool(row["result"]["candidate_correct"]) for row in f1),
        "F1_task_correct": f1_task_correct,
        "F1_fishing_004_A_satisfied": all(row["result"]["final_status"] == "satisfied" for row in behavior_rows("F1::fishing_004.jpeg", "A")),
        "new_false_assignment": sum(bool(row["result"]["false_assignment"]) for row in behavior),
        "fallback_harm": sum(bool(row["result"]["fallback_harm"]) for row in behavior),
    }
    behavior_gate["pass"] = (
        behavior_gate["challenge_001_bystander_satisfied"] == 0
        and behavior_gate["challenge_001_operator_retained"] >= 4
        and behavior_gate["challenge_003_uncertain"] == 5
        and behavior_gate["challenge_004_elder_retained"] >= 4
        and behavior_gate["challenge_004_child_satisfied"] == 0
        and behavior_gate["F1_candidate_correct"] >= 5
        and behavior_gate["F1_task_correct"] >= 3
        and behavior_gate["F1_fishing_004_A_satisfied"]
        and behavior_gate["new_false_assignment"] == 0
        and behavior_gate["fallback_harm"] == 0
    )
    relation_gate = {
        "F4_017_hand_fallback_attempts": sum(row["result"]["fallback_attempts"] == 1 for row in f4),
        "F4_017_target_satisfied": sum(bool(row["result"]["target_satisfied"]) for row in f4),
        "F4_017_subject_retained": sum("A" in row["result"]["final_retained_subject_ids"] for row in f4),
        "F4_017_non_target_satisfied": sum(len(set(row["result"]["hand_satisfied_related_ids"]) - set(row["result"]["target_candidate_ids"])) for row in f4),
        "F2_005_hand_fallback_attempts": sum(row["result"]["fallback_attempts"] == 1 for row in f2_negative),
        "F2_005_subject_retained": sum(bool(row["result"]["final_retained_subject_ids"]) for row in f2_negative),
        "F2_005_hand_candidate_satisfied": sum(len(row["result"]["hand_satisfied_related_ids"]) for row in f2_negative),
        "existing_positive_retained": all(bool(row["result"]["final_retained_subject_ids"]) for row in existing_positive),
        "existing_positive_hand_detector_calls": sum(row["result"]["hand_detector_calls"] for row in existing_positive),
        "existing_positive_hand_relation_calls": sum(row["result"]["hand_relation_calls"] for row in existing_positive),
        "core_014_final_target_count": sum(len(row["result"]["final_retained_subject_ids"]) for row in core_014),
        "core_014_new_false_binding": sum(len(row["result"]["hand_satisfied_related_ids"]) for row in core_014),
    }
    relation_gate["pass"] = (
        relation_gate["F4_017_hand_fallback_attempts"] == 5
        and relation_gate["F4_017_target_satisfied"] >= 4
        and relation_gate["F4_017_subject_retained"] >= 4
        and relation_gate["F4_017_non_target_satisfied"] == 0
        and relation_gate["F2_005_hand_fallback_attempts"] == 5
        and relation_gate["F2_005_subject_retained"] == 0
        and relation_gate["F2_005_hand_candidate_satisfied"] == 0
        and relation_gate["existing_positive_retained"]
        and relation_gate["existing_positive_hand_detector_calls"] == 0
        and relation_gate["existing_positive_hand_relation_calls"] == 0
        and relation_gate["core_014_final_target_count"] == 0
        and relation_gate["core_014_new_false_binding"] == 0
    )
    failures = len(records) - len(successful)
    return {
        "schema_version": "GENERAL_RGB_BEHAVIOR_RELATION_JOINT_TARGETED_CONFIRMATION_SUMMARY_V1",
        "scheduled": 48,
        "terminal_success": len(successful),
        "terminal_failure": failures,
        "failed_execution_replacement": False,
        "behavior": behavior_gate,
        "relation": relation_gate,
        "joint_policy_candidate_confirmed": failures == 0 and behavior_gate["pass"] and relation_gate["pass"],
    }


def run_joint(
    receipt: PreflightReceipt,
    output_root: Path,
    *,
    behavior_executor=run_behavior_slot,
    relation_executor=run_relation_slot,
) -> None:
    if _behavior_sequence_sha(receipt.behavior_slots) != FROZEN_BEHAVIOR_SLOT_SEQUENCE_SHA256:
        raise JointFailure("preflight", "behavior_slot_sequence", "35 frozen slots required")
    if _relation_sequence_sha(receipt.relation_slots) != FROZEN_RELATION_SLOT_SEQUENCE_SHA256:
        raise JointFailure("preflight", "relation_slot_sequence", "13 frozen slots required")
    receipt_path = output_root / "preflight.json"
    receipt_bytes = (json.dumps(receipt.as_record(), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if receipt_path.exists() and receipt_path.read_bytes() != receipt_bytes:
        raise JointFailure("preflight", "receipt_mismatch", str(receipt_path))
    output_root.mkdir(parents=True, exist_ok=True)
    if not receipt_path.exists():
        receipt_path.write_bytes(receipt_bytes)
    recorder = ResultRecorder(output_root / "raw_results.jsonl")
    existing = recorder.existing()
    for slot in receipt.behavior_slots:
        if slot.slot_id in existing:
            continue
        recorder.append(
            _terminal(
                slot.slot_id,
                lambda slot=slot: {
                    "kind": "behavior",
                    "case_id": slot.case_id,
                    "repetition": slot.repetition,
                    "candidate_id": slot.candidate["id"],
                    **behavior_executor(slot, receipt.behavior_manifests[slot.case_id]),
                },
            )
        )
    for slot in receipt.relation_slots:
        if slot.slot_id in existing:
            continue
        recorder.append(
            _terminal(
                slot.slot_id,
                lambda slot=slot: {
                    "kind": "relation",
                    "case_id": slot.case["case_id"],
                    "repetition": slot.repetition,
                    **relation_executor(slot, output_root / "relation_artifacts", receipt.relation_reference),
                },
            )
        )
    records = list(recorder.existing().values())
    (output_root / "summary.json").write_text(
        json.dumps(summarize(records), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    receipt = verify_preflight(repo_root, args.evidence_root.resolve(), args.authorization.resolve())
    run_joint(receipt, args.output_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
