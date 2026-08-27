import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SELECTION_PATH = Path(
    r"E:\3\Visual Agent\_evidence_worktree\evidence\final_acceptance"
    r"\GENERAL_RGB_R3_CANDIDATE_IDENTITY_REMEDIATION_V1\frozen_selection.json"
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    summary = load_json(ROOT / "execution_summary.json")
    selection = load_json(SELECTION_PATH)
    rows = [json.loads(line) for line in (ROOT / "results.jsonl").read_text(
        encoding="utf-8"
    ).splitlines() if line.strip()]

    fallback = {arm: Counter() for arm in ("A", "B", "C")}
    final_status = {arm: Counter() for arm in ("A", "B", "C")}
    first_status = {arm: Counter() for arm in ("A", "B", "C")}
    grouped = defaultdict(list)
    for row in rows:
        arm = row["arm"]
        final_status[arm][row["final_status"]] += 1
        first_status[arm][row["first_pass"]["status"]] += 1
        grouped[(row["case_id"], row["candidate_id"], arm)].append(
            row["final_status"]
        )
        if "fallback" in row:
            fallback[arm][row["fallback_classification"]] += 1

    observations = summary["gate_observations"]
    a = observations["A"]
    gate = {}
    for arm in ("A", "B", "C"):
        obs = observations[arm]
        checks = {
            "challenge_001_bystander_false_assignment_0_of_5": (
                obs["challenge_001_bystander_false_assignment"] == 0
            ),
            "challenge_001_true_operator_retained_at_least_4_of_5": (
                obs["challenge_001_true_operator_retained"] >= 4
            ),
            "challenge_003_legitimate_uncertain_5_of_5": (
                obs["challenge_003_uncertain_preserved"] == 5
            ),
            "challenge_003_confident_binary_0_of_5": (
                obs["challenge_003_confident_binary"] == 0
            ),
            "challenge_004_elder_retained_at_least_4_of_5": (
                obs["challenge_004_elder_retained"] >= 4
            ),
            "challenge_004_child_false_assignment_0_of_5": (
                obs["challenge_004_child_false_assignment"] == 0
            ),
            "F1_candidate_non_regression_and_at_least_4_of_10": (
                obs["F1_candidate_correct"] >= a["F1_candidate_correct"]
                and obs["F1_candidate_correct"] >= 4
            ),
            "F1_task_non_regression_and_at_least_2_of_6": (
                obs["F1_task_correct"] >= a["F1_task_correct"]
                and obs["F1_task_correct"] >= 2
            ),
            "positive_control_F1_fishing_004_A_satisfied": (
                grouped[("F1::fishing_004.jpeg", "A", arm)] == ["satisfied"]
            ),
            "final_failure_zero": summary["terminal"].get("success") == 105
            and not summary["failures"],
        }
        if arm == "C":
            checks["fallback_harm_zero"] = fallback[arm].get("fallback_harm", 0) == 0
        gate[arm] = {
            "checks": checks,
            "pass": all(checks.values()),
        }

    payload = {
        "schema_version": "R3_FROZEN_GATE_EVALUATION_V1",
        "source": {
            "results": "results.jsonl",
            "execution_summary": "execution_summary.json",
            "selection_sha256": sha256(SELECTION_PATH),
        },
        "system": {
            "scheduled_first_pass_slots": summary["scheduled_first_pass_slots"],
            "terminal_records": summary["terminal_records"],
            "terminal": summary["terminal"],
            "failures": summary["failures"],
            "logical_model_calls": summary["logical_model_calls"],
            "fallback_calls": summary["fallback_calls"],
            "protocol_attempts": summary["protocol_attempts"],
            "retry_count": summary["retry_count"],
            "recovered": summary["recovered"],
        },
        "status_counts": {
            arm: {
                "first_pass": dict(first_status[arm]),
                "final": dict(final_status[arm]),
            }
            for arm in ("A", "B", "C")
        },
        "fallback_classification": {
            "A": {"policy": "REPORT_ONLY", "counts": dict(fallback["A"])},
            "B": {"policy": "NOT_APPLICABLE", "counts": dict(fallback["B"])},
            "C": {"policy": "GATE_REQUIRES_ZERO", "counts": dict(fallback["C"])},
        },
        "gate_observations": observations,
        "gate_evaluation": gate,
        "decision": {
            "arm_A": "CONTROL_NOT_ELIGIBLE",
            "arm_B": "NOT_CONFIRMED",
            "arm_C": "NOT_CONFIRMED",
            "production_policy": "KEEP_CURRENT_PRODUCTION",
            "production_modification": "NOT_AUTHORIZED",
        },
    }
    write_json(ROOT / "gate_evaluation.json", payload)

    report = f"""# R3 Candidate Identity A/B/C Execution Report

## Frozen execution

- Scheduled first-pass calls: {summary['scheduled_first_pass_slots']}
- Terminal records: {summary['terminal_records']} (success {summary['terminal'].get('success', 0)}, failure {sum(summary['failures'].values())})
- Logical Local VLM calls: {summary['logical_model_calls']} (fallback {summary['fallback_calls']})
- Protocol attempts: {summary['protocol_attempts']}; retry {summary['retry_count']}; recovered {summary['recovered']}
- Tokens: prompt {summary['prompt_tokens']}, completion {summary['completion_tokens']}, total {summary['total_tokens']}
- Model latency: {summary['model_latency_seconds']} s; wall time: {summary['wall_seconds']} s
- Provider/model: OpenAI-compatible Local Ollama / `qwen3.8:27b-mtp-q4_K_M`

No failed execution was replaced. No Production code was modified.

## Frozen Gate observations

| Metric | A | B | C |
|---|---:|---:|---:|
| challenge_001 bystander false assignment | {a['challenge_001_bystander_false_assignment']}/5 | {observations['B']['challenge_001_bystander_false_assignment']}/5 | {observations['C']['challenge_001_bystander_false_assignment']}/5 |
| challenge_001 true operator retained | {a['challenge_001_true_operator_retained']}/5 | {observations['B']['challenge_001_true_operator_retained']}/5 | {observations['C']['challenge_001_true_operator_retained']}/5 |
| challenge_003 uncertainty preserved | {a['challenge_003_uncertain_preserved']}/5 | {observations['B']['challenge_003_uncertain_preserved']}/5 | {observations['C']['challenge_003_uncertain_preserved']}/5 |
| challenge_003 confident binary | {a['challenge_003_confident_binary']}/5 | {observations['B']['challenge_003_confident_binary']}/5 | {observations['C']['challenge_003_confident_binary']}/5 |
| challenge_004 elder retained | {a['challenge_004_elder_retained']}/5 | {observations['B']['challenge_004_elder_retained']}/5 | {observations['C']['challenge_004_elder_retained']}/5 |
| challenge_004 child false assignment | {a['challenge_004_child_false_assignment']}/5 | {observations['B']['challenge_004_child_false_assignment']}/5 | {observations['C']['challenge_004_child_false_assignment']}/5 |
| F1 candidate correct | {a['F1_candidate_correct']}/10 | {observations['B']['F1_candidate_correct']}/10 | {observations['C']['F1_candidate_correct']}/10 |
| F1 task correct | {a['F1_task_correct']}/6 | {observations['B']['F1_task_correct']}/6 | {observations['C']['F1_task_correct']}/6 |

Fallback classification: A `{dict(fallback['A'])}` (report only), B N/A, C `{dict(fallback['C'])}` (Gate requires zero harm).

## Decision

- Arm B removes challenge_001 false assignment and safely preserves challenge_003 uncertainty, but it does not retain the challenge_004 elder and regresses the paired F1 candidate/task counts.
- Arm C removes challenge_001 false assignment and matches A on F1, but it converts challenge_003 legitimate uncertainty to confident binary and does not retain the challenge_004 elder.
- Therefore neither B nor C passes all frozen gates. No R3 candidate-identity Production change is authorized; keep the current Production evidence policy.

The full mechanical verdict is in `gate_evaluation.json`; raw terminal records remain in `results.jsonl`.
"""
    (ROOT / "R3_A_B_C_EXECUTION_REPORT.md").write_text(report, encoding="utf-8")

    excluded = {"artifact_manifest.json"}
    files = []
    for path in sorted(p for p in ROOT.rglob("*") if p.is_file()):
        rel = path.relative_to(ROOT).as_posix()
        if rel in excluded:
            continue
        files.append({"path": rel, "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_json(
        ROOT / "artifact_manifest.json",
        {
            "schema_version": "R3_EXECUTION_ARTIFACT_MANIFEST_V1",
            "file_count": len(files),
            "total_bytes": sum(item["bytes"] for item in files),
            "files": files,
        },
    )


if __name__ == "__main__":
    main()
