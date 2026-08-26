"""复制冻结输入原始字节，并生成最终证据文件 SHA-256 清单。"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(r"E:\3\_visual_agent_real_world_acceptance\v1\_general_rgb_final_acceptance_v1")
INPUTS = ROOT / "inputs" / "by_sha256"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    schedule = json.loads((ROOT / "frozen_schedule.json").read_text(encoding="utf-8"))
    INPUTS.mkdir(parents=True, exist_ok=True)
    input_map = []
    for row in schedule:
        source = Path(row["image_path"])
        suffix = source.suffix.lower()
        destination = INPUTS / f"{row['image_sha256']}{suffix}"
        if not destination.exists():
            shutil.copyfile(source, destination)
        if sha256(destination) != row["image_sha256"]:
            raise RuntimeError(f"输入原始字节 SHA-256 不一致：{source}")
        input_map.append({
            "unit_id": row["unit_id"],
            "case_id": row["case_id"],
            "original_source_path": row["image_path"],
            "evidence_input_path": destination.relative_to(ROOT).as_posix(),
            "sha256": row["image_sha256"],
            "bytes": destination.stat().st_size,
        })
    (ROOT / "input_evidence_map.json").write_text(
        json.dumps(input_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    excluded = {"final_evidence_manifest.json"}
    files = []
    for path in sorted(item for item in ROOT.rglob("*") if item.is_file()):
        if path.name in excluded:
            continue
        files.append({
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        })
    manifest = {
        "schema_version": "GENERAL_RGB_FINAL_ACCEPTANCE_EVIDENCE_MANIFEST_V1",
        "stage": "GENERAL_RGB_FINAL_ACCEPTANCE_V1",
        "final_decision": "FAIL",
        "production_commit": "4dac9cb3823e22e90ff3bb8157c6544c6c6b88fd",
        "scheduled_units": 140,
        "unique_input_files": len({item["evidence_input_path"] for item in input_map}),
        "files": len(files),
        "bytes": sum(item["bytes"] for item in files),
        "entries": files,
    }
    (ROOT / "final_evidence_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: manifest[key] for key in ["unique_input_files", "files", "bytes"]}))


if __name__ == "__main__":
    main()
