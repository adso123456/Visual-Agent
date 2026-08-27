import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from benchmark.r3_candidate_identity_v1 import execution_harness as harness
from benchmark.r3_candidate_identity_v1.evidence_builder import ArmEvidence
from benchmark.r3_candidate_identity_v1.execution_harness import (
    CaseBinding,
    HarnessFailure,
    LoadedEvidence,
    ManifestBinding,
    ManifestEvidenceProvider,
    PreflightReceipt,
    ProductionBehaviorAdapter,
    VerificationOutcome,
    run_harness_slots,
    verify_execution_preflight,
)
from benchmark.r3_candidate_identity_v1.runner import ResultRecorder, Slot
from visual_agent.vlm_client import VlmConfig


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_artifact(path: Path, content: bytes = b"frozen") -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {"path": path.name, "sha256": _sha(path), "bytes": path.stat().st_size}


def _manifest_pair(root: Path, case: dict) -> tuple[ManifestBinding, ManifestBinding]:
    case_id = case["case_id"]
    candidate = case["candidates"][0]
    mask_root = root / "mask" / case_id
    mask_record = _write_artifact(mask_root / "candidate_A.bin")
    mask_record.update({"candidate_id": "A", "bbox": candidate["bbox"]})
    mask_path = mask_root / "manifest.json"
    _write_json(
        mask_path,
        {
            "case_id": case_id,
            "image_sha256": case["image_sha256"],
            "masks": [mask_record],
        },
    )

    evidence_root = root / "evidence" / case_id
    artifacts = []
    for arm, evidence_types in (
        ("A", ("isolated", "local", "full_scene")),
        ("B", ("isolated", "local")),
        ("C", ("isolated", "local", "full_scene")),
    ):
        for evidence_type in evidence_types:
            path = evidence_root / f"{arm}_{evidence_type}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (3, 2), (10, 20, 30)).save(path)
            artifacts.append(
                {
                    "candidate_id": "A",
                    "arm": arm,
                    "evidence_type": evidence_type,
                    "path": path.name,
                    "sha256": _sha(path),
                    "bytes": path.stat().st_size,
                }
            )
    evidence_path = evidence_root / "manifest.json"
    _write_json(
        evidence_path,
        {
            "case_id": case_id,
            "source_image": {"sha256": case["image_sha256"]},
            "artifacts": artifacts,
        },
    )
    return (
        ManifestBinding(mask_path, _sha(mask_path)),
        ManifestBinding(evidence_path, _sha(evidence_path)),
    )


def _preflight_fixture(tmp_path, monkeypatch, *, git_runner=None):
    repo = tmp_path / "repo"
    repo.mkdir()
    contract = tmp_path / "contract.json"
    selection = tmp_path / "selection.json"
    schedule = tmp_path / "schedule.json"
    bindings = repo / "benchmark" / "r3_candidate_identity_v1" / "bindings.json"
    case = {
        "case_id": "case",
        "prompt": "找到正在钓鱼的人",
        "image_sha256": "image-sha",
        "candidates": [
            {"id": "A", "bbox": [1, 2, 8, 9], "expected": "satisfied"}
        ],
    }
    _write_json(contract, {"contract": 1})
    _write_json(selection, {"cases": [case]})
    _write_json(
        schedule,
        {
            "failed_execution_replacement": False,
            "challenge_schedule": [
                {"case_id": "case", "repetition": 1, "arm_order": ["A", "B", "C"]}
            ],
            "F1_schedule": [],
            "totals": {"scheduled_first_pass_candidate_calls": 3},
        },
    )
    _write_json(
        bindings,
        {
            "cases": [
                {
                    "case_id": "case",
                    "prompt": case["prompt"],
                    "semantic_constraint": "正在钓鱼",
                    "image_sha256": case["image_sha256"],
                    "candidate_ids": ["A"],
                }
            ]
        },
    )
    mask, evidence = _manifest_pair(tmp_path, case)
    locked_file = repo / "benchmark" / "harness.py"
    locked_file.parent.mkdir(parents=True, exist_ok=True)
    locked_file.write_bytes(b"reviewed harness")
    lock = tmp_path / "review_lock.json"
    _write_json(
        lock,
        {
            "builder_implementation_sha": harness.BUILDER_IMPLEMENTATION_SHA,
            "harness_review_sha": "reviewed-harness-sha",
            "production_base_sha": harness.PRODUCTION_BASE_SHA,
            "execution_bindings_sha256": _sha(bindings),
            "files": [
                {
                    "path": "benchmark/harness.py",
                    "sha256": _sha(locked_file),
                    "bytes": locked_file.stat().st_size,
                }
            ],
        },
    )
    monkeypatch.setattr(harness, "FROZEN_CONTRACT_SHA256", _sha(contract))
    monkeypatch.setattr(harness, "FROZEN_SELECTION_SHA256", _sha(selection))
    monkeypatch.setattr(harness, "FROZEN_SCHEDULE_SHA256", _sha(schedule))
    if git_runner is None:
        git_runner = lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="", stderr=""
        )
    receipt = verify_execution_preflight(
        repo_root=repo,
        review_lock_path=lock,
        review_lock_sha256=_sha(lock),
        contract_path=contract,
        selection_path=selection,
        schedule_path=schedule,
        execution_bindings_path=bindings,
        mask_manifests={"case": mask},
        evidence_manifests={"case": evidence},
        git_runner=git_runner,
    )
    return receipt, lock, mask, evidence


