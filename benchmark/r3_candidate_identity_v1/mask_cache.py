"""固定 SAM mask cache；真实 segmenter 必须由未来获批的执行脚本注入。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image


Segmenter = Callable[[Path, list[list[float]]], list[np.ndarray]]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MaskCache:
    def __init__(self, root: Path):
        self.root = root

    def build(
        self,
        *,
        case_id: str,
        image_path: Path,
        image_sha256: str,
        candidates: list[dict[str, object]],
        segmenter: Segmenter,
    ) -> Path:
        actual_image_sha = _sha256(image_path.read_bytes())
        if actual_image_sha != image_sha256:
            raise ValueError("输入图片 SHA-256 与冻结 selection 不一致")

        cache_dir = self.root / image_sha256
        manifest_path = cache_dir / "manifest.json"
        if manifest_path.exists():
            self.load(
                image_path=image_path,
                image_sha256=image_sha256,
                candidates=candidates,
            )
            return manifest_path

        with Image.open(image_path) as image:
            width, height = image.size
        bboxes = [list(candidate["bbox"]) for candidate in candidates]
        masks = segmenter(image_path, bboxes)
        if len(masks) != len(candidates):
            raise ValueError("segmenter 返回的 mask 数量与 candidate 数量不一致")

        normalized_masks = []
        for raw_mask in masks:
            mask = np.asarray(raw_mask, dtype=bool)
            if mask.shape != (height, width):
                raise ValueError("segmenter 返回的 mask 尺寸与原图不一致")
            normalized_masks.append(mask)

        cache_dir.mkdir(parents=True, exist_ok=False)
        records = []
        for candidate, mask in zip(candidates, normalized_masks, strict=True):
            packed = np.packbits(mask.reshape(-1), bitorder="little").tobytes()
            mask_path = cache_dir / f"candidate_{candidate['id']}.bin"
            mask_path.write_bytes(packed)
            records.append(
                {
                    "candidate_id": candidate["id"],
                    "bbox": candidate["bbox"],
                    "path": mask_path.name,
                    "sha256": _sha256(packed),
                    "bytes": len(packed),
                    "true_pixels": int(mask.sum()),
                }
            )
        payload = {
            "schema_version": "R3_FIXED_MASK_CACHE_V1",
            "case_id": case_id,
            "image_sha256": image_sha256,
            "width": width,
            "height": height,
            "bitorder": "little",
            "masks": records,
        }
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest_path

    def load(
        self,
        *,
        image_path: Path,
        image_sha256: str,
        candidates: list[dict[str, object]],
    ) -> dict[str, np.ndarray]:
        cache_dir = self.root / image_sha256
        payload = json.loads((cache_dir / "manifest.json").read_text(encoding="utf-8"))
        if _sha256(image_path.read_bytes()) != image_sha256:
            raise ValueError("输入图片 SHA-256 与冻结 selection 不一致")
        with Image.open(image_path) as image:
            width, height = image.size
        if (payload["image_sha256"], payload["width"], payload["height"]) != (
            image_sha256,
            width,
            height,
        ):
            raise ValueError("mask cache manifest 与输入图片不一致")

        expected = {str(row["id"]): list(row["bbox"]) for row in candidates}
        cached = {
            str(row["candidate_id"]): list(row["bbox"])
            for row in payload["masks"]
        }
        if cached != expected:
            raise ValueError("mask cache candidate/bbox 与冻结 selection 不一致")

        result: dict[str, np.ndarray] = {}
        count = width * height
        for record in payload["masks"]:
            data = (cache_dir / record["path"]).read_bytes()
            if _sha256(data) != record["sha256"] or len(data) != record["bytes"]:
                raise ValueError("mask cache SHA-256/字节数校验失败")
            mask = np.unpackbits(
                np.frombuffer(data, dtype=np.uint8), bitorder="little"
            )[:count].reshape((height, width)).astype(bool)
            if int(mask.sum()) != record["true_pixels"]:
                raise ValueError("mask cache true_pixels 校验失败")
            result[str(record["candidate_id"])] = mask
        return result
