import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path


REPO = Path(r"E:\3\Visual Agent\_r3_identity_benchmark_v1")
EVIDENCE_REPO = Path(r"E:\3\Visual Agent\_evidence_worktree")
OUTPUT = Path(r"E:\3\_visual_agent_real_world_acceptance\v1\general_rgb_r3_candidate_identity_remediation_v1")
CONTRACT_DIR = EVIDENCE_REPO / "evidence/final_acceptance/GENERAL_RGB_R3_CANDIDATE_IDENTITY_REMEDIATION_V1"
REVIEW_LOCK_SHA256 = "eff9212667c79ec6fe14c36cad1f43e847f59a200de052823a1e8f319e07c10f"

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.path.insert(0, str(REPO))

from benchmark.r3_candidate_identity_v1.evidence_builder import (  # noqa: E402
    materialize_case_evidence,
)
from benchmark.r3_candidate_identity_v1.execution_harness import (  # noqa: E402
    ManifestBinding,
    ManifestEvidenceProvider,
    ProductionBehaviorAdapter,
    run_harness_slots,
    verify_execution_preflight,
)
from benchmark.r3_candidate_identity_v1.mask_cache import MaskCache  # noqa: E402
from benchmark.r3_candidate_identity_v1.runner import ResultRecorder  # noqa: E402
from visual_agent.models import get_segmenter  # noqa: E402


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def materialize(selection):
    mask_root = OUTPUT / "mask_cache"
    evidence_root = OUTPUT / "evidence"
    cache = MaskCache(mask_root)
    segmenter, cached = get_segmenter()
    sam_calls = []

    for index, case in enumerate(selection["cases"], start=1):
        image_path = EVIDENCE_REPO / case["image_path"]

        def segment(image, bboxes):
            results, metrics = segmenter.segment(image, bboxes)
            sam_calls.append(
                {
                    "case_id": case["case_id"],
                    "image_sha256": case["image_sha256"],
                    "bbox_count": len(bboxes),
                    "metrics": metrics,
                }
            )
            return [row["mask"] for row in results]

        cache.build(
            case_id=case["case_id"],
            image_path=image_path,
            image_sha256=case["image_sha256"],
            candidates=case["candidates"],
            segmenter=segment,
        )
        masks = cache.load(
            image_path=image_path,
            image_sha256=case["image_sha256"],
            candidates=case["candidates"],
        )
        materialize_case_evidence(evidence_root, case, image_path, masks)
        print(f"SAM_EVIDENCE {index}/9 {case['case_id']}", flush=True)

    write_json(
        OUTPUT / "sam_materialization.json",
        {
            "schema_version": "R3_REAL_SAM_MATERIALIZATION_V1",
            "segmenter_cached_at_start": cached,
            "logical_image_calls": len(sam_calls),
            "calls": sam_calls,
        },
    )


def binding_maps(selection):
    masks = {}
    evidence = {}
    for case in selection["cases"]:
        image_sha = case["image_sha256"]
        mask_manifest = OUTPUT / "mask_cache" / image_sha / "manifest.json"
        evidence_manifest = OUTPUT / "evidence" / image_sha / "manifest.json"
        masks[case["case_id"]] = ManifestBinding(mask_manifest, sha256(mask_manifest))
        evidence[case["case_id"]] = ManifestBinding(
            evidence_manifest, sha256(evidence_manifest)
        )
    return masks, evidence


def outcome_correct(candidate, status):
    if "expected" in candidate:
        return status == candidate["expected"]
    return status in candidate["allowed"]


