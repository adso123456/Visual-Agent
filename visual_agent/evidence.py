import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


ISOLATED_BACKGROUND_RGB = (128, 128, 128)
BEHAVIOR_MARGIN = 0.35
BEHAVIOR_CONTOUR_RGB = (255, 0, 0)
BEHAVIOR_CONTOUR_WIDTH = 5


def _load_image_and_mask(
    image_path: Path,
    mask: np.ndarray,
) -> tuple[Image.Image, np.ndarray]:
    image = Image.open(image_path).convert("RGB")
    normalized_mask = np.asarray(mask, dtype=bool)
    if normalized_mask.shape != (image.height, image.width):
        raise ValueError(
            f"candidate mask 尺寸 {normalized_mask.shape} 与原图 "
            f"{(image.height, image.width)} 不一致"
        )
    return image, normalized_mask


def build_isolated_instance_evidence(
    image_path: Path,
    mask: np.ndarray,
) -> Image.Image:
    """保留实例原始像素，其余区域替换为固定中性灰。"""
    image, normalized_mask = _load_image_and_mask(image_path, mask)
    pixels = np.asarray(image)
    isolated = np.full_like(pixels, ISOLATED_BACKGROUND_RGB)
    isolated[normalized_mask] = pixels[normalized_mask]
    return Image.fromarray(isolated, mode="RGB")


def build_behavior_evidence(
    image_path: Path,
    bbox: list[float],
    mask: np.ndarray,
) -> Image.Image:
    """构建固定 35% 上下文，并仅用当前实例 mask contour 标识身份。"""
    image, normalized_mask = _load_image_and_mask(image_path, mask)
    crop = expanded_candidate_bbox(image.size, bbox)

    crop_pixels = np.asarray(image.crop(tuple(crop))).copy()
    mask_crop = (
        normalized_mask[crop[1] : crop[3], crop[0] : crop[2]].astype(np.uint8)
        * 255
    )
    _draw_mask_contour(crop_pixels, mask_crop)
    return Image.fromarray(crop_pixels, mode="RGB")


def expanded_candidate_bbox(
    image_size: tuple[int, int],
    bbox: list[float],
) -> list[int]:
    """按固定 35% margin 生成 candidate-local crop；供 behavior 与 R2 secondary grounding 共用。"""
    if len(bbox) != 4:
        raise ValueError("candidate bbox 必须包含四个坐标")
    x1, y1, x2, y2 = bbox
    width = x2 - x1
    height = y2 - y1
    if width <= 0 or height <= 0:
        raise ValueError("candidate bbox 必须具有正面积")
    image_width, image_height = image_size
    crop = [
        max(0, math.floor(x1 - BEHAVIOR_MARGIN * width)),
        max(0, math.floor(y1 - BEHAVIOR_MARGIN * height)),
        min(image_width, math.ceil(x2 + BEHAVIOR_MARGIN * width)),
        min(image_height, math.ceil(y2 + BEHAVIOR_MARGIN * height)),
    ]
    if crop[0] >= crop[2] or crop[1] >= crop[3]:
        raise ValueError("candidate behavior crop 为空")
    return crop


def build_subject_conditioned_grounding_view(
    image_path: Path,
    bbox: list[float],
) -> tuple[Image.Image, list[int]]:
    """R2 固定 secondary view：原图上按 subject bbox 向四周扩展 35%，禁止额外调参。"""
    image = Image.open(image_path).convert("RGB")
    crop = expanded_candidate_bbox(image.size, bbox)
    return image.crop(tuple(crop)), crop


def _draw_mask_contour(pixels: np.ndarray, mask: np.ndarray) -> None:
    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    cv2.drawContours(
        pixels,
        contours,
        -1,
        BEHAVIOR_CONTOUR_RGB,
        BEHAVIOR_CONTOUR_WIDTH,
    )


def build_candidate_marked_full_scene_evidence(
    image_path: Path,
    mask: np.ndarray,
) -> Image.Image:
    """R3 fallback：保持完整原图尺度，仅用当前 candidate 的红色 mask 轮廓锚定身份。"""
    image, normalized_mask = _load_image_and_mask(image_path, mask)
    pixels = np.asarray(image).copy()
    _draw_mask_contour(pixels, normalized_mask.astype(np.uint8) * 255)
    return Image.fromarray(pixels, mode="RGB")


