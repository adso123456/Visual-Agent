import json
import sys
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visual_agent.segmentation import Sam2Segmenter


def main() -> None:
    result_path = ROOT / "benchmark" / "phase7_results" / "core_004" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    target = result["targets"][0]
    group = result["semantic_groups"][0]
    boxes = [group["subject"]["bbox"], group["related_members"][0]["bbox"]]

    segmenter = Sam2Segmenter()
    components, _ = segmenter.segment(ROOT / "images/test_images/commons_umbrella.jpg", boxes)
    subject_mask = components[0]["mask"]
    related_mask = components[1]["mask"]
    composite_mask = np.logical_or(subject_mask, related_mask)

    saved_mask = cv2.imread(
        str(ROOT / target["segmentation"]["mask_path"]),
        cv2.IMREAD_GRAYSCALE,
    ) > 0
    cutout = cv2.imread(
        str(ROOT / result["action_result"]["image_path"]),
        cv2.IMREAD_UNCHANGED,
    )
    assert subject_mask.any()
    assert related_mask.any()
    assert np.array_equal(saved_mask, composite_mask)
    assert target["segmentation"]["mask_area_pixels"] == int(composite_mask.sum())
    assert abs(
        target["segmentation"]["mask_score"]
        - round(min(component["score"] for component in components), 4)
    ) < 1e-4
    assert cutout is not None and cutout.shape[2] == 4
    assert np.array_equal(cutout[:, :, 3] > 0, composite_mask)
    print("Phase 7 composite mask/score/alpha: PASS")


if __name__ == "__main__":
    main()
