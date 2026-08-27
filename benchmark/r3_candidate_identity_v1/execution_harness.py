"""R3 模型执行 harness；当前提交仅允许 stub/mock 测试。"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable
from unittest.mock import patch

from PIL import Image

from visual_agent import vlm
from visual_agent.vlm_client import (
    DEFAULT_VLM_BASE_URL,
    VlmConfig,
    create_vlm_client,
    load_vlm_config,
)

from .evidence_builder import ArmEvidence
from .runner import (
    ResultRecorder,
    Slot,
    VALID_STATUSES,
    classify_fallback,
    expand_schedule,
)


BUILDER_IMPLEMENTATION_SHA = "0b32695dcd46d13cf22987f5347b2b212e7132c1"
PRODUCTION_BASE_SHA = "be54f3c89171d8b16f53c82397e9f468fb4b4c97"
FROZEN_CONTRACT_SHA256 = "7072d0a6acdbe0beeb9db6f048a35d5d2dc28488696286183887f6c84ef5dd73"
FROZEN_SELECTION_SHA256 = "37fb7fcb97e5a324a4d76d81abe805e947e220420c97102eb6d690cc64c44563"
FROZEN_SCHEDULE_SHA256 = "e531bc803758a0b4827787d619cbd3b4a62c71a0c4647f78cd6d6ada3d08ca84"
FROZEN_VLM_MODEL = "qwen3.8:27b-mtp-q4_K_M"
FROZEN_VLM_BASE_URL = "http://192.168.250.9:11434/v1"
FROZEN_VLM_TIMEOUT = 120.0
BUILDER_FILES = (
    "benchmark/r3_candidate_identity_v1/README.md",
    "benchmark/r3_candidate_identity_v1/__init__.py",
    "benchmark/r3_candidate_identity_v1/evidence_builder.py",
    "benchmark/r3_candidate_identity_v1/mask_cache.py",
    "benchmark/r3_candidate_identity_v1/runner.py",
    "benchmark/test_r3_candidate_identity_builder.py",
)


class HarnessFailure(RuntimeError):
    def __init__(
        self,
        stage: str,
        category: str,
        message: str,
        details: dict[str, object] | None = None,
    ):
        super().__init__(message)
        self.stage = stage
        self.category = category
        self.details = details or {}


@dataclass(frozen=True)
class ManifestBinding:
    path: Path
    sha256: str


@dataclass(frozen=True)
class CaseBinding:
    case_id: str
    prompt: str
    semantic_constraint: str
    image_sha256: str
    candidate_ids: tuple[str, ...]
    mask_manifest: ManifestBinding
    evidence_manifest: ManifestBinding


@dataclass(frozen=True)
class PreflightReceipt:
    builder_implementation_sha: str
    harness_review_sha: str
    harness_review_lock_sha256: str
    contract_sha256: str
    selection_sha256: str
    schedule_sha256: str
    execution_bindings_sha256: str
    scheduled_slot_count: int
    scheduled_slot_sequence_sha256: str
    scheduled_slots: tuple[Slot, ...]
    case_bindings: tuple[CaseBinding, ...]

    def as_record(self) -> dict[str, object]:
        return {
            "builder_implementation_sha": self.builder_implementation_sha,
            "harness_review_sha": self.harness_review_sha,
            "harness_review_lock_sha256": self.harness_review_lock_sha256,
            "contract_sha256": self.contract_sha256,
            "selection_sha256": self.selection_sha256,
            "schedule_sha256": self.schedule_sha256,
            "execution_bindings_sha256": self.execution_bindings_sha256,
            "scheduled_slot_count": self.scheduled_slot_count,
            "scheduled_slot_sequence_sha256": self.scheduled_slot_sequence_sha256,
            "scheduled_slot_ids": [slot.slot_id for slot in self.scheduled_slots],
            "case_bindings": [
                {
                    "case_id": binding.case_id,
                    "prompt": binding.prompt,
                    "semantic_constraint": binding.semantic_constraint,
                    "image_sha256": binding.image_sha256,
                    "candidate_ids": list(binding.candidate_ids),
                    "mask_manifest": {
                        "path": binding.mask_manifest.path.as_posix(),
                        "sha256": binding.mask_manifest.sha256,
                    },
                    "evidence_manifest": {
                        "path": binding.evidence_manifest.path.as_posix(),
                        "sha256": binding.evidence_manifest.sha256,
                    },
                }
                for binding in self.case_bindings
            ],
        }


@dataclass(frozen=True)
class LoadedEvidence:
    images: ArmEvidence
    first_pass_sha256: tuple[str, str]
    fallback_sha256: str | None


@dataclass(frozen=True)
class VerificationOutcome:
    status: str
    evidence: str
    protocol: dict[str, object]
    model: str
    provider: str
    base_url: str
    latency_seconds: float
    request_latency_seconds: tuple[float, ...]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def as_record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "evidence": self.evidence,
            "protocol": self.protocol,
            "model": self.model,
            "provider": self.provider,
            "base_url": self.base_url,
            "latency_seconds": self.latency_seconds,
            "request_latency_seconds": list(self.request_latency_seconds),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_manifest(binding: ManifestBinding) -> dict[str, object]:
    if _sha256(binding.path) != binding.sha256:
        raise HarnessFailure("preflight", "manifest_sha", f"manifest SHA 不一致: {binding.path}")
    payload = json.loads(binding.path.read_text(encoding="utf-8"))
    records = payload.get("artifacts") or payload.get("masks")
    if not isinstance(records, list):
        raise HarnessFailure("preflight", "manifest_contract", f"manifest 缺少 artifacts/masks: {binding.path}")
    for record in records:
        artifact = Path(record["path"])
        if not artifact.is_absolute():
            artifact = binding.path.parent / artifact
        if not artifact.is_file():
            raise HarnessFailure("preflight", "artifact_missing", str(artifact))
        data = artifact.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise HarnessFailure("preflight", "artifact_sha", str(artifact))
        if len(data) != record["bytes"]:
            raise HarnessFailure("preflight", "artifact_bytes", str(artifact))
    return payload


def _slot_sequence_sha256(slots: tuple[Slot, ...] | list[Slot]) -> str:
    payload = [
        {
            "slot_id": slot.slot_id,
            "case_id": slot.case_id,
            "repetition": slot.repetition,
            "arm": slot.arm,
            "candidate": slot.candidate,
        }
        for slot in slots
    ]
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _git_check(
    git_runner: Callable[..., subprocess.CompletedProcess],
    repo_root: Path,
    command: list[str],
    category: str,
) -> None:
    result = git_runner(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise HarnessFailure("preflight", category, " ".join(command))


def verify_execution_preflight(
    *,
    repo_root: Path,
    review_lock_path: Path,
    review_lock_sha256: str,
    contract_path: Path,
    selection_path: Path,
    schedule_path: Path,
    execution_bindings_path: Path,
    mask_manifests: dict[str, ManifestBinding],
    evidence_manifests: dict[str, ManifestBinding],
    git_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> PreflightReceipt:
    """在任何模型调用前核验代码、配置输入、case 绑定、资产与 schedule。"""
    expected_files = (
        (contract_path, FROZEN_CONTRACT_SHA256),
        (selection_path, FROZEN_SELECTION_SHA256),
        (schedule_path, FROZEN_SCHEDULE_SHA256),
    )
    for path, expected in expected_files:
        if not path.is_file() or _sha256(path) != expected:
            raise HarnessFailure("preflight", "frozen_contract_sha", str(path))
    if not review_lock_path.is_file() or _sha256(review_lock_path) != review_lock_sha256:
        raise HarnessFailure("preflight", "review_lock_sha", str(review_lock_path))
    review_lock = json.loads(review_lock_path.read_text(encoding="utf-8"))
    harness_review_sha = str(review_lock["harness_review_sha"])
    if review_lock.get("builder_implementation_sha") != BUILDER_IMPLEMENTATION_SHA:
        raise HarnessFailure("preflight", "builder_review_lock", BUILDER_IMPLEMENTATION_SHA)
    if review_lock.get("production_base_sha") != PRODUCTION_BASE_SHA:
        raise HarnessFailure("preflight", "production_review_lock", PRODUCTION_BASE_SHA)
    for record in review_lock["files"]:
        path = repo_root / record["path"]
        if (
            not path.is_file()
            or _sha256(path) != record["sha256"]
            or path.stat().st_size != record["bytes"]
        ):
            raise HarnessFailure("preflight", "harness_file_sha", str(path))

    _git_check(
        git_runner,
        repo_root,
        ["git", "merge-base", "--is-ancestor", BUILDER_IMPLEMENTATION_SHA, "HEAD"],
        "builder_implementation_sha",
    )
    _git_check(
        git_runner,
        repo_root,
        ["git", "merge-base", "--is-ancestor", harness_review_sha, "HEAD"],
        "harness_review_sha",
    )
    _git_check(
        git_runner,
        repo_root,
        ["git", "merge-base", "--is-ancestor", PRODUCTION_BASE_SHA, "HEAD"],
        "production_base_sha",
    )
    _git_check(
        git_runner,
        repo_root,
        ["git", "diff", "--quiet", BUILDER_IMPLEMENTATION_SHA, "HEAD", "--", *BUILDER_FILES],
        "builder_implementation_drift",
    )
    locked_harness_files = [str(record["path"]) for record in review_lock["files"]]
    _git_check(
        git_runner,
        repo_root,
        ["git", "diff", "--quiet", harness_review_sha, "HEAD", "--", *locked_harness_files],
        "harness_implementation_drift",
    )
    _git_check(
        git_runner,
        repo_root,
        ["git", "diff", "--quiet", PRODUCTION_BASE_SHA, "HEAD", "--", "visual_agent"],
        "production_verifier_drift",
    )
    status = git_runner(
        ["git", "status", "--porcelain", "--", "benchmark", "visual_agent"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0 or status.stdout.strip():
        raise HarnessFailure("preflight", "working_tree_dirty", status.stdout.strip())

    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    execution_bindings_sha = _sha256(execution_bindings_path)
    if execution_bindings_sha != review_lock["execution_bindings_sha256"]:
        raise HarnessFailure("preflight", "execution_bindings_sha", str(execution_bindings_path))
    frozen_bindings = json.loads(
        execution_bindings_path.read_text(encoding="utf-8")
    )["cases"]
    selection_by_id = {str(case["case_id"]): case for case in selection["cases"]}
    binding_by_id = {str(case["case_id"]): case for case in frozen_bindings}
    if set(binding_by_id) != set(selection_by_id):
        raise HarnessFailure("preflight", "case_binding_coverage", "case_id 集合不一致")
    if set(mask_manifests) != set(selection_by_id) or set(evidence_manifests) != set(
        selection_by_id
    ):
        raise HarnessFailure("preflight", "case_manifest_coverage", "case manifest key 集合不一致")

    case_bindings: list[CaseBinding] = []
    for case_id, frozen in binding_by_id.items():
        selected = selection_by_id[case_id]
        selected_candidate_ids = tuple(str(row["id"]) for row in selected["candidates"])
        if (
            frozen["prompt"] != selected["prompt"]
            or frozen["image_sha256"] != selected["image_sha256"]
            or tuple(frozen["candidate_ids"]) != selected_candidate_ids
        ):
            raise HarnessFailure("preflight", "case_semantic_binding", case_id)

        mask_binding = mask_manifests[case_id]
        evidence_binding = evidence_manifests[case_id]
        mask_payload = _verify_manifest(mask_binding)
        evidence_payload = _verify_manifest(evidence_binding)
        mask_candidate_ids = tuple(
            str(row["candidate_id"]) for row in mask_payload["masks"]
        )
        evidence_candidate_ids = {
            str(row["candidate_id"]) for row in evidence_payload["artifacts"]
        }
        if (
            mask_payload.get("case_id") != case_id
            or mask_payload.get("image_sha256") != selected["image_sha256"]
            or mask_candidate_ids != selected_candidate_ids
            or any(
                list(record["bbox"]) != list(candidate["bbox"])
                for record, candidate in zip(
                    mask_payload["masks"], selected["candidates"], strict=True
                )
            )
        ):
            raise HarnessFailure("preflight", "mask_case_binding", case_id)
        if (
            evidence_payload.get("case_id") != case_id
            or evidence_payload.get("source_image", {}).get("sha256")
            != selected["image_sha256"]
            or evidence_candidate_ids != set(selected_candidate_ids)
        ):
            raise HarnessFailure("preflight", "evidence_case_binding", case_id)
        case_bindings.append(
            CaseBinding(
                case_id=case_id,
                prompt=str(frozen["prompt"]),
                semantic_constraint=str(frozen["semantic_constraint"]),
                image_sha256=str(frozen["image_sha256"]),
                candidate_ids=selected_candidate_ids,
                mask_manifest=mask_binding,
                evidence_manifest=evidence_binding,
            )
        )

    scheduled_slots = tuple(expand_schedule(selection, schedule))
    scheduled_sequence_sha = _slot_sequence_sha256(scheduled_slots)
    return PreflightReceipt(
        builder_implementation_sha=BUILDER_IMPLEMENTATION_SHA,
        harness_review_sha=harness_review_sha,
        harness_review_lock_sha256=review_lock_sha256,
        contract_sha256=FROZEN_CONTRACT_SHA256,
        selection_sha256=FROZEN_SELECTION_SHA256,
        schedule_sha256=FROZEN_SCHEDULE_SHA256,
        execution_bindings_sha256=execution_bindings_sha,
        scheduled_slot_count=len(scheduled_slots),
        scheduled_slot_sequence_sha256=scheduled_sequence_sha,
        scheduled_slots=scheduled_slots,
        case_bindings=tuple(case_bindings),
    )


class ManifestEvidenceProvider:
    """按已核验 case manifest 加载证据，并在每次调用前复核字节 SHA。"""

    def __init__(self, preflight: PreflightReceipt):
        self.case_manifests = {
            binding.case_id: binding.evidence_manifest
            for binding in preflight.case_bindings
        }

    def __call__(self, slot: Slot) -> LoadedEvidence:
        try:
            binding = self.case_manifests[slot.case_id]
            payload = _verify_manifest(binding)
            records = {
                (str(row["candidate_id"]), str(row["arm"]), str(row["evidence_type"])): row
                for row in payload["artifacts"]
            }

            def load(evidence_type: str) -> tuple[Image.Image, str]:
                record = records[(str(slot.candidate["id"]), slot.arm, evidence_type)]
                path = Path(record["path"])
                if not path.is_absolute():
                    path = binding.path.parent / path
                with Image.open(path) as image:
                    loaded = image.convert("RGB").copy()
                return loaded, str(record["sha256"])

            isolated, isolated_sha = load("isolated")
            local, local_sha = load("local")
            fallback = None
            fallback_sha = None
            if slot.arm in {"A", "C"}:
                fallback, fallback_sha = load("full_scene")
            return LoadedEvidence(
                images=ArmEvidence((isolated, local), fallback),
                first_pass_sha256=(isolated_sha, local_sha),
                fallback_sha256=fallback_sha,
            )
        except HarnessFailure as error:
            raise HarnessFailure(
                "evidence", error.category, str(error), error.details
            ) from error
        except Exception as error:
            raise HarnessFailure("evidence", "evidence_integrity", str(error)) from error


class _MeteredCompletions:
    def __init__(self, completions):
        self._completions = completions
        self.latencies: list[float] = []
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0

    def create(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            response = self._completions.create(*args, **kwargs)
        finally:
            self.latencies.append(time.perf_counter() - started)
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
            self.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
            self.total_tokens += int(getattr(usage, "total_tokens", 0) or 0)
        return response


class _MeteredClient:
    def __init__(self, client):
        self.completions = _MeteredCompletions(client.chat.completions)
        self.chat = SimpleNamespace(completions=self.completions)


class ProductionBehaviorAdapter:
    """调用 Production behavior verifier；不复制或改写 prompt/validator/retry。"""

    def __init__(
        self,
        *,
        preflight: PreflightReceipt,
        config_loader: Callable[[], VlmConfig] = load_vlm_config,
        client_factory: Callable[[VlmConfig], object] = create_vlm_client,
        verifier: Callable[..., tuple[list[dict], dict]] = vlm.verify_candidate_constraints,
    ):
        self.case_bindings = {
            binding.case_id: binding for binding in preflight.case_bindings
        }
        self.config_loader = config_loader
        self.client_factory = client_factory
        self.verifier = verifier

    def verify(self, slot: Slot, images: tuple[Image.Image, ...]) -> VerificationOutcome:
        started = time.perf_counter()
        config = None
        metered = None
        try:
            config = self.config_loader()
            if (
                config.model != FROZEN_VLM_MODEL
                or config.base_url.rstrip("/") != FROZEN_VLM_BASE_URL.rstrip("/")
                or config.timeout != FROZEN_VLM_TIMEOUT
            ):
                raise HarnessFailure(
                    "preflight",
                    "frozen_vlm_config",
                    (
                        f"model={config.model}, base_url={config.base_url}, "
                        f"timeout={config.timeout}"
                    ),
                )
            metered = _MeteredClient(self.client_factory(config))
            binding = self.case_bindings[slot.case_id]
            if str(slot.candidate["id"]) not in binding.candidate_ids:
                raise HarnessFailure(
                    "preflight", "candidate_semantic_binding", slot.slot_id
                )
            constraints = [
                {"text": binding.semantic_constraint, "route": "behavior"}
            ]
            with patch.object(vlm, "_client", return_value=metered):
                checks, protocol = self.verifier(
                    {"id": slot.candidate["id"]},
                    constraints,
                    list(images),
                    "behavior",
                )
            check = checks[0]
            status = check["status"]
            if status not in VALID_STATUSES:
                raise HarnessFailure("validator", "invalid_status", str(status))
            return VerificationOutcome(
                status=status,
                evidence=check["evidence"],
                protocol=protocol,
                model=config.model,
                provider=(
                    "dashscope"
                    if config.base_url.rstrip("/") == DEFAULT_VLM_BASE_URL.rstrip("/")
                    else "openai_compatible"
                ),
                base_url=config.base_url,
                latency_seconds=time.perf_counter() - started,
                request_latency_seconds=tuple(metered.completions.latencies),
                prompt_tokens=metered.completions.prompt_tokens,
                completion_tokens=metered.completions.completion_tokens,
                total_tokens=metered.completions.total_tokens,
            )
        except HarnessFailure:
            raise
        except RuntimeError as error:
            message = str(error)
            if "contract_validation_error" in message:
                category = "validator"
            elif "json_decode_error" in message or "empty_response" in message:
                category = "protocol"
            elif "evidence payload normalization" in message:
                category = "evidence"
            else:
                category = "provider"
            raise HarnessFailure(
                category,
                category,
                message,
                self._failure_details(started, config, metered),
            ) from error
        except Exception as error:
            raise HarnessFailure(
                "provider",
                "provider",
                str(error),
                self._failure_details(started, config, metered),
            ) from error

    @staticmethod
    def _failure_details(started, config, metered) -> dict[str, object]:
        details: dict[str, object] = {
            "latency_seconds": time.perf_counter() - started,
        }
        evidence_payload = vlm._take_evidence_telemetry()
        if evidence_payload is not None:
            details["evidence_payload"] = evidence_payload
        if config is not None:
            details.update(
                {
                    "model": config.model,
                    "base_url": config.base_url,
                    "provider": (
                        "dashscope"
                        if config.base_url.rstrip("/")
                        == DEFAULT_VLM_BASE_URL.rstrip("/")
                        else "openai_compatible"
                    ),
                }
            )
        if metered is not None:
            details.update(
                {
                    "request_latency_seconds": list(metered.completions.latencies),
                    "attempts_observed": len(metered.completions.latencies),
                    "retry_count_observed": max(
                        0, len(metered.completions.latencies) - 1
                    ),
                    "recovered": False,
                    "prompt_tokens": metered.completions.prompt_tokens,
                    "completion_tokens": metered.completions.completion_tokens,
                    "total_tokens": metered.completions.total_tokens,
                }
            )
        return details


HarnessVerifier = Callable[[Slot, tuple[Image.Image, ...]], VerificationOutcome]


def run_harness_slots(
    *,
    preflight: PreflightReceipt,
    evidence_provider: Callable[[Slot], LoadedEvidence],
    verifier: HarnessVerifier,
    recorder: ResultRecorder,
) -> None:
    """执行冻结 slot；preflight receipt 自动固化为结果 sidecar。"""
    if preflight.builder_implementation_sha != BUILDER_IMPLEMENTATION_SHA:
        raise HarnessFailure(
            "preflight",
            "builder_implementation_sha",
            preflight.builder_implementation_sha,
        )
    slots = preflight.scheduled_slots
    if (
        len(slots) != preflight.scheduled_slot_count
        or _slot_sequence_sha256(slots)
        != preflight.scheduled_slot_sequence_sha256
    ):
        raise HarnessFailure("preflight", "scheduled_slot_sequence", "slot sequence 不一致")
    receipt_bytes = (
        json.dumps(
            preflight.as_record(), ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    ).encode("utf-8")
    receipt_path = recorder.path.with_suffix(".preflight.json")
    if receipt_path.exists():
        if receipt_path.read_bytes() != receipt_bytes:
            raise HarnessFailure(
                "preflight", "receipt_mismatch", str(receipt_path)
            )
    else:
        receipt_path.write_bytes(receipt_bytes)
    receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
    for slot in slots:
        if recorder.has_terminal_record(slot.slot_id):
            continue
        record: dict[str, object] = {
            "slot_id": slot.slot_id,
            "case_id": slot.case_id,
            "repetition": slot.repetition,
            "arm": slot.arm,
            "candidate_id": slot.candidate["id"],
            "preflight_receipt_sha256": receipt_sha,
        }
        try:
            loaded = evidence_provider(slot)
            record["first_pass_evidence_sha256"] = list(loaded.first_pass_sha256)
            first = verifier(slot, loaded.images.first_pass)
            record["first_pass"] = first.as_record()
            final = first
            if first.status == "uncertain" and slot.arm in {"A", "C"}:
                if loaded.images.fallback is None or loaded.fallback_sha256 is None:
                    raise HarnessFailure("evidence", "fallback_missing", slot.slot_id)
                record["fallback_evidence_sha256"] = loaded.fallback_sha256
                fallback = verifier(
                    slot,
                    (*loaded.images.first_pass, loaded.images.fallback),
                )
                record["fallback"] = fallback.as_record()
                record["fallback_classification"] = classify_fallback(
                    slot.candidate, fallback.status
                )
                final = fallback
            record.update({"final_status": final.status, "terminal": "success"})
        except HarnessFailure as error:
            record.update(
                {
                    "terminal": "failed",
                    "failure_stage": error.stage,
                    "failure_category": error.category,
                    "failure_message": str(error),
                    "failure_telemetry": error.details,
                }
            )
        except Exception as error:
            record.update(
                {
                    "terminal": "failed",
                    "failure_stage": "harness",
                    "failure_category": "unexpected",
                    "failure_message": str(error),
                }
            )
        recorder.append(record)