def _bbox_area(box: Sequence[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _bbox_intersection_area(box_a: Sequence[float], box_b: Sequence[float]) -> float:
    width = max(0.0, min(box_a[2], box_b[2]) - max(box_a[0], box_b[0]))
    height = max(0.0, min(box_a[3], box_b[3]) - max(box_a[1], box_b[1]))
    return width * height


def identity_contamination_risk(
    image_size: tuple[int, int],
    candidate_id: str,
    candidates: Sequence[Mapping],
) -> bool:
    """冻结 predicate：当前 candidate 的 35% crop 覆盖任一 non-target candidate
    bbox >= 70% 且该 non-target 中心位于 crop 内（合同 §1.3）。

    - candidates 为带 `{id, bbox}` 的序列；按 candidate ID 排除当前 candidate，
      不依赖 bbox equality。
    - crop 复用 `expanded_candidate_bbox`（35% margin、floor/ceil、image clamp）。
    - 裁决完全由 bbox 几何确定，不得根据 case ID、模型文本或输出状态覆盖。
    """
    if len(candidates) < 2:
        return False
    current = next(
        (candidate for candidate in candidates if candidate["id"] == candidate_id),
        None,
    )
    if current is None:
        return False
    crop = expanded_candidate_bbox(image_size, current["bbox"])
    for neighbor in candidates:
        if neighbor["id"] == candidate_id:
            continue
        neighbor_box = neighbor["bbox"]
        neighbor_area = _bbox_area(neighbor_box)
        if neighbor_area <= 0:
            continue
        overlap = _bbox_intersection_area(neighbor_box, crop)
        if overlap / neighbor_area < 0.70:
            continue
        center_x = (neighbor_box[0] + neighbor_box[2]) / 2.0
        center_y = (neighbor_box[1] + neighbor_box[3]) / 2.0
        if crop[0] <= center_x <= crop[2] and crop[1] <= center_y <= crop[3]:
            return True
    return False


def blend_non_target_people(
    source: np.ndarray,
    target_mask: np.ndarray,
    person_masks: list[np.ndarray],
) -> np.ndarray:
    """按冻结整数公式弱化非目标人物；目标 mask 在重叠区域优先（合同 §1.4）。

    像素公式（RGB 每 channel，uint8 -> uint16 计算后写回）：
        output = (45 * original + 55 * 128 + 50) // 100
    de-emphasis 区域 = union(non_target masks) & ~target_mask；
    target mask 内像素保持原 RGB（target-wins）。这是 de-emphasis，不是删除。
    """
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
        45 * original + 55 * ISOLATED_BACKGROUND_RGB[0] + 50
    ) // 100
    return result


def build_target_anchored_behavior_evidence(
    image_path: Path,
    bbox: list[float],
    target_mask: np.ndarray,
    person_masks: list[np.ndarray],
) -> Image.Image:
    """Arm B/C first-pass local：全图 de-emphasis 后按 35% crop 裁剪，
    仅绘制 target 的 5px 红色 mask contour（合同 §1.4 local 视图）。"""
    image, target = _load_image_and_mask(image_path, target_mask)
    people = [np.asarray(mask, dtype=bool) for mask in person_masks]
    if any(mask.shape != (image.height, image.width) for mask in people):
        raise ValueError("candidate mask 尺寸必须与原图一致")
    pixels = blend_non_target_people(np.asarray(image), target, people)

    crop = expanded_candidate_bbox(image.size, bbox)
    evidence = pixels[crop[1] : crop[3], crop[0] : crop[2]].copy()
    contour_mask = target[crop[1] : crop[3], crop[0] : crop[2]].astype(
        np.uint8
    ) * 255
    _draw_mask_contour(evidence, contour_mask)
    return Image.fromarray(evidence, mode="RGB")


def build_target_anchored_full_scene_evidence(
    image_path: Path,
    target_mask: np.ndarray,
    person_masks: list[np.ndarray],
) -> Image.Image:
    """Arm C fallback full-scene：全图 de-emphasis + target 5px 红 contour，
    不裁剪、不预缩放（合同 §1.4 full-scene 视图）。"""
    image, target = _load_image_and_mask(image_path, target_mask)
    people = [np.asarray(mask, dtype=bool) for mask in person_masks]
    if any(mask.shape != (image.height, image.width) for mask in people):
        raise ValueError("candidate mask 尺寸必须与原图一致")
    pixels = blend_non_target_people(np.asarray(image), target, people)
    contour_mask = target.astype(np.uint8) * 255
    _draw_mask_contour(pixels, contour_mask)
    return Image.fromarray(pixels, mode="RGB")
