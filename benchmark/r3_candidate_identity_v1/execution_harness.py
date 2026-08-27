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
from .runner import ResultRecorder, Slot, VALID_STATUSES, classify_fallback


BUILDER_IMPLEMENTATION_SHA = "0b32695dcd46d13cf22987f5347b2b212e7132c1"
FROZEN_CONTRACT_SHA256 = "7072d0a6acdbe0beeb9db6f048a35d5d2dc28488696286183887f6c84ef5dd73"
FROZEN_SELECTION_SHA256 = "37fb7fcb97e5a324a4d76d81abe805e947e220420c97102eb6d690cc64c44563"
FROZEN_SCHEDULE_SHA256 = "e531bc803758a0b4827787d619cbd3b4a62c71a0c4647f78cd6d6ada3d08ca84"
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
class PreflightReceipt:
    implementation_sha: str
    contract_sha256: str
    selection_sha256: str
    schedule_sha256: str
    mask_manifest_sha256: tuple[str, ...]
    evidence_manifest_sha256: tuple[str, ...]
    image_sha256: tuple[str, ...]

    def as_record(self) -> dict[str, object]:
        return {
            "implementation_sha": self.implementation_sha,
            "contract_sha256": self.contract_sha256,
            "selection_sha256": self.selection_sha256,
            "schedule_sha256": self.schedule_sha256,
            "mask_manifest_sha256": list(self.mask_manifest_sha256),
            "evidence_manifest_sha256": list(self.evidence_manifest_sha256),
            "image_sha256": list(self.image_sha256),
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


def verify_execution_preflight(
    *,
    repo_root: Path,
    contract_path: Path,
    selection_path: Path,
    schedule_path: Path,
    mask_manifests: list[ManifestBinding],
    evidence_manifests: list[ManifestBinding],
    git_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> PreflightReceipt:
    """在任何模型调用前核验冻结合同、builder commit 及全部生成资产。"""
    expected_files = (
        (contract_path, FROZEN_CONTRACT_SHA256),
        (selection_path, FROZEN_SELECTION_SHA256),
        (schedule_path, FROZEN_SCHEDULE_SHA256),
    )
    for path, expected in expected_files:
        if not path.is_file() or _sha256(path) != expected:
            raise HarnessFailure("preflight", "frozen_contract_sha", str(path))
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    expected_image_shas = {
        str(case["image_sha256"]) for case in selection["cases"]
    }

    ancestor = git_runner(
        ["git", "merge-base", "--is-ancestor", BUILDER_IMPLEMENTATION_SHA, "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if ancestor.returncode != 0:
        raise HarnessFailure("preflight", "implementation_sha", BUILDER_IMPLEMENTATION_SHA)
    unchanged = git_runner(
        ["git", "diff", "--quiet", BUILDER_IMPLEMENTATION_SHA, "HEAD", "--", *BUILDER_FILES],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if unchanged.returncode != 0:
        raise HarnessFailure("preflight", "implementation_drift", BUILDER_IMPLEMENTATION_SHA)

    mask_payloads = [_verify_manifest(binding) for binding in mask_manifests]
    evidence_payloads = [
        _verify_manifest(binding) for binding in evidence_manifests
    ]
    mask_image_shas = {str(payload.get("image_sha256")) for payload in mask_payloads}
    evidence_image_shas = {
        str(payload.get("source_image", {}).get("sha256"))
        for payload in evidence_payloads
    }
    if mask_image_shas != expected_image_shas:
        raise HarnessFailure("preflight", "mask_manifest_coverage", "mask image SHA 集合不完整")
    if evidence_image_shas != expected_image_shas:
        raise HarnessFailure(
            "preflight",
            "evidence_manifest_coverage",
            "evidence image SHA 集合不完整",
        )
    return PreflightReceipt(
        implementation_sha=BUILDER_IMPLEMENTATION_SHA,
        contract_sha256=FROZEN_CONTRACT_SHA256,
        selection_sha256=FROZEN_SELECTION_SHA256,
        schedule_sha256=FROZEN_SCHEDULE_SHA256,
        mask_manifest_sha256=tuple(sorted(binding.sha256 for binding in mask_manifests)),
        evidence_manifest_sha256=tuple(
            sorted(binding.sha256 for binding in evidence_manifests)
        ),
        image_sha256=tuple(sorted(expected_image_shas)),
    )


class ManifestEvidenceProvider:
    """按已核验 case manifest 加载证据，并在每次调用前复核字节 SHA。"""

    def __init__(self, case_manifests: dict[str, ManifestBinding]):
        self.case_manifests = case_manifests

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
        prompts: dict[str, str],
        config_loader: Callable[[], VlmConfig] = load_vlm_config,
        client_factory: Callable[[VlmConfig], object] = create_vlm_client,
        verifier: Callable[..., tuple[list[dict], dict]] = vlm.verify_candidate_constraints,
    ):
        self.prompts = prompts
        self.config_loader = config_loader
        self.client_factory = client_factory
        self.verifier = verifier

    def verify(self, slot: Slot, images: tuple[Image.Image, ...]) -> VerificationOutcome:
        started = time.perf_counter()
        config = None
        metered = None
        try:
            config = self.config_loader()
            metered = _MeteredClient(self.client_factory(config))
            constraints = [
                {"text": self.prompts[slot.case_id], "route": "behavior"}
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
    slots: list[Slot],
    *,
    preflight: PreflightReceipt,
    evidence_provider: Callable[[Slot], LoadedEvidence],
    verifier: HarnessVerifier,
    recorder: ResultRecorder,
) -> None:
    """执行冻结 slot；preflight receipt 自动固化为结果 sidecar。"""
    if preflight.implementation_sha != BUILDER_IMPLEMENTATION_SHA:
        raise HarnessFailure(
            "preflight", "implementation_sha", preflight.implementation_sha
        )
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
