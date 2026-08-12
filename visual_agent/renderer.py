import json
from copy import deepcopy
from pathlib import Path

import cv2
import numpy as np

from visual_agent.actions import ImageActionExecutor


def _next_result_paths(output_dir: Path, image_suffix: str) -> tuple[Path, Path]:
    numbers = []
    for path in output_dir.glob("result_*.*"):
        try:
            numbers.append(int(path.stem.removeprefix("result_")))
        except ValueError:
            continue
    number = max(numbers, default=0) + 1
    return (
        output_dir / f"result_{number:03d}{image_suffix}",
        output_dir / f"result_{number:03d}.json",
    )


def save_results(image_path: Path, result: dict, output_dir: Path) -> tuple[Path, Path]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"OpenCV 无法读取图片：{image_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    action_type = result["plan"]["action"]["type"]
    image_suffix = ".png" if action_type == "cutout" and result["targets"] else ".jpg"
    image_output, json_output = _next_result_paths(output_dir, image_suffix)
    result_stem = image_output.stem
    json_result = deepcopy(result)

    masks = []
    for target, json_target in zip(result["targets"], json_result["targets"]):
        mask = target.get("_mask")
        mask_score = target.get("_mask_score")
        json_target.pop("_mask", None)
        json_target.pop("_mask_score", None)
        if mask is None or mask_score is None:
            raise RuntimeError(f"目标 {target['id']} 缺少 SAM2 分割结果")
        if mask.shape != image.shape[:2]:
            raise RuntimeError(
                f"目标 {target['id']} mask 尺寸 {mask.shape} 与原图 {image.shape[:2]} 不一致"
            )

        mask_output = output_dir / f"{result_stem}_mask_{target['id']}.png"
        binary_mask = mask.astype(np.uint8) * 255
        if not cv2.imwrite(str(mask_output), binary_mask):
            raise RuntimeError(f"无法保存 binary mask：{mask_output}")
        json_target["segmentation"] = {
            "mask_path": mask_output.as_posix(),
            "mask_score": round(mask_score, 4),
            "mask_area_pixels": int(mask.sum()),
        }
        masks.append(mask)

    image = ImageActionExecutor().execute(image, masks, action_type)
    json_result["action_result"] = {
        "type": action_type,
        "image_path": image_output.as_posix(),
    }

    if not cv2.imwrite(str(image_output), image):
        raise RuntimeError(f"无法保存结果图片：{image_output}")
    json_output.write_text(
        json.dumps(json_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return image_output, json_output
