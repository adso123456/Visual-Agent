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
    if len(bbox) != 4:
        raise ValueError("candidate bbox 必须包含四个坐标")
    x1, y1, x2, y2 = bbox
    width = x2 - x1
    height = y2 - y1
    if width <= 0 or height <= 0:
        raise ValueError("candidate bbox 必须具有正面积")
    crop = [
        max(0, math.floor(x1 - BEHAVIOR_MARGIN * width)),
        max(0, math.floor(y1 - BEHAVIOR_MARGIN * height)),
        min(image.width, math.ceil(x2 + BEHAVIOR_MARGIN * width)),
        min(image.height, math.ceil(y2 + BEHAVIOR_MARGIN * height)),
    ]
    if crop[0] >= crop[2] or crop[1] >= crop[3]:
        raise ValueError("candidate behavior crop 为空")

    crop_pixels = np.asarray(image.crop(tuple(crop))).copy()
    mask_crop = (
        normalized_mask[crop[1] : crop[3], crop[0] : crop[2]].astype(np.uint8)
        * 255
    )
    contours, _ = cv2.findContours(
        mask_crop,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    cv2.drawContours(
        crop_pixels,
        contours,
        -1,
        BEHAVIOR_CONTOUR_RGB,
        BEHAVIOR_CONTOUR_WIDTH,
    )
    return Image.fromarray(crop_pixels, mode="RGB")
