"""执行冻结的 F4::fishing_017 Gate L，仅调用 Grounding DINO。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw

from visual_agent.grounding import GroundingDetector


EVIDENCE_HEAD = "cad109b"
PRODUCTION_REFERENCE = "be54f3c89171d8b16f53c82397e9f468fb4b4c97"
STAGE = "GENERAL_RGB_F4_SMALL_HELD_OBJECT_LOCALIZATION_V1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(path: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def bbox_iou(left: list[float], right: list[float]) -> float:
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def remap_bbox(bbox: list[float], crop: list[int]) -> list[float]:
    return [
        round(bbox[0] + crop[0], 2),
        round(bbox[1] + crop[1], 2),
        round(bbox[2] + crop[0], 2),
        round(bbox[3] + crop[1], 2),
    ]


def stable_deduplicate(detections: list[dict], threshold: float = 0.8) -> list[dict]:
    ordered = sorted(
        detections,
        key=lambda item: (
            -item["confidence"],
            *item["bbox"],
        ),
    )
    kept: list[dict] = []
    for detection in ordered:
        if any(bbox_iou(detection["bbox"], item["bbox"]) >= threshold for item in kept):
            continue
        kept.append(detection)
    return kept


def localization_metrics(bbox: list[float], reference: dict) -> dict:
    reference_bbox = reference["bbox"]
    reference_center = reference["center"]
    candidate_center = [
        (bbox[0] + bbox[2]) / 2,
        (bbox[1] + bbox[3]) / 2,
    ]
    contains_reference_center = (
        bbox[0] <= reference_center[0] <= bbox[2]
        and bbox[1] <= reference_center[1] <= bbox[3]
    )
    candidate_center_inside_reference = (
        reference_bbox[0] <= candidate_center[0] <= reference_bbox[2]
        and reference_bbox[1] <= candidate_center[1] <= reference_bbox[3]
    )
    iou = bbox_iou(bbox, reference_bbox)
    return {
        "contains_reference_center": contains_reference_center,
        "candidate_center_inside_reference_bbox": candidate_center_inside_reference,
        "iou_with_reference_bbox": round(iou, 6),
        "localized": (
            contains_reference_center
            and candidate_center_inside_reference
            and iou >= 0.1
        ),
    }


def save_view(image: Image.Image, crop: list[int], path: Path) -> dict:
    view = image.crop(tuple(crop))
    view.save(path, format="PNG")
    return {
        "path": str(path),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "dimensions": list(view.size),
        "crop_bbox": crop,
    }


def detector_call(
    detector: GroundingDetector,
    view: dict,
    query: str,
    call_id: str,
) -> dict:
    started = time.perf_counter()
    detections = detector.detect(Path(view["path"]), query, threshold=0.3)
    elapsed = time.perf_counter() - started
    remapped = []
    for detection in detections:
        remapped.append(
            {
                **detection,
                "bbox": remap_bbox(detection["bbox"], view["crop_bbox"]),
            }
        )
    return {
        "call_id": call_id,
        "query": query,
        "threshold": 0.3,
        "view": view,
        "elapsed_seconds": round(elapsed, 6),
        "raw_detections": detections,
        "remapped_detections": remapped,
    }


def hand_crops(base: list[int], subject: list[float], hand_call: dict) -> list[list[int]]:
    eligible = []
    for detection in hand_call["remapped_detections"]:
        bbox = detection["bbox"]
        center = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
        if subject[0] <= center[0] <= subject[2] and subject[1] <= center[1] <= subject[3]:
            eligible.append(detection)
    eligible.sort(key=lambda item: (-item["confidence"], *item["bbox"]))
    crops = []
    for detection in eligible[:2]:
        x1, y1, x2, y2 = detection["bbox"]
        width = x2 - x1
        height = y2 - y1
        crop = [
            max(base[0], math.floor(x1 - width)),
            max(base[1], math.floor(y1 - height)),
            min(base[2], math.ceil(x2 + width)),
            min(base[3], math.ceil(y2 + height)),
        ]
        if crop[0] < crop[2] and crop[1] < crop[3] and crop not in crops:
            crops.append(crop)
    return crops


def overlay(image: Image.Image, reference: dict, arms: dict, path: Path) -> None:
    rendered = image.copy()
    draw = ImageDraw.Draw(rendered)
    draw.rectangle(reference["bbox"], outline="#ff00ff", width=8)
    x, y = reference["center"]
    draw.line((x - 15, y, x + 15, y), fill="#ff00ff", width=5)
    draw.line((x, y - 15, x, y + 15), fill="#ff00ff", width=5)
    colors = {"A": "#ff0000", "B": "#00aa00", "C": "#0066ff"}
    for arm_id, arm in arms.items():
        for detection in arm["deduplicated_detections"]:
            draw.rectangle(detection["bbox"], outline=colors[arm_id], width=5)
    rendered.save(path, format="PNG")


def verify_contract(evidence_root: Path) -> tuple[dict, dict, dict]:
    if not git_head(evidence_root).startswith(EVIDENCE_HEAD):
        raise RuntimeError("evidence worktree HEAD 不是已冻结合同 cad109b")
    stage = evidence_root / "evidence" / "final_acceptance" / STAGE
    manifest_path = stage / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    contract = json.loads((stage / "contract_candidate.json").read_text(encoding="utf-8"))
    selection = json.loads((stage / "selection_candidate.json").read_text(encoding="utf-8"))
    if manifest["status"] != "CONTRACT_APPROVED_FROZEN":
        raise RuntimeError("manifest 未冻结")
    if contract["authorized_scope"] != "GATE_L_DETECTOR_ONLY":
        raise RuntimeError("执行授权不是 Gate L detector only")
    if contract["gate_R"]["authorized"]:
        raise RuntimeError("Gate R 不得授权")
    for entry in manifest["files"]:
        path = stage / entry["path"]
        if sha256(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise RuntimeError(f"合同文件漂移：{entry['path']}")
    return manifest, contract, selection


def run(evidence_root: Path, output_root: Path) -> int:
    if output_root.exists():
        raise RuntimeError("Gate L 输出目录已存在；禁止补跑或覆盖")
    output_root.mkdir(parents=True)
    views_root = output_root / "views"
    views_root.mkdir()
    manifest, contract, selection = verify_contract(evidence_root)
    spec = selection["cases"][0]
    image_path = evidence_root / spec["image_path"]
    if sha256(image_path) != spec["image_sha256"]:
        raise RuntimeError("输入图片 SHA 不一致")
    image = Image.open(image_path).convert("RGB")
    if list(image.size) != spec["image_size"]:
        raise RuntimeError("输入图片尺寸不一致")

    preflight = {
        "status": "PASS",
        "evidence_head": git_head(evidence_root),
        "production_reference": PRODUCTION_REFERENCE,
        "contract_manifest_sha256": sha256(
            evidence_root / "evidence" / "final_acceptance" / STAGE / "manifest.json"
        ),
        "contract_sha256": sha256(
            evidence_root / "evidence" / "final_acceptance" / STAGE / "contract_candidate.json"
        ),
        "selection_sha256": sha256(
            evidence_root / "evidence" / "final_acceptance" / STAGE / "selection_candidate.json"
        ),
        "runner_sha256": sha256(Path(__file__)),
        "relation_vlm_calls_authorized": False,
    }
    (output_root / "preflight.json").write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = {
        "schema_version": "GENERAL_RGB_F4_SMALL_HELD_OBJECT_GATE_L_RESULT_V1",
        "terminal_status": "running",
        "case_id": spec["case_id"],
        "model": contract["detector"]["model"],
        "threshold": 0.3,
        "reference": contract["reference"],
        "arms": {},
        "detector_calls": [],
        "relation_vlm_calls": 0,
    }
    result_path = output_root / "raw_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        detector = GroundingDetector()
        base = contract["arms"]["A"]["base_crop"]

        a_view = save_view(image, base, views_root / "A_base.png")
        a_call = detector_call(detector, a_view, "fish", "A_fish_1")
        result["detector_calls"].append(a_call)
        result["arms"]["A"] = {"calls": [a_call]}

        b_calls = []
        for index, crop in enumerate(contract["arms"]["B"]["tiles"], 1):
            view = save_view(image, crop, views_root / f"B_tile_{index}.png")
            call = detector_call(detector, view, "fish", f"B_fish_{index}")
            b_calls.append(call)
            result["detector_calls"].append(call)
        result["arms"]["B"] = {"calls": b_calls}

        c_hand_view = save_view(image, base, views_root / "C_hand_query_base.png")
        c_hand_call = detector_call(detector, c_hand_view, "hand", "C_hand_1")
        result["detector_calls"].append(c_hand_call)
        c_crops = hand_crops(base, spec["subject_bbox"], c_hand_call)
        c_fish_calls = []
        for index, crop in enumerate(c_crops, 1):
            view = save_view(image, crop, views_root / f"C_hand_{index}.png")
            call = detector_call(detector, view, "fish", f"C_fish_{index}")
            c_fish_calls.append(call)
            result["detector_calls"].append(call)
        result["arms"]["C"] = {
            "hand_call": c_hand_call,
            "hand_crops": c_crops,
            "fish_calls": c_fish_calls,
        }

        for arm_id, arm in result["arms"].items():
            calls = arm.get("calls", arm.get("fish_calls", []))
            detections = [
                detection
                for call in calls
                for detection in call["remapped_detections"]
            ]
            deduplicated = stable_deduplicate(detections)
            for detection in deduplicated:
                detection["localization"] = localization_metrics(
                    detection["bbox"], contract["reference"]
                )
            arm["deduplicated_detections"] = deduplicated
            arm["target_localized"] = any(
                item["localization"]["localized"] for item in deduplicated
            )
            arm["detector_call_count"] = (
                len(calls) + (1 if arm_id == "C" else 0)
            )

        result["terminal_status"] = "success"
        result["gate_L"] = {
            "B_or_C_success": (
                result["arms"]["B"]["target_localized"]
                or result["arms"]["C"]["target_localized"]
            ),
            "decision": (
                "LOCALIZATION_MECHANISM_FOUND"
                if (
                    result["arms"]["B"]["target_localized"]
                    or result["arms"]["C"]["target_localized"]
                )
                else "NOT_FOUND_CLOSE_WITHOUT_RELATION_VLM"
            ),
        }
        overlay(image, contract["reference"], result["arms"], output_root / "overlay.png")
    except Exception as exc:  # 保留首次 terminal failure，不补跑。
        result["terminal_status"] = "failure"
        result["failure_type"] = type(exc).__name__
        result["failure_message"] = str(exc)
    finally:
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    artifacts = []
    for path in sorted(item for item in output_root.rglob("*") if item.is_file()):
        if path.name == "artifact_manifest.json":
            continue
        artifacts.append(
            {
                "path": path.relative_to(output_root).as_posix(),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    artifact_manifest = {
        "schema_version": "GENERAL_RGB_F4_SMALL_HELD_OBJECT_GATE_L_ARTIFACT_MANIFEST_V1",
        "terminal_status": result["terminal_status"],
        "artifacts": artifacts,
    }
    (output_root / "artifact_manifest.json").write_text(
        json.dumps(artifact_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if result["terminal_status"] == "success" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    return run(args.evidence_root.resolve(), args.output_root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
