import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from benchmark.r3_candidate_identity_v1 import execution_harness as harness
from benchmark.r3_candidate_identity_v1.evidence_builder import ArmEvidence
from benchmark.r3_candidate_identity_v1.execution_harness import (
    HarnessFailure,
    LoadedEvidence,
    ManifestBinding,
    ManifestEvidenceProvider,
    ProductionBehaviorAdapter,
    PreflightReceipt,
    VerificationOutcome,
    run_harness_slots,
    verify_execution_preflight,
)
from benchmark.r3_candidate_identity_v1.runner import ResultRecorder, Slot
from visual_agent.vlm_client import VlmConfig


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def _artifact_manifest(
    tmp_path: Path, name: str, image_sha: str, *, kind: str
) -> ManifestBinding:
    artifact = tmp_path / f"{name}.bin"
    artifact.write_bytes(b"frozen-bytes")
    manifest = tmp_path / f"{name}.json"
    records_key = "masks" if kind == "mask" else "artifacts"
    payload = {
        records_key: [
                {
                    "path": artifact.name,
                    "sha256": _sha(artifact),
                    "bytes": artifact.stat().st_size,
                }
            ],
    }
    if kind == "mask":
        payload["image_sha256"] = image_sha
    else:
        payload["source_image"] = {"sha256": image_sha}
    _write_json(manifest, payload)
    return ManifestBinding(manifest, _sha(manifest))


def test_preflight_locks_contract_builder_and_all_manifest_bytes(tmp_path, monkeypatch):
    contract = tmp_path / "contract.json"
    selection = tmp_path / "selection.json"
    schedule = tmp_path / "schedule.json"
    for path, payload in (
        (contract, {"contract": 1}),
        (selection, {"cases": [{"image_sha256": "image-sha"}]}),
        (schedule, {"schedule": 1}),
    ):
        _write_json(path, payload)
    monkeypatch.setattr(harness, "FROZEN_CONTRACT_SHA256", _sha(contract))
    monkeypatch.setattr(harness, "FROZEN_SELECTION_SHA256", _sha(selection))
    monkeypatch.setattr(harness, "FROZEN_SCHEDULE_SHA256", _sha(schedule))
    commands = []

    def git_runner(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    mask = _artifact_manifest(tmp_path, "mask", "image-sha", kind="mask")
    evidence = _artifact_manifest(
        tmp_path, "evidence", "image-sha", kind="evidence"
    )
    receipt = verify_execution_preflight(
        repo_root=tmp_path,
        contract_path=contract,
        selection_path=selection,
        schedule_path=schedule,
        mask_manifests=[mask],
        evidence_manifests=[evidence],
        git_runner=git_runner,
    )

    assert commands[0][0:4] == ["git", "merge-base", "--is-ancestor", harness.BUILDER_IMPLEMENTATION_SHA]
    assert commands[1][0:3] == ["git", "diff", "--quiet"]
    assert receipt.image_sha256 == ("image-sha",)
    assert receipt.implementation_sha == harness.BUILDER_IMPLEMENTATION_SHA

    (tmp_path / "mask.bin").write_bytes(b"changed")
    with pytest.raises(HarnessFailure) as error:
        verify_execution_preflight(
            repo_root=tmp_path,
            contract_path=contract,
            selection_path=selection,
            schedule_path=schedule,
            mask_manifests=[mask],
            evidence_manifests=[evidence],
            git_runner=git_runner,
        )
    assert (error.value.stage, error.value.category) == ("preflight", "artifact_sha")


def test_preflight_rejects_builder_implementation_drift(tmp_path, monkeypatch):
    paths = [tmp_path / name for name in ("contract", "selection", "schedule")]
    paths[0].write_bytes(b"x")
    _write_json(paths[1], {"cases": []})
    paths[2].write_bytes(b"x")
    monkeypatch.setattr(harness, "FROZEN_CONTRACT_SHA256", _sha(paths[0]))
    monkeypatch.setattr(harness, "FROZEN_SELECTION_SHA256", _sha(paths[1]))
    monkeypatch.setattr(harness, "FROZEN_SCHEDULE_SHA256", _sha(paths[2]))
    returns = iter([0, 1])

    with pytest.raises(HarnessFailure) as error:
        verify_execution_preflight(
            repo_root=tmp_path,
            contract_path=paths[0],
            selection_path=paths[1],
            schedule_path=paths[2],
            mask_manifests=[],
            evidence_manifests=[],
            git_runner=lambda *_args, **_kwargs: SimpleNamespace(
                returncode=next(returns)
            ),
        )
    assert error.value.category == "implementation_drift"


def test_preflight_rejects_manifest_image_set_mismatch(tmp_path, monkeypatch):
    contract, selection, schedule = [
        tmp_path / name for name in ("contract", "selection", "schedule")
    ]
    contract.write_bytes(b"contract")
    _write_json(selection, {"cases": [{"image_sha256": "expected-image"}]})
    schedule.write_bytes(b"schedule")
    monkeypatch.setattr(harness, "FROZEN_CONTRACT_SHA256", _sha(contract))
    monkeypatch.setattr(harness, "FROZEN_SELECTION_SHA256", _sha(selection))
    monkeypatch.setattr(harness, "FROZEN_SCHEDULE_SHA256", _sha(schedule))
    mask = _artifact_manifest(tmp_path, "mask", "wrong-image", kind="mask")
    evidence = _artifact_manifest(
        tmp_path, "evidence", "expected-image", kind="evidence"
    )

    with pytest.raises(HarnessFailure) as error:
        verify_execution_preflight(
            repo_root=tmp_path,
            contract_path=contract,
            selection_path=selection,
            schedule_path=schedule,
            mask_manifests=[mask],
            evidence_manifests=[evidence],
            git_runner=lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
        )
    assert error.value.category == "mask_manifest_coverage"


def test_manifest_evidence_provider_rechecks_sha_and_loads_frozen_arm(tmp_path):
    root = tmp_path / "case"
    records = []
    for evidence_type in ("isolated", "local", "full_scene"):
        path = root / f"{evidence_type}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (3, 2), (10, 20, 30)).save(path)
        records.append(
            {
                "candidate_id": "A",
                "arm": "C",
                "evidence_type": evidence_type,
                "path": path.name,
                "sha256": _sha(path),
                "bytes": path.stat().st_size,
            }
        )
    manifest = root / "manifest.json"
    _write_json(manifest, {"artifacts": records})
    provider = ManifestEvidenceProvider(
        {"case": ManifestBinding(manifest, _sha(manifest))}
    )
    slot = Slot("case", 1, "C", {"id": "A", "expected": "satisfied"})

    loaded = provider(slot)

    assert len(loaded.images.first_pass) == 2
    assert loaded.images.fallback is not None
    assert loaded.fallback_sha256 == records[2]["sha256"]

    (root / "local.png").write_bytes(b"corrupt")
    with pytest.raises(HarnessFailure) as error:
        provider(slot)
    assert (error.value.stage, error.value.category) == (
        "evidence",
        "artifact_sha",
    )


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=item))],
            usage=SimpleNamespace(
                prompt_tokens=11,
                completion_tokens=7,
                total_tokens=18,
            ),
        )


