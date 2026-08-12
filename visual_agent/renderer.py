import json
from pathlib import Path

import cv2


def save_results(
    image_path: Path,
    prompt: str,
    target_info: dict[str, str],
    detections: list[dict],
    output_dir: Path,
) -> tuple[Path, Path]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"OpenCV 无法读取图片：{image_path}")

    targets = []
    for detection in detections:
        x1, y1, x2, y2 = (round(value) for value in detection["bbox"])
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 200, 0), 2)
        text = f'{target_info["grounding_text"]} {detection["confidence"]:.2f}'
        cv2.putText(
            image,
            text,
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 200, 0),
            2,
            cv2.LINE_AA,
        )
        targets.append(
            {
                "label": target_info["label"],
                "bbox": detection["bbox"],
                "confidence": detection["confidence"],
                "reason": target_info["reason"],
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    image_output = output_dir / "result.jpg"
    json_output = output_dir / "result.json"
    if not cv2.imwrite(str(image_output), image):
        raise RuntimeError(f"无法保存结果图片：{image_output}")
    json_output.write_text(
        json.dumps({"prompt": prompt, "targets": targets}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return image_output, json_output