def test_preflight_locks_harness_builder_production_bindings_and_schedule(
    tmp_path, monkeypatch
):
    commands = []

    def git_runner(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    receipt, lock, _mask, _evidence = _preflight_fixture(
        tmp_path, monkeypatch, git_runner=git_runner
    )
    assert receipt.builder_implementation_sha == harness.BUILDER_IMPLEMENTATION_SHA
    assert receipt.harness_review_sha == "reviewed-harness-sha"
    assert receipt.harness_review_lock_sha256 == _sha(lock)
    assert receipt.scheduled_slot_count == 3
    assert [slot.slot_id for slot in receipt.scheduled_slots] == [
        "case|r1|A|A",
        "case|r1|B|A",
        "case|r1|C|A",
    ]
    assert receipt.case_bindings[0].semantic_constraint == "正在钓鱼"
    assert any(command[:3] == ["git", "status", "--porcelain"] for command in commands)


@pytest.mark.parametrize(
    ("failure_command", "expected_category"),
    [
        ("reviewed-harness-sha", "harness_review_sha"),
        ("visual_agent", "production_verifier_drift"),
    ],
)
def test_preflight_rejects_commit_or_production_drift(
    tmp_path, monkeypatch, failure_command, expected_category
):
    def git_runner(command, **_kwargs):
        return SimpleNamespace(
            returncode=1 if failure_command in command else 0,
            stdout="",
            stderr="",
        )

    with pytest.raises(HarnessFailure) as error:
        _preflight_fixture(tmp_path, monkeypatch, git_runner=git_runner)
    assert error.value.category == expected_category


def test_preflight_rejects_uncommitted_benchmark_or_visual_agent_changes(
    tmp_path, monkeypatch
):
    def git_runner(command, **_kwargs):
        dirty = command[:3] == ["git", "status", "--porcelain"]
        return SimpleNamespace(
            returncode=0,
            stdout=" M benchmark/r3_candidate_identity_v1/execution_harness.py\n"
            if dirty
            else "",
            stderr="",
        )

    with pytest.raises(HarnessFailure) as error:
        _preflight_fixture(tmp_path, monkeypatch, git_runner=git_runner)
    assert error.value.category == "working_tree_dirty"


def test_preflight_rejects_case_manifest_swap_even_when_image_set_matches(
    tmp_path, monkeypatch
):
    _receipt, lock, mask, evidence = _preflight_fixture(tmp_path, monkeypatch)
    payload = json.loads(evidence.path.read_text(encoding="utf-8"))
    payload["case_id"] = "other-case"
    _write_json(evidence.path, payload)
    changed_evidence = ManifestBinding(evidence.path, _sha(evidence.path))
    repo = tmp_path / "repo"

    with pytest.raises(HarnessFailure) as error:
        verify_execution_preflight(
            repo_root=repo,
            review_lock_path=lock,
            review_lock_sha256=_sha(lock),
            contract_path=tmp_path / "contract.json",
            selection_path=tmp_path / "selection.json",
            schedule_path=tmp_path / "schedule.json",
            execution_bindings_path=repo
            / "benchmark"
            / "r3_candidate_identity_v1"
            / "bindings.json",
            mask_manifests={"case": mask},
            evidence_manifests={"case": changed_evidence},
            git_runner=lambda *_args, **_kwargs: SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
        )
    assert error.value.category == "evidence_case_binding"


def test_manifest_evidence_provider_uses_receipt_binding_and_rechecks_sha(
    tmp_path, monkeypatch
):
    receipt, _lock, _mask, evidence = _preflight_fixture(tmp_path, monkeypatch)
    provider = ManifestEvidenceProvider(receipt)
    loaded = provider(receipt.scheduled_slots[2])
    assert len(loaded.images.first_pass) == 2
    assert loaded.images.fallback is not None

    payload = json.loads(evidence.path.read_text(encoding="utf-8"))
    corrupt = evidence.path.parent / payload["artifacts"][0]["path"]
    corrupt.write_bytes(b"corrupt")
    with pytest.raises(HarnessFailure) as error:
        provider(receipt.scheduled_slots[2])
    assert (error.value.stage, error.value.category) == ("evidence", "artifact_sha")


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
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
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


def _manual_receipt(slots=None):
    if slots is None:
        slots = (Slot("case", 1, "C", {"id": "A", "expected": "satisfied"}),)
    binding = CaseBinding(
        case_id="case",
        prompt="找到正在钓鱼的人",
        semantic_constraint="正在钓鱼",
        image_sha256="image",
        candidate_ids=("A",),
        mask_manifest=ManifestBinding(Path("mask.json"), "mask"),
        evidence_manifest=ManifestBinding(Path("evidence.json"), "evidence"),
    )
    return PreflightReceipt(
        builder_implementation_sha=harness.BUILDER_IMPLEMENTATION_SHA,
        harness_review_sha="review",
        harness_review_lock_sha256="lock",
        contract_sha256="contract",
        selection_sha256="selection",
        schedule_sha256="schedule",
        execution_bindings_sha256="bindings",
        scheduled_slot_count=len(slots),
        scheduled_slot_sequence_sha256=harness._slot_sequence_sha256(slots),
        scheduled_slots=tuple(slots),
        case_bindings=(binding,),
    )


def _adapter(client, receipt=None, config=None, calls=None):
    receipt = receipt or _manual_receipt()
    config = config or VlmConfig(
        model=harness.FROZEN_VLM_MODEL,
        base_url=harness.FROZEN_VLM_BASE_URL,
        api_key="dummy",
        timeout=harness.FROZEN_VLM_TIMEOUT,
    )

    def client_factory(_config):
        if calls is not None:
            calls.append("client")
        return client

    return ProductionBehaviorAdapter(
        preflight=receipt,
        config_loader=lambda: config,
        client_factory=client_factory,
    )


@pytest.mark.parametrize(
    "bad_config",
    [
        VlmConfig("wrong-model", harness.FROZEN_VLM_BASE_URL, "x", 120),
        VlmConfig(harness.FROZEN_VLM_MODEL, "https://dashscope.example/v1", "x", 120),
        VlmConfig(harness.FROZEN_VLM_MODEL, harness.FROZEN_VLM_BASE_URL, "x", 60),
    ],
)
def test_adapter_rejects_non_frozen_runtime_config_before_client_creation(bad_config):
    client, _ = _fake_client([_valid_response()])
    calls = []
    receipt = _manual_receipt()
    adapter = _adapter(client, receipt, bad_config, calls)

    with pytest.raises(HarnessFailure) as error:
        adapter.verify(
            receipt.scheduled_slots[0],
            (Image.new("RGB", (2, 2)), Image.new("RGB", (2, 2))),
        )
    assert (error.value.stage, error.value.category) == (
        "preflight",
        "frozen_vlm_config",
    )
    assert calls == []


def test_adapter_uses_frozen_constraint_and_production_contract_with_telemetry():
    client, completions = _fake_client(["not json", _valid_response()])
    receipt = _manual_receipt()
    adapter = _adapter(client, receipt)
    outcome = adapter.verify(
        receipt.scheduled_slots[0],
        (Image.new("RGB", (4, 3)), Image.new("RGB", (5, 4))),
    )

    assert outcome.status == "satisfied"
    assert outcome.model == harness.FROZEN_VLM_MODEL
    assert outcome.protocol["attempts"] == 2
    assert outcome.protocol["evidence_payload"]["evidence_count"] == 2
    assert outcome.total_tokens == 36
    request = completions.requests[0]
    assert request["temperature"] == 0
    assert request["response_format"] == {"type": "json_object"}
    assert 'constraints：["正在钓鱼"]' in request["messages"][1]["content"][-1]["text"]


@pytest.mark.parametrize(
    ("responses", "stage"),
    [
        ([RuntimeError("network down")], "provider"),
        (["not json", "still not json"], "protocol"),
        ([json.dumps({"wrong": True}), json.dumps({"wrong": True})], "validator"),
    ],
)
def test_adapter_classifies_failure_and_keeps_telemetry(responses, stage):
    client, _ = _fake_client(responses)
    receipt = _manual_receipt()
    adapter = _adapter(client, receipt)
    with pytest.raises(HarnessFailure) as error:
        adapter.verify(receipt.scheduled_slots[0], (Image.new("RGB", (2, 2)),))
    assert error.value.stage == stage
    assert error.value.details["model"] == harness.FROZEN_VLM_MODEL
    assert error.value.details["attempts_observed"] >= 1


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


def test_harness_executes_only_receipt_schedule_and_uses_three_image_fallback(tmp_path):
    slots = (
        Slot("case", 1, "C", {"id": "A", "expected": "satisfied"}),
        Slot("case", 1, "B", {"id": "A", "expected": "satisfied"}),
    )
    receipt = _manual_receipt(slots)
    image = Image.new("RGB", (1, 1))
    loaded = LoadedEvidence(ArmEvidence((image, image), image), ("i", "l"), "f")
    calls = []

    def verifier(slot, images):
        calls.append((slot.slot_id, len(images)))
        if slot.arm == "C" and len(images) == 2:
            return _outcome("uncertain")
        return _outcome("satisfied")

    recorder = ResultRecorder(tmp_path / "results.jsonl")
    run_harness_slots(
        preflight=receipt,
        evidence_provider=lambda _slot: loaded,
        verifier=verifier,
        recorder=recorder,
    )
    rows = [json.loads(line) for line in recorder.path.read_text(encoding="utf-8").splitlines()]
    assert calls == [
        ("case|r1|C|A", 2),
        ("case|r1|C|A", 3),
        ("case|r1|B|A", 2),
    ]
    assert rows[0]["fallback_classification"] == "correctly_resolved"
    assert rows[0]["preflight_receipt_sha256"] == _sha(
        recorder.path.with_suffix(".preflight.json")
    )


def test_harness_rejects_tampered_slot_sequence_before_verifier(tmp_path):
    receipt = _manual_receipt()
    tampered = replace(receipt, scheduled_slot_sequence_sha256="0" * 64)
    calls = []
    with pytest.raises(HarnessFailure) as error:
        run_harness_slots(
            preflight=tampered,
            evidence_provider=lambda _slot: calls.append("evidence"),
            verifier=lambda _slot, _images: calls.append("verifier"),
            recorder=ResultRecorder(tmp_path / "results.jsonl"),
        )
    assert error.value.category == "scheduled_slot_sequence"
    assert calls == []
