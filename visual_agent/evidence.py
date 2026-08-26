import math
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
