import time
from pathlib import Path

import torch
from PIL import Image
from transformers import Sam2Model, Sam2Processor


MODEL_NAME = "facebook/sam2.1-hiera-base-plus"


class Sam2Segmenter:
    def __init__(self) -> None:
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cuda":
            torch.cuda.reset_peak_memory_stats()
        started_at = time.perf_counter()
        self.processor = Sam2Processor.from_pretrained(MODEL_NAME)
        self.model = Sam2Model.from_pretrained(MODEL_NAME).to(self.device)
        self.model.eval()
        if self.device == "cuda":
            torch.cuda.synchronize()
        self.load_seconds = time.perf_counter() - started_at
        self.memory_after_load_mb = self._memory_allocated_mb()

    def segment(self, image_path: Path, boxes: list[list[float]]) -> tuple[list[dict], dict]:
        image = Image.open(image_path).convert("RGB")
        inputs = self.processor(
            images=image,
            input_boxes=[[box for box in boxes]],
            return_tensors="pt",
        ).to(self.device)

        if self.device == "cuda":
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
        started_at = time.perf_counter()
        with torch.inference_mode():
            outputs = self.model(**inputs, multimask_output=False)
        if self.device == "cuda":
            torch.cuda.synchronize()
        inference_seconds = time.perf_counter() - started_at

        processed_masks = self.processor.post_process_masks(
            outputs.pred_masks.cpu(),
            inputs["original_sizes"].cpu(),
        )[0]
        scores = outputs.iou_scores.detach().cpu()[0]
        if len(processed_masks) != len(boxes) or len(scores) != len(boxes):
            raise RuntimeError(
                "SAM2 输出数量与 verified targets 不一致："
                f"masks={tuple(processed_masks.shape)}, scores={tuple(scores.shape)}, targets={len(boxes)}"
            )

        results = []
        for mask, score in zip(processed_masks, scores):
            binary_mask = mask.squeeze().numpy().astype(bool)
            if binary_mask.shape != (image.height, image.width):
                raise RuntimeError(
                    f"SAM2 mask 尺寸错误：{binary_mask.shape}，原图尺寸：{(image.height, image.width)}"
                )
            results.append(
                {
                    "mask": binary_mask,
                    "score": float(score.squeeze().item()),
                }
            )

        metrics = {
            "model": MODEL_NAME,
            "device": self.device,
            "load_seconds": round(self.load_seconds, 3),
            "inference_seconds": round(inference_seconds, 3),
            "memory_after_load_mb": round(self.memory_after_load_mb, 1),
            "peak_memory_mb": round(self._peak_memory_allocated_mb(), 1),
        }
        return results, metrics

    def _memory_allocated_mb(self) -> float:
        if self.device != "cuda":
            return 0.0
        return torch.cuda.memory_allocated() / 1024**2

    def _peak_memory_allocated_mb(self) -> float:
        if self.device != "cuda":
            return 0.0
        return torch.cuda.max_memory_allocated() / 1024**2
