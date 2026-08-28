import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

from PIL import Image


OUTPUT = Path(__file__).resolve().parent
EVIDENCE_REPO = Path(r"E:\3\Visual Agent\_evidence_worktree")
BENCHMARK_REPO = Path(r"E:\3\Visual Agent\_r3_identity_benchmark_v1")
STAGE = EVIDENCE_REPO / "evidence/final_acceptance/GENERAL_RGB_BEHAVIOR_LONG_RANGE_CONTEXT_REMEDIATION_V1"
SOURCE = EVIDENCE_REPO / "evidence/final_acceptance/GENERAL_RGB_R3_CANDIDATE_IDENTITY_REMEDIATION_V1/execution"
EXPECTED_EVIDENCE_HEAD = "16d48bbe74b9d297ac66748d7bf39a75cfea42e9"
EXPECTED_BENCHMARK_HEAD = "22b22570c5f9ac6bd5249dae8f70782f500fb810"
EXPECTED_RESULTS_SHA = "70ffbd79bd562dfe00cff10191c60a89e58021f7fd067b4fdce33ec3dd00715e"
EXPECTED_SLOT_SEQUENCE_SHA = "2eb24f569fecd157d338ee83b830b69ddc0aff234d8655b5208a389bcb03785c"

sys.path.insert(0, str(BENCHMARK_REPO))

from benchmark.r3_candidate_identity_v1.execution_harness import (  # noqa: E402
    FROZEN_VLM_BASE_URL,
    FROZEN_VLM_MODEL,
    FROZEN_VLM_TIMEOUT,
    HarnessFailure,
    _MeteredClient,
)
from visual_agent import vlm  # noqa: E402
from visual_agent.vlm_client import (  # noqa: E402
    DEFAULT_VLM_BASE_URL,
    create_vlm_client,
    load_vlm_config,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, encoding="utf-8"
    ).strip()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def preflight():
    if git(EVIDENCE_REPO, "rev-parse", "HEAD") != EXPECTED_EVIDENCE_HEAD:
        raise RuntimeError("evidence_head_mismatch")
    if git(EVIDENCE_REPO, "status", "--porcelain"):
        raise RuntimeError("evidence_worktree_dirty")
    if git(BENCHMARK_REPO, "rev-parse", "HEAD") != EXPECTED_BENCHMARK_HEAD:
        raise RuntimeError("benchmark_head_mismatch")
    if git(BENCHMARK_REPO, "status", "--porcelain"):
        raise RuntimeError("benchmark_worktree_dirty")

    manifest = load_json(STAGE / "manifest.json")
    for item in manifest["files"]:
        path = STAGE / item["path"]
        if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise RuntimeError(f"contract_manifest_mismatch:{item['path']}")

    results_path = SOURCE / "results.jsonl"
    if sha256(results_path) != EXPECTED_RESULTS_SHA:
        raise RuntimeError("source_results_sha_mismatch")
    slots_payload = load_json(STAGE / "frozen_long_range_slots.json")
    slots = slots_payload["slots"]
    sequence = "".join(f"{slot['slot_id']}\n" for slot in slots).encode("utf-8")
    if len(slots) != 8 or hashlib.sha256(sequence).hexdigest() != EXPECTED_SLOT_SEQUENCE_SHA:
        raise RuntimeError("slot_sequence_mismatch")

    source_rows = {}
    for raw_line in results_path.read_bytes().splitlines():
        row = json.loads(raw_line.decode("utf-8"))
        source_rows[row["slot_id"]] = (row, hashlib.sha256(raw_line).hexdigest())

    used_evidence = {}
    for slot in slots:
        row, row_sha = source_rows[slot["source_slot_id"]]
        if (
            row_sha != slot["source_record_sha256"]
            or row["case_id"] != slot["case_id"]
            or row["candidate_id"] != slot["candidate_id"]
            or row["first_pass"]["status"] != "not_satisfied"
            or list(row["first_pass_evidence_sha256"]) != slot["evidence_sha256"][:2]
        ):
            raise RuntimeError(f"source_record_binding:{slot['slot_id']}")
        paths = (
            SOURCE / "evidence" / slot["image_sha256"] / slot["candidate_id"] / "C" / "isolated.png",
            SOURCE / "evidence" / slot["image_sha256"] / slot["candidate_id"] / "C" / "local.png",
            SOURCE / "evidence" / slot["image_sha256"] / slot["candidate_id"] / "C" / "fallback_full_scene.png",
        )
        actual = [sha256(path) for path in paths]
        if actual != slot["evidence_sha256"]:
            raise RuntimeError(f"evidence_sha_binding:{slot['slot_id']}")
        used_evidence[slot["slot_id"]] = paths

    inherited = {
        ("challenge_001", "A"): "uncertain",
        ("challenge_001", "B"): "satisfied",
        ("challenge_003", "A"): "uncertain",
        ("challenge_004", "B"): "uncertain",
    }
    for (case_id, candidate_id), expected in inherited.items():
        selected = [
            row
            for row, _ in source_rows.values()
            if row["case_id"] == case_id
            and row["candidate_id"] == candidate_id
            and row["arm"] == "B"
        ]
        if len(selected) != 5 or any(row["final_status"] != expected for row in selected):
            raise RuntimeError(f"inherited_control:{case_id}:{candidate_id}")

    config = load_vlm_config()
    if (
        config.model != FROZEN_VLM_MODEL
        or config.base_url.rstrip("/") != FROZEN_VLM_BASE_URL.rstrip("/")
        or config.timeout != FROZEN_VLM_TIMEOUT
    ):
        raise RuntimeError("frozen_vlm_config")
    receipt = {
        "schema_version": "LONG_RANGE_8_PREFLIGHT_V1",
        "evidence_head": EXPECTED_EVIDENCE_HEAD,
        "benchmark_head": EXPECTED_BENCHMARK_HEAD,
        "contract_sha256": sha256(STAGE / "narrow_mechanism_contract.json"),
        "slots_sha256": sha256(STAGE / "frozen_long_range_slots.json"),
        "source_results_sha256": EXPECTED_RESULTS_SHA,
        "slot_sequence_sha256": EXPECTED_SLOT_SEQUENCE_SHA,
        "scheduled_logical_calls": 8,
        "inherited_controls_verified": 20,
        "model": config.model,
        "base_url": config.base_url,
        "timeout_seconds": config.timeout,
    }
    return slots, used_evidence, config, receipt