def summarize(selection, receipt, results_path, started_at):
    rows = [
        json.loads(line)
        for line in results_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cases = {case["case_id"]: case for case in selection["cases"]}
    terminal = Counter(row["terminal"] for row in rows)
    failures = Counter(
        f"{row.get('failure_stage')}:{row.get('failure_category')}"
        for row in rows
        if row["terminal"] == "failed"
    )
    by_arm = defaultdict(lambda: Counter())
    grouped = defaultdict(list)
    total_prompt_tokens = total_completion_tokens = total_tokens = 0
    logical_calls = protocol_attempts = retry_count = recovered = 0
    total_model_latency = 0.0
    for row in rows:
        by_arm[row["arm"]][row["terminal"]] += 1
        if row["terminal"] != "success":
            continue
        grouped[(row["case_id"], row["candidate_id"], row["arm"])].append(
            row["final_status"]
        )
        for key in ("first_pass", "fallback"):
            call = row.get(key)
            if not call:
                continue
            logical_calls += 1
            protocol = call["protocol"]
            protocol_attempts += protocol["attempts"]
            retry_count += protocol["retry_count"]
            recovered += int(bool(protocol["recovered"]))
            total_prompt_tokens += call["prompt_tokens"]
            total_completion_tokens += call["completion_tokens"]
            total_tokens += call["total_tokens"]
            total_model_latency += call["latency_seconds"]

    gate = {}
    for arm in ("A", "B", "C"):
        def statuses(case_id, candidate_id):
            return grouped.get((case_id, candidate_id, arm), [])

        gate[arm] = {
            "challenge_001_bystander_false_assignment": statuses(
                "challenge_001", "A"
            ).count("satisfied"),
            "challenge_001_true_operator_retained": statuses(
                "challenge_001", "B"
            ).count("satisfied"),
            "challenge_003_uncertain_preserved": statuses(
                "challenge_003", "A"
            ).count("uncertain"),
            "challenge_003_confident_binary": sum(
                status != "uncertain"
                for status in statuses("challenge_003", "A")
            ),
            "challenge_004_elder_retained": statuses(
                "challenge_004", "A"
            ).count("satisfied"),
            "challenge_004_child_false_assignment": statuses(
                "challenge_004", "B"
            ).count("satisfied"),
        }
        f1_candidate_correct = 0
        f1_candidate_total = 0
        f1_task_correct = 0
        f1_task_total = 0
        for case in selection["cases"]:
            if not case["case_id"].startswith("F1::"):
                continue
            final_statuses = []
            for candidate in case["candidates"]:
                observed = statuses(case["case_id"], candidate["id"])
                if len(observed) != 1:
                    continue
                final_statuses.append(observed[0])
                f1_candidate_total += 1
                f1_candidate_correct += int(outcome_correct(candidate, observed[0]))
            if len(final_statuses) == len(case["candidates"]):
                task_status = (
                    "satisfied"
                    if "satisfied" in final_statuses
                    else "uncertain"
                    if "uncertain" in final_statuses
                    else "not_satisfied"
                )
                f1_task_total += 1
                f1_task_correct += int(task_status == case["expected_task_status"])
        gate[arm].update(
            {
                "F1_candidate_correct": f1_candidate_correct,
                "F1_candidate_total": f1_candidate_total,
                "F1_task_correct": f1_task_correct,
                "F1_task_total": f1_task_total,
            }
        )

    payload = {
        "schema_version": "R3_FROZEN_EXECUTION_SUMMARY_V1",
        "scheduled_first_pass_slots": receipt.scheduled_slot_count,
        "terminal_records": len(rows),
        "terminal": dict(terminal),
        "failures": dict(failures),
        "by_arm": {arm: dict(counts) for arm, counts in by_arm.items()},
        "logical_model_calls": logical_calls,
        "protocol_attempts": protocol_attempts,
        "retry_count": retry_count,
        "recovered": recovered,
        "fallback_calls": sum("fallback" in row for row in rows),
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "total_tokens": total_tokens,
        "model_latency_seconds": round(total_model_latency, 3),
        "wall_seconds": round(time.time() - started_at, 3),
        "gate_observations": gate,
    }
    write_json(OUTPUT / "execution_summary.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)


def main():
    started_at = time.time()
    selection_path = CONTRACT_DIR / "frozen_selection.json"
    schedule_path = CONTRACT_DIR / "frozen_schedule.json"
    selection = load_json(selection_path)
    materialize(selection)
    masks, evidence = binding_maps(selection)
    receipt = verify_execution_preflight(
        repo_root=REPO,
        review_lock_path=REPO
        / "benchmark/r3_candidate_identity_v1/harness_review_lock.json",
        review_lock_sha256=REVIEW_LOCK_SHA256,
        contract_path=CONTRACT_DIR / "contract_candidate.json",
        selection_path=selection_path,
        schedule_path=schedule_path,
        execution_bindings_path=REPO
        / "benchmark/r3_candidate_identity_v1/frozen_execution_bindings.json",
        mask_manifests=masks,
        evidence_manifests=evidence,
    )
    write_json(OUTPUT / "preflight_receipt_preview.json", receipt.as_record())
    print(
        f"PREFLIGHT PASS slots={receipt.scheduled_slot_count} "
        f"sequence_sha={receipt.scheduled_slot_sequence_sha256}",
        flush=True,
    )

    os.environ["VLM_MODEL"] = "qwen3.8:27b-mtp-q4_K_M"
    os.environ["VLM_BASE_URL"] = "http://192.168.250.9:11434/v1"
    os.environ["VLM_API_KEY"] = "ollama"
    os.environ["VLM_TIMEOUT"] = "120"
    results_path = OUTPUT / "results.jsonl"
    run_harness_slots(
        preflight=receipt,
        evidence_provider=ManifestEvidenceProvider(receipt),
        verifier=ProductionBehaviorAdapter(preflight=receipt).verify,
        recorder=ResultRecorder(results_path),
    )
    summarize(selection, receipt, results_path, started_at)


if __name__ == "__main__":
    main()
