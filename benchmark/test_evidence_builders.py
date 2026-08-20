from pathlib import Path

import numpy as np
from PIL import Image

from visual_agent.evidence import (
    BEHAVIOR_MARGIN,
    build_behavior_evidence,
    build_isolated_instance_evidence,
)


def _write_image(path: Path, width: int = 20, height: int = 16) -> np.ndarray:
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    pixels[:, :, 0] = np.arange(width, dtype=np.uint8)
    pixels[:, :, 1] = np.arange(height, dtype=np.uint8)[:, None]
    pixels[:, :, 2] = 77
    Image.fromarray(pixels, mode="RGB").save(path)
    return pixels


def test_isolated_instance_preserves_canvas_inside_and_gray_outside(tmp_path):
    image_path = tmp_path / "source.png"
    source = _write_image(image_path)
    mask = np.zeros(source.shape[:2], dtype=bool)
    mask[4:12, 6:15] = True

    evidence = np.asarray(build_isolated_instance_evidence(image_path, mask))

    assert evidence.shape == source.shape
    assert np.array_equal(evidence[mask], source[mask])
    assert np.all(evidence[~mask] == (128, 128, 128))


def test_evidence_rejects_mask_with_wrong_shape(tmp_path):
    image_path = tmp_path / "source.png"
    _write_image(image_path)
    wrong_mask = np.zeros((3, 4), dtype=bool)

    try:
        build_isolated_instance_evidence(image_path, wrong_mask)
    except ValueError as error:
        assert "mask" in str(error)
    else:
        raise AssertionError("尺寸错误的 mask 必须失败")


def test_behavior_evidence_uses_fixed_margin_clamp_and_red_contour(tmp_path):
    image_path = tmp_path / "source.png"
    source = _write_image(image_path)
    mask = np.zeros(source.shape[:2], dtype=bool)
    mask[4:12, 6:15] = True
    bbox = [6, 4, 15, 12]

    evidence = np.asarray(build_behavior_evidence(image_path, bbox, mask))

    assert BEHAVIOR_MARGIN == 0.35
    # floor(6-3.15), floor(4-2.8), ceil(15+3.15), ceil(12+2.8)
    assert evidence.shape[:2] == (14, 17)
    red = np.all(evidence == (255, 0, 0), axis=2)
    assert red.any()

    boundary_mask = np.zeros(source.shape[:2], dtype=bool)
    boundary_mask[0:4, 0:5] = True
    boundary = np.asarray(
        build_behavior_evidence(image_path, [0, 0, 5, 4], boundary_mask)
    )
    # 左上必须 clamp 为 0；右=ceil(5+1.75)=7，下=ceil(4+1.4)=6。
    assert boundary.shape[:2] == (6, 7)