def verify(slot, paths, config):
    started = time.perf_counter()
    metered = _MeteredClient(create_vlm_client(config))
    try:
        images = []
        for path in paths:
            with Image.open(path) as image:
                images.append(image.convert("RGB").copy())
        constraints = [{"text": "正在钓鱼", "route": "behavior"}]
        with patch.object(vlm, "_client", return_value=metered):
            checks, protocol = vlm.verify_candidate_constraints(
                {"id": slot["candidate_id"]}, constraints, images, "behavior"
            )
        check = checks[0]
        if check["status"] not in {"satisfied", "not_satisfied", "uncertain"}:
            raise HarnessFailure("validator", "invalid_status", check["status"])
        return {
            "terminal": "success",
            "status": check["status"],
            "evidence": check["evidence"],
            "protocol": protocol,
            "model": config.model,
            "base_url": config.base_url,
            "provider": "dashscope" if config.base_url.rstrip("/") == DEFAULT_VLM_BASE_URL.rstrip("/") else "openai_compatible",
            "latency_seconds": time.perf_counter() - started,
            "request_latency_seconds": metered.completions.latencies,
            "prompt_tokens": metered.completions.prompt_tokens,
            "completion_tokens": metered.completions.completion_tokens,
            "total_tokens": metered.completions.total_tokens,
        }
    except Exception as error:
        category = "validator" if isinstance(error, HarnessFailure) else "provider"
        return {
            "terminal": "failed",
            "failure_stage": category,
            "failure_category": category,
            "failure_message": str(error),
            "latency_seconds": time.perf_counter() - started,
            "attempts_observed": len(metered.completions.latencies),
            "request_latency_seconds": metered.completions.latencies,
            "prompt_tokens": metered.completions.prompt_tokens,
            "completion_tokens": metered.completions.completion_tokens,
            "total_tokens": metered.completions.total_tokens,
        }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results_path = OUTPUT / "results.jsonl"
    slots, evidence, config, receipt = preflight()
    write_json(OUTPUT / "preflight_receipt.json", receipt)
    existing = {}
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            existing[row["slot_id"]] = row
    started = time.time()
    for index, slot in enumerate(slots, 1):
        if slot["slot_id"] in existing:
            continue
        outcome = verify(slot, evidence[slot["slot_id"]], config)
        record = {
            "slot_id": slot["slot_id"],
            "source_slot_id": slot["source_slot_id"],
            "source_record_sha256": slot["source_record_sha256"],
            "case_id": slot["case_id"],
            "candidate_id": slot["candidate_id"],
            "repetition": slot["repetition"],
            "source_first_status": slot["source_first_status"],
            "expected": slot["expected"],
            "long_range_class": "OBJECT_MEDIATED_SCENE_INTERACTION",
            "evidence_sha256": slot["evidence_sha256"],
            "escalation": outcome,
        }
        with results_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        print(f"[{index}/8] {slot['slot_id']} -> {outcome['terminal']}:{outcome.get('status', '-')}", flush=True)

    rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line]
    elder = [row for row in rows if row["case_id"] == "challenge_004"]
    controls = [row for row in rows if row["case_id"].startswith("F1::")]
    success = sum(row["escalation"]["terminal"] == "success" for row in rows)
    failures = len(rows) - success
    logical_calls = sum(1 for row in rows if row["escalation"]["terminal"] in {"success", "failed"})
    attempts = sum(
        len(row["escalation"].get("request_latency_seconds", [])) for row in rows
    )
    retry_count = sum(
        int(row["escalation"].get("protocol", {}).get("retry_count", 0) or 0)
        for row in rows
    )
    recovered = sum(
        bool(row["escalation"].get("protocol", {}).get("recovered", False))
        for row in rows
    )
    elder_satisfied = sum(row["escalation"].get("status") == "satisfied" for row in elder)
    controls_not_satisfied = sum(row["escalation"].get("status") == "not_satisfied" for row in controls)
    gate = {
        "elder_satisfied_at_least_4_of_5": elder_satisfied >= 4,
        "F1_negative_not_satisfied_3_of_3": controls_not_satisfied == 3,
        "new_false_assignment_zero": sum(row["escalation"].get("status") == "satisfied" for row in controls) == 0,
        "inherited_controls_verified": receipt["inherited_controls_verified"] == 20,
        "final_failure_zero": failures == 0,
        "terminal_records_8": len(rows) == 8,
        "logical_model_calls_8": logical_calls == 8,
    }
    summary = {
        "schema_version": "LONG_RANGE_8_EXECUTION_SUMMARY_V1",
        "terminal_records": len(rows),
        "success": success,
        "failure": failures,
        "logical_model_calls": logical_calls,
        "protocol_attempts": attempts,
        "retry_count": retry_count,
        "recovered": recovered,
        "elder_satisfied": elder_satisfied,
        "elder_total": len(elder),
        "F1_negative_not_satisfied": controls_not_satisfied,
        "F1_negative_total": len(controls),
        "prompt_tokens": sum(row["escalation"].get("prompt_tokens", 0) for row in rows),
        "completion_tokens": sum(row["escalation"].get("completion_tokens", 0) for row in rows),
        "total_tokens": sum(row["escalation"].get("total_tokens", 0) for row in rows),
        "model_latency_seconds": sum(row["escalation"].get("latency_seconds", 0) for row in rows),
        "wall_seconds": time.time() - started,
        "gate": gate,
        "confirmed": all(gate.values()),
        "verdict": "LONG_RANGE_NOT_SATISFIED_ESCALATION_MECHANISM_CONFIRMED" if all(gate.values()) else "LONG_RANGE_NOT_SATISFIED_ESCALATION_MECHANISM_NOT_CONFIRMED",
        "production_policy_confirmed": False,
    }
    write_json(OUTPUT / "execution_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
