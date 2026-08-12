from pathlib import Path

import torch
from PIL import Image
from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor


MODEL_NAME = "IDEA-Research/grounding-dino-base"


class GroundingDetector:
    def __init__(self) -> None:
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.processor = AutoProcessor.from_pretrained(MODEL_NAME)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(
            MODEL_NAME, dtype=torch.float32
        ).to(self.device)
        self.model.eval()

    def detect(self, image_path: Path, target_text: str, threshold: float = 0.3) -> list[dict]:
        image = Image.open(image_path).convert("RGB")
        text = target_text.strip().rstrip(".") + "."
        inputs = self.processor(images=image, text=text, return_tensors="pt").to(self.device)
        inputs["pixel_values"] = inputs["pixel_values"].to(
            dtype=next(self.model.parameters()).dtype
        )

        with torch.inference_mode():
            outputs = self.model(**inputs)

        results = self.processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            threshold=threshold,
            text_threshold=threshold,
            target_sizes=[image.size[::-1]],
        )[0]
        detections = []
        for box, score, text_label in zip(
            results["boxes"], results["scores"], results["text_labels"]
        ):
            detections.append(
                {
                    "bbox": [round(value, 2) for value in box.tolist()],
                    "confidence": round(float(score), 4),
                    "text_label": text_label,
                }
            )
        return detections