def _fake_client(responses):
    completions = FakeCompletions(responses)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def _valid_response(status="satisfied"):
    return json.dumps(
        {
            "candidate_id": "A",
            "checks": [
                {
                    "constraint": "正在钓鱼",
                    "status": status,
                    "evidence": "可见候选正在操作鱼竿",
                }
            ],
        },
        ensure_ascii=False,
    )


def _adapter(client):
    return ProductionBehaviorAdapter(
        prompts={"case": "正在钓鱼"},
        config_loader=lambda: VlmConfig(
            model="local-model",
            base_url="http://local.example/v1",
            api_key="dummy",
            timeout=120,
        ),
        client_factory=lambda _config: client,
    )


def test_adapter_reuses_production_prompt_validator_normalization_and_telemetry():
    client, completions = _fake_client(["not json", _valid_response()])
    adapter = _adapter(client)
    slot = Slot("case", 1, "C", {"id": "A", "expected": "satisfied"})
    images = (Image.new("RGB", (4, 3)), Image.new("RGB", (5, 4)))

    outcome = adapter.verify(slot, images)

    assert outcome.status == "satisfied"
    assert outcome.model == "local-model"
    assert outcome.provider == "openai_compatible"
    assert outcome.protocol["attempts"] == 2
    assert outcome.protocol["retry_count"] == 1
    assert outcome.protocol["recovered"] is True
    assert outcome.protocol["evidence_payload"]["evidence_count"] == 2
    assert outcome.prompt_tokens == 22
    assert outcome.completion_tokens == 14
    assert outcome.total_tokens == 36
    assert len(outcome.request_latency_seconds) == 2
    request = completions.requests[0]
    assert request["temperature"] == 0
    assert request["response_format"] == {"type": "json_object"}
    assert "固定 35% 局部图" in request["messages"][0]["content"]
    images_in_message = [
        row
        for row in request["messages"][1]["content"]
        if row["type"] == "image_url"
    ]
    assert len(images_in_message) == 2
    assert all(
        row["image_url"]["url"].startswith("data:image/png;base64,")
        for row in images_in_message
    )


@pytest.mark.parametrize(
    ("responses", "stage"),
    [
        ([RuntimeError("network down")], "provider"),
        (["not json", "still not json"], "protocol"),
        ([json.dumps({"wrong": True}), json.dumps({"wrong": True})], "validator"),
    ],
)
def test_adapter_classifies_terminal_failure_stage_and_keeps_telemetry(
    responses, stage
):
    client, _completions = _fake_client(responses)
    adapter = _adapter(client)
    slot = Slot("case", 1, "A", {"id": "A", "expected": "satisfied"})

    with pytest.raises(HarnessFailure) as error:
        adapter.verify(slot, (Image.new("RGB", (2, 2)),))

    assert error.value.stage == stage
    assert error.value.details["model"] == "local-model"
    assert error.value.details["attempts_observed"] >= 1
    assert "evidence_payload" in error.value.details


