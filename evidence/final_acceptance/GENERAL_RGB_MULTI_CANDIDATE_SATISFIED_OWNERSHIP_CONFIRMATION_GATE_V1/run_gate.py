"""20-slot multi-candidate satisfied ownership confirmation Gate。"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

from PIL import Image

from visual_agent.vlm import verify_candidate_constraints
from visual_agent.vlm_client import load_vlm_config


PROJECT = Path(r"E:\3\Visual Agent\_implementation_worktree")
OUTPUT = Path(
    r"E:\3\_visual_agent_real_world_acceptance\v1"
    r"\multi_candidate_satisfied_ownership_confirmation_gate_v1"
)
EVIDENCE = Path(
    r"E:\3\Visual Agent\_evidence_worktree\evidence\final_acceptance"
    r"\GENERAL_RGB_R3_CANDIDATE_IDENTITY_REMEDIATION_V1\execution\evidence"
)
EXPECTED_HEAD = "e829315f33b7c41175726f10c53554d2be1d7a64"
EXPECTED_MODEL = "qwen3.8:27b-mtp-q4_K_M"
EXPECTED_BASE_URL = "http://192.168.250.9:11434/v1"

CASES = (
    {
        "case_id": "challenge_001",
        "candidate_id": "A",
        "bbox": [183.95, 60.79, 234.64, 148.47],
        "image_sha256": "179af15ea7f004631e99d0906e3542f81982760cc81b7320112847b54af4827c",
        "candidate_count": 2,
        "identity_risk": True,
        "first_arm": "B",
        "ordinary_full_arm": "C",
    },
    {
        "case_id": "challenge_001",
        "candidate_id": "B",
        "bbox": [155.37, 23.12, 205.32, 124.4],
        "image_sha256": "179af15ea7f004631e99d0906e3542f81982760cc81b7320112847b54af4827c",
        "candidate_count": 2,
        "identity_risk": True,
        "first_arm": "B",
        "ordinary_full_arm": "C",
    },
    {
        "case_id": "F1::fishing_014.jpeg",
        "candidate_id": "B",
        "bbox": [4208.56, 2371.68, 4931.18, 3156.99],
        "image_sha256": "8e04ceaa925594739664cc49e1908ff2f94ba48f82badfb83592c3c5ebad7355",
        "candidate_count": 3,
        "identity_risk": False,
        "first_arm": "A",
        "ordinary_full_arm": "A",
    },
    {
        "case_id": "F1::fishing_010.jpeg",
        "candidate_id": "C",
        "bbox": [2410.05, 854.47, 3121.58, 1894.21],
        "image_sha256": "acaa943cb04cf5a94bdf56632add1b324dbc46f9354a0b774e837936ac4653f4",
        "candidate_count": 3,
        "identity_risk": False,
        "first_arm": "A",
        "ordinary_full_arm": "A",
    },
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def preflight() -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT, capture_output=True,
        text=True, check=True,
    ).stdout.strip()
    if head != EXPECTED_HEAD:
        raise RuntimeError(f"HEAD 不匹配：{head}")
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=PROJECT,
        capture_output=True, text=True, check=True,
    ).stdout
    if dirty:
        raise RuntimeError("implementation worktree 非 clean")
    config = load_vlm_config()
    if config.model != EXPECTED_MODEL:
        raise RuntimeError(f"VLM model 不匹配：{config.model}")
    if config.base_url.rstrip("/") != EXPECTED_BASE_URL:
        raise RuntimeError(f"VLM endpoint 不匹配：{config.base_url}")
    if config.timeout != 120:
        raise RuntimeError(f"VLM timeout 不匹配：{config.timeout}")
    for case in CASES:
        root = EVIDENCE / case["image_sha256"] / case["candidate_id"]
        for arm, name in (
            (case["first_arm"], "isolated.png"),
            (case["first_arm"], "local.png"),
            (case["ordinary_full_arm"], "fallback_full_scene.png"),
            ("C", "fallback_full_scene.png"),
        ):
            if not (root / arm / name).is_file():
                raise RuntimeError(f"冻结 evidence 缺失：{root / arm / name}")


def load_images(case: dict) -> tuple[list[Image.Image], Image.Image, Image.Image]:
    root = EVIDENCE / case["image_sha256"] / case["candidate_id"]
    first_root = root / case["first_arm"]
    first = [
        Image.open(first_root / "isolated.png").convert("RGB"),
        Image.open(first_root / "local.png").convert("RGB"),
    ]
    ordinary = Image.open(
        root / case["ordinary_full_arm"] / "fallback_full_scene.png"
    ).convert("RGB")
    anchored = Image.open(root / "C" / "fallback_full_scene.png").convert("RGB")
    return first, ordinary, anchored


def verify(case: dict, images: list[Image.Image]) -> tuple[str, dict, float]:
    started = time.perf_counter()
    checks, metadata = verify_candidate_constraints(
        {"id": case["candidate_id"], "bbox": case["bbox"]},
        [{"text": "正在钓鱼", "route": "behavior"}],
        images,
        "behavior",
    )
    return checks[0]["status"], metadata, round(time.perf_counter() - started, 4)


def main() -> None:
    existing = {path.name for path in OUTPUT.iterdir()} if OUTPUT.exists() else set()
    if existing - {"run_gate.py"}:
        raise RuntimeError(f"输出目录已有执行结果，拒绝覆盖：{sorted(existing)}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    preflight()
    schedule = [
        {
            "ordinal": ordinal,
            "slot_id": f"{case['case_id']}|{case['candidate_id']}|r{repetition}",
            "repetition": repetition,
            **case,
        }
        for ordinal, (case, repetition) in enumerate(
            ((case, repetition) for case in CASES for repetition in range(1, 6)),
            start=1,
        )
    ]
    write_json(OUTPUT / "frozen_schedule.json", schedule)
    write_json(
        OUTPUT / "execution_manifest.json",
        {
            "stage": "MULTI_CANDIDATE_SATISFIED_OWNERSHIP_CONFIRMATION_GATE_V1",
            "implementation_head": EXPECTED_HEAD,
            "model": EXPECTED_MODEL,
            "base_url": EXPECTED_BASE_URL,
            "timeout_seconds": 120,
            "concurrency": 1,
            "scheduled_slots": 20,
            "failed_execution_replacement": False,
            "production_modification_authorized": False,
        },
    )
    raw_path = OUTPUT / "raw_execution.jsonl"
    with raw_path.open("x", encoding="utf-8", newline="\n") as raw:
        for slot in schedule:
            print(f"START [{slot['ordinal']}/20] {slot['slot_id']}", flush=True)
            record = {key: value for key, value in slot.items()}
            record["terminal_status"] = "error"
            try:
                first_images, ordinary_full, anchored_full = load_images(slot)
                record["first_pass_evidence_sha256"] = [
                    sha256(
                        EVIDENCE / slot["image_sha256"] / slot["candidate_id"]
                        / slot["first_arm"] / name
                    )
                    for name in ("isolated.png", "local.png")
                ]
                first_status, first_meta, first_elapsed = verify(slot, first_images)
                confirmation_attempted = (
                    slot["candidate_count"] >= 2 and first_status == "satisfied"
                )
                existing_fallback_attempted = False
                confirmation_status = None
                fallback_status = None
                final_status = first_status
                second_meta = None
                second_elapsed = 0.0
                if confirmation_attempted:
                    full = anchored_full if slot["identity_risk"] else ordinary_full
                    confirmation_status, second_meta, second_elapsed = verify(
                        slot, [*first_images, full]
                    )
                    final_status = confirmation_status
                elif first_status == "uncertain" and slot["candidate_count"] >= 2:
                    existing_fallback_attempted = True
                    full = anchored_full if slot["identity_risk"] else ordinary_full
                    fallback_status, second_meta, second_elapsed = verify(
                        slot, [*first_images, full]
                    )
                    final_status = fallback_status
                elif first_status == "not_satisfied":
                    existing_fallback_attempted = True
                    fallback_status, second_meta, second_elapsed = verify(
                        slot, [*first_images, anchored_full]
                    )
                    final_status = fallback_status
                record.update(
                    {
                        "terminal_status": "success",
                        "first_pass_status": first_status,
                        "confirmation_attempted": confirmation_attempted,
                        "confirmation_status": confirmation_status,
                        "existing_fallback_attempted": existing_fallback_attempted,
                        "existing_fallback_status": fallback_status,
                        "final_status": final_status,
                        "identity_risk": slot["identity_risk"],
                        "first_pass_metadata": first_meta,
                        "second_pass_metadata": second_meta,
                        "first_pass_elapsed_seconds": first_elapsed,
                        "second_pass_elapsed_seconds": second_elapsed,
                    }
                )
            except Exception as error:  # terminal failure 必须原样保留
                record["error_type"] = type(error).__name__
                record["error"] = str(error)
            raw.write(json.dumps(record, ensure_ascii=False) + "\n")
            raw.flush()
            print(
                f"DONE  [{slot['ordinal']}/20] {slot['slot_id']} "
                f"{record['terminal_status']} first={record.get('first_pass_status')} "
                f"confirm={record.get('confirmation_status')} final={record.get('final_status')}",
                flush=True,
            )

    rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
    success = [row for row in rows if row["terminal_status"] == "success"]
    groups = {
        (case_id, candidate_id): [
            row for row in success
            if row["case_id"] == case_id and row["candidate_id"] == candidate_id
        ]
        for case_id, candidate_id in (
            ("challenge_001", "A"),
            ("challenge_001", "B"),
            ("F1::fishing_014.jpeg", "B"),
            ("F1::fishing_010.jpeg", "C"),
        )
    }
    satisfied = {
        f"{key[0]}|{key[1]}": sum(row["final_status"] == "satisfied" for row in value)
        for key, value in groups.items()
    }
    gates = {
        "all_terminal_success": len(success) == 20,
        "challenge_001_A_final_satisfied_zero": satisfied["challenge_001|A"] == 0,
        "challenge_001_B_final_satisfied_at_least_4": satisfied["challenge_001|B"] >= 4,
        "F1_014_B_final_satisfied_zero": satisfied["F1::fishing_014.jpeg|B"] == 0,
        "F1_010_C_final_satisfied_zero": satisfied["F1::fishing_010.jpeg|C"] == 0,
    }
    gates["gate_pass"] = all(gates.values())
    summary = {
        "execution": {"scheduled": 20, "completed": len(rows), "success": len(success), "error": 20 - len(success)},
        "final_satisfied_counts": satisfied,
        "confirmation_attempts": sum(bool(row.get("confirmation_attempted")) for row in success),
        "gates": gates,
    }
    write_json(OUTPUT / "summary.json", summary)
    report = "# Multi-candidate Satisfied Ownership Confirmation Gate\n\n"
    report += f"- Execution: {len(success)}/20 success\n"
    report += f"- Final satisfied counts: `{json.dumps(satisfied, ensure_ascii=False)}`\n"
    report += f"- Gate: `{'PASS' if gates['gate_pass'] else 'FAIL'}`\n"
    (OUTPUT / "EXECUTION_REPORT.md").write_text(report, encoding="utf-8", newline="\n")
    files = []
    for path in sorted(OUTPUT.iterdir()):
        if path.is_file() and path.name != "artifact_manifest.json":
            files.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_json(OUTPUT / "artifact_manifest.json", {"file_count": len(files), "files": files})


if __name__ == "__main__":
    main()
