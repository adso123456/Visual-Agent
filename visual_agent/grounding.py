from pathlib import Path

import torch
from PIL import Image
from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor


MODEL_NAME = "IDEA-Research/grounding-dino-tiny"


class GroundingDetector:
    def __init__(self) -> None:
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.processor = AutoProcessor.from_pretrained(MODEL_NAME)
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(
            MODEL_NAME, dtype=dtype
        ).to(self.device)
        self.model.eval()

    def detect(self, image_path: Path, target_text: str, threshold: float = 0.3) -> list[dict]:
        image = Image.open(image_path).convert("RGB")
        text = target_text.strip().rstrip(".") + "."
        inputs = self.processor(images=image, text=text, return_tensors="pt").to(self.device)

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
        for box, score in zip(results["boxes"], results["scores"]):
            detections.append(
                {
                    "bbox": [round(value, 2) for value in box.tolist()],
                    "confidence": round(float(score), 4),
                }
            )
        return detections