def _outcome(status):
    return VerificationOutcome(
        status=status,
        evidence="stub",
        protocol={"attempts": 1, "retry_count": 0, "recovered": False},
        model="stub",
        provider="stub",
        base_url="stub",
        latency_seconds=0.1,
        request_latency_seconds=(0.1,),
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
    )


def _receipt():
    return PreflightReceipt(
        implementation_sha=harness.BUILDER_IMPLEMENTATION_SHA,
        contract_sha256="contract",
        selection_sha256="selection",
        schedule_sha256="schedule",
        mask_manifest_sha256=("mask",),
        evidence_manifest_sha256=("evidence",),
        image_sha256=("image",),
    )


def test_harness_uses_three_image_production_fallback_and_records_sha(tmp_path):
    image = Image.new("RGB", (1, 1))
    loaded = LoadedEvidence(
        ArmEvidence((image, image), image),
        ("isolated-sha", "local-sha"),
        "full-sha",
    )
    slots = [
        Slot("case", 1, "C", {"id": "A", "expected": "satisfied"}),
        Slot("case", 1, "B", {"id": "B", "expected": "uncertain"}),
    ]
    calls = []

    def verifier(slot, images):
        calls.append((slot.arm, len(images)))
        if slot.arm == "C" and len(images) == 2:
            return _outcome("uncertain")
        if slot.arm == "C":
            return _outcome("satisfied")
        return _outcome("uncertain")

    recorder = ResultRecorder(tmp_path / "results.jsonl")
    run_harness_slots(
        slots,
        preflight=_receipt(),
        evidence_provider=lambda _slot: loaded,
        verifier=verifier,
        recorder=recorder,
    )
    rows = [json.loads(line) for line in recorder.path.read_text(encoding="utf-8").splitlines()]

    assert calls == [("C", 2), ("C", 3), ("B", 2)]
    assert rows[0]["first_pass_evidence_sha256"] == ["isolated-sha", "local-sha"]
    assert rows[0]["fallback_evidence_sha256"] == "full-sha"
    assert rows[0]["fallback_classification"] == "correctly_resolved"
    assert "fallback" not in rows[1]
    receipt_path = recorder.path.with_suffix(".preflight.json")
    assert receipt_path.is_file()
    assert rows[0]["preflight_receipt_sha256"] == _sha(receipt_path)


def test_harness_records_explicit_evidence_failure_stage_and_continues(tmp_path):
    image = Image.new("RGB", (1, 1))
    loaded = LoadedEvidence(ArmEvidence((image, image), None), ("a", "b"), None)
    slots = [
        Slot("case", 1, "B", {"id": "bad", "expected": "not_satisfied"}),
        Slot("case", 1, "B", {"id": "good", "expected": "not_satisfied"}),
    ]

    def provider(slot):
        if slot.candidate["id"] == "bad":
            raise HarnessFailure("evidence", "evidence_integrity", "bad sha")
        return loaded

    recorder = ResultRecorder(tmp_path / "results.jsonl")
    run_harness_slots(
        slots,
        preflight=_receipt(),
        evidence_provider=provider,
        verifier=lambda _slot, _images: _outcome("not_satisfied"),
        recorder=recorder,
    )
    rows = [json.loads(line) for line in recorder.path.read_text(encoding="utf-8").splitlines()]

    assert rows[0]["terminal"] == "failed"
    assert rows[0]["failure_stage"] == "evidence"
    assert rows[0]["failure_category"] == "evidence_integrity"
    assert rows[1]["terminal"] == "success"


@pytest.mark.parametrize("stage", ["provider", "protocol", "validator"])
def test_harness_writes_model_failure_stage_to_terminal_record(tmp_path, stage):
    image = Image.new("RGB", (1, 1))
    loaded = LoadedEvidence(ArmEvidence((image, image), None), ("a", "b"), None)
    slot = Slot("case", 1, "B", {"id": stage, "expected": "not_satisfied"})
    recorder = ResultRecorder(tmp_path / f"{stage}.jsonl")

    run_harness_slots(
        [slot],
        preflight=_receipt(),
        evidence_provider=lambda _slot: loaded,
        verifier=lambda _slot, _images: (_ for _ in ()).throw(
            HarnessFailure(
                stage,
                stage,
                "stub failure",
                {"attempts_observed": 2, "total_tokens": 0},
            )
        ),
        recorder=recorder,
    )
    row = json.loads(recorder.path.read_text(encoding="utf-8"))

    assert row["terminal"] == "failed"
    assert row["failure_stage"] == stage
    assert row["failure_category"] == stage
    assert row["failure_telemetry"]["attempts_observed"] == 2
