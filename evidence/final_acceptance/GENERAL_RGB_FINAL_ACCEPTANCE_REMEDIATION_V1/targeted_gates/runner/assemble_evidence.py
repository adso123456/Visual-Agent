"""Assemble Targeted Remediation Gate evidence into the evidence branch work clone."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


OUTPUT = Path(r"E:\3\_visual_agent_real_world_acceptance\v1\_general_rgb_final_acceptance_remediation_v1")
RUNNER = Path(r"E:\3\Visual Agent\_gate_runner")
EVIDENCE_DIR = Path(r"E:\3\Visual Agent\_evidence_worktree\evidence\final_acceptance\GENERAL_RGB_FINAL_ACCEPTANCE_REMEDIATION_V1")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    dest = EVIDENCE_DIR / "targeted_gates"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    entries = []

    def add(src: Path, rel: str) -> None:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        entries.append({"path": str(target.relative_to(EVIDENCE_DIR)), "sha256": sha256(target), "bytes": target.stat().st_size})

    for gate in (1, 2, 3, 4):
        for name in ("gate", "raw_execution"):
            pass
    for f in sorted(OUTPUT.glob("gate*_frozen_schedule.json")):
        add(f, f.name)
    for f in sorted(OUTPUT.glob("raw_execution_gate*.jsonl")):
        add(f, f.name)
    for f in sorted(OUTPUT.glob("gate_adjudication.*")):
        add(f, f.name)
    for f in sorted(RUNNER.glob("run_remediation_gates.py")):
        add(f, "runner/" + f.name)
    for f in sorted(RUNNER.glob("adjudicate_remediation_gates.py")):
        add(f, "runner/" + f.name)
    for f in sorted(RUNNER.glob("assemble_evidence.py")):
        add(f, "runner/" + f.name)
    report = RUNNER / "GENERAL_RGB_FINAL_ACCEPTANCE_REMEDIATION_V1_GATES_REPORT.md"
    if report.is_file():
        add(report, report.name)
    references = {
        "F2_REF": {k: v for k, v in []},
        "note": "R1 marker 负例、R2.3 确定性 35% 规则、R3 双视图等判定参考框见 runner/adjudicate_remediation_gates.py 常量。",
    }
    ref_file = dest / "adjudication_references.json"
    ref_file.write_text(json.dumps(references, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    entries.append({"path": str(ref_file.relative_to(EVIDENCE_DIR)), "sha256": sha256(ref_file), "bytes": ref_file.stat().st_size})

    manifest = {
        "schema_version": "GENERAL_RGB_FINAL_ACCEPTANCE_REMEDIATION_TARGETED_GATES_EVIDENCE_V1",
        "implementation_commit": "41b7b46cd076af7943c14eb421bd4662150fa2fb",
        "contract_commit": "919fcf200fefebbe10f7c87a579def9c8d3f9348",
        "vlm_model": "qwen3.8:27b-mtp-q4_K_M",
        "vlm_base_url": "http://192.168.250.9:11434/v1",
        "concurrency": 1,
        "entries": entries,
    }
    mf = dest / "gate_evidence_manifest.json"
    mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    print("assembled", len(entries), "files into", dest)


if __name__ == "__main__":
    main()
