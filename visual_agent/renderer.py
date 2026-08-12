import json
from copy import deepcopy
from pathlib import Path

import cv2
import numpy as np


def _next_result_paths(output_dir: Path) -> tuple[Path, Path]:
    numbers = []
    for path in output_dir.glob("result_*.*"):
        try:
            numbers.append(int(path.stem.removeprefix("result_")))
        except ValueError:
            continue
    number = max(numbers, default=0) + 1
    return (
        output_dir / f"result_{number:03d}.jpg",
        output_dir / f"result_{number:03d}.json",
    )


def save_results(image_path: Path, result: dict, output_dir: Path) -> tuple[Path, Path]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"OpenCV 无法读取图片：{image_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    image_output, json_output = _next_result_paths(output_dir)
    result_stem = image_output.stem
    json_result = deepcopy(result)

    colors = [(0, 200, 0), (255, 120, 0), (0, 120, 255), (180, 0, 180)]
    for index, (target, json_target) in enumerate(zip(result["targets"], json_result["targets"])):
        mask = target.pop("_mask", None)
        mask_score = target.pop("_mask_score", None)
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

        color = colors[index % len(colors)]
        overlay = np.zeros_like(image)
        overlay[mask] = color
        image = cv2.addWeighted(image, 1.0, overlay, 0.4, 0)
        contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(image, contours, -1, color, 2)

    for index, target in enumerate(result["targets"]):
        x1, y1, x2, y2 = (round(value) for value in target["bbox"])
        color = colors[index % len(colors)]
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        text = f'{target["text_label"]} {target["confidence"]:.2f}'
        cv2.putText(
            image,
            text,
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            color,
            2,
            cv2.LINE_AA,
        )

    if not cv2.imwrite(str(image_output), image):
        raise RuntimeError(f"无法保存结果图片：{image_output}")
    json_output.write_text(
        json.dumps(json_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return image_output, json_output
