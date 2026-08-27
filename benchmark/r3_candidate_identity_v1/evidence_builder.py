"""冻结 R3 A/B/C evidence 构造；本模块不创建模型客户端。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from visual_agent.evidence import (
    BEHAVIOR_CONTOUR_RGB,
    BEHAVIOR_CONTOUR_WIDTH,
    build_behavior_evidence,
    build_candidate_marked_full_scene_evidence,
    build_isolated_instance_evidence,
    expanded_candidate_bbox,
    _draw_mask_contour,
)


NEUTRAL_GRAY = 128
ORIGINAL_WEIGHT = 45
NEUTRAL_WEIGHT = 55


@dataclass(frozen=True)
class ArmEvidence:
    first_pass: tuple[Image.Image, Image.Image]
    fallback: Image.Image | None


def _validated_masks(
    image: Image.Image,
    target_mask: np.ndarray,
    person_masks: list[np.ndarray],
) -> tuple[np.ndarray, list[np.ndarray]]:
    shape = (image.height, image.width)
    target = np.asarray(target_mask, dtype=bool)
    people = [np.asarray(mask, dtype=bool) for mask in person_masks]
    if target.shape != shape or any(mask.shape != shape for mask in people):
        raise ValueError("candidate mask 尺寸必须与原图一致")
    return target, people


def blend_non_target_people(
    source: np.ndarray,
    target_mask: np.ndarray,
    person_masks: list[np.ndarray],
) -> np.ndarray:
    """按冻结整数公式弱化非目标人物；目标 mask 在重叠区域优先。"""
    if source.ndim != 3 or source.shape[2] != 3:
        raise ValueError("source 必须是 RGB 像素数组")
    target = np.asarray(target_mask, dtype=bool)
    people = [np.asarray(mask, dtype=bool) for mask in person_masks]
    if target.shape != source.shape[:2] or any(
        mask.shape != source.shape[:2] for mask in people
    ):
        raise ValueError("candidate mask 尺寸必须与像素数组一致")

    non_target_union = np.zeros(target.shape, dtype=bool)
    for mask in people:
        non_target_union |= mask
    de_emphasis = non_target_union & ~target

    result = source.copy()
    original = source[de_emphasis].astype(np.uint16)
    result[de_emphasis] = (
        ORIGINAL_WEIGHT * original
        + NEUTRAL_WEIGHT * NEUTRAL_GRAY
        + 50
    ) // 100
    return result


def build_target_anchored_evidence(
    image_path: Path,
    bbox: list[float],
    target_mask: np.ndarray,
    person_masks: list[np.ndarray],
    *,
    full_scene: bool,
) -> Image.Image:
    """构造 B/C evidence；只弱化非目标 person，不删除场景上下文。"""
    image = Image.open(image_path).convert("RGB")
    target, people = _validated_masks(image, target_mask, person_masks)
    pixels = blend_non_target_people(np.asarray(image), target, people)

    if full_scene:
        evidence = pixels.copy()
        contour_mask = target.astype(np.uint8) * 255
    else:
        crop = expanded_candidate_bbox(image.size, bbox)
        evidence = pixels[crop[1] : crop[3], crop[0] : crop[2]].copy()
        contour_mask = target[crop[1] : crop[3], crop[0] : crop[2]].astype(
            np.uint8
        ) * 255

    _draw_mask_contour(evidence, contour_mask)
    return Image.fromarray(evidence, mode="RGB")


def build_arm_evidence(
    arm: str,
    image_path: Path,
    bbox: list[float],
    target_mask: np.ndarray,
    person_masks: list[np.ndarray],
) -> ArmEvidence:
    """生成冻结 A/B/C 输入；fallback 仅作为资产生成，不在此决定是否调用。"""
    isolated = build_isolated_instance_evidence(image_path, target_mask)
    if arm == "A":
        return ArmEvidence(
            first_pass=(
                isolated,
                build_behavior_evidence(image_path, bbox, target_mask),
            ),
            fallback=build_candidate_marked_full_scene_evidence(
                image_path, target_mask
            ),
        )
    if arm in {"B", "C"}:
        local = build_target_anchored_evidence(
            image_path,
            bbox,
            target_mask,
            person_masks,
            full_scene=False,
        )
        fallback = None
        if arm == "C":
            fallback = build_target_anchored_evidence(
                image_path,
                bbox,
                target_mask,
                person_masks,
                full_scene=True,
            )
        return ArmEvidence(first_pass=(isolated, local), fallback=fallback)
    raise ValueError(f"未知 arm: {arm}")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_png(image: Image.Image, path: Path) -> dict[str, object]:
    """以 PNG 原样保存 benchmark evidence，并返回可审计元数据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False, compress_level=6)
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "width": image.width,
        "height": image.height,
    }


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def materialize_case_evidence(
    output_root: Path,
    case: dict[str, object],
    image_path: Path,
    masks: dict[str, np.ndarray],
) -> Path:
    """一次性生成单个冻结 case 的全部 A/B/C evidence 与 SHA manifest。"""
    if sha256_file(image_path) != case["image_sha256"]:
        raise ValueError("输入图片 SHA-256 与冻结 selection 不一致")
    candidate_ids = [str(row["id"]) for row in case["candidates"]]
    if set(masks) != set(candidate_ids):
        raise ValueError("mask 集合与冻结 candidate 集合不一致")

    case_root = output_root / str(case["image_sha256"])
    manifest_path = case_root / "manifest.json"
    if manifest_path.exists():
        raise ValueError("case evidence manifest 已存在，禁止覆盖")
    person_masks = [masks[candidate_id] for candidate_id in candidate_ids]
    artifacts: list[dict[str, object]] = []
    for candidate in case["candidates"]:
        candidate_id = str(candidate["id"])
        for arm in ("A", "B", "C"):
            evidence = build_arm_evidence(
                arm,
                image_path,
                list(candidate["bbox"]),
                masks[candidate_id],
                person_masks,
            )
            arm_root = case_root / candidate_id / arm
            for name, image in zip(
                ("isolated", "local"), evidence.first_pass, strict=True
            ):
                record = save_png(image, arm_root / f"{name}.png")
                record.update(
                    {
                        "candidate_id": candidate_id,
                        "arm": arm,
                        "stage": "first_pass",
                        "evidence_type": name,
                    }
                )
                artifacts.append(record)
            if evidence.fallback is not None:
                record = save_png(
                    evidence.fallback, arm_root / "fallback_full_scene.png"
                )
                record.update(
                    {
                        "candidate_id": candidate_id,
                        "arm": arm,
                        "stage": "fallback",
                        "evidence_type": "full_scene",
                    }
                )
                artifacts.append(record)
    write_manifest(
        manifest_path,
        {
            "schema_version": "R3_CANDIDATE_EVIDENCE_MANIFEST_V1",
            "case_id": case["case_id"],
            "source_image": {
                "path": image_path.as_posix(),
                "sha256": case["image_sha256"],
            },
            "artifacts": artifacts,
        },
    )
    return manifest_path
