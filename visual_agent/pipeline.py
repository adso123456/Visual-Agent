from pathlib import Path

from visual_agent.grounding import GroundingDetector
from visual_agent.renderer import save_results
from visual_agent.vlm import understand_target, verify_candidate


def run_pipeline(image_path: Path, prompt: str) -> tuple[Path, Path]:
    image_path = image_path.resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"图片不存在：{image_path}")

    plan = understand_target(image_path, prompt)
    detections = GroundingDetector().detect(image_path, plan["target_object"])

    candidates = []
    targets = []
    for candidate_id, detection in enumerate(detections, 1):
        verification = verify_candidate(image_path, prompt, plan, detection["bbox"])
        candidate = {
            "id": candidate_id,
            "text_label": detection["text_label"],
            "bbox": detection["bbox"],
            "dino_confidence": detection["confidence"],
            "verified": verification["match"],
            "verification_reason": verification["reason"],
        }
        candidates.append(candidate)
        if verification["match"]:
            targets.append(
                {
                    "label": plan["label"],
                    "text_label": detection["text_label"],
                    "bbox": detection["bbox"],
                    "confidence": detection["confidence"],
                    "reason": verification["reason"],
                }
            )

    result = {
        "prompt": prompt,
        "plan": plan,
        "candidates": candidates,
        "targets": targets,
    }
    return save_results(image_path, result, Path("images/output_images"))
