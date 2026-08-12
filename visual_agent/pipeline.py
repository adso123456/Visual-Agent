from pathlib import Path

from visual_agent.grounding import GroundingDetector
from visual_agent.renderer import save_results
from visual_agent.vlm import understand_target, verify_candidates


def run_pipeline(image_path: Path, prompt: str) -> tuple[Path, Path]:
    image_path = image_path.resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"图片不存在：{image_path}")

    plan = understand_target(image_path, prompt)
    detections = GroundingDetector().detect(image_path, plan["target_object"])
    candidate_inputs = [
        {
            "id": chr(ord("A") + index) if index < 26 else str(index + 1),
            "bbox": detection["bbox"],
        }
        for index, detection in enumerate(detections)
    ]
    if plan["constraints"] and candidate_inputs:
        verification_results = verify_candidates(image_path, prompt, plan, candidate_inputs)
        checks_by_id = {item["id"]: item["checks"] for item in verification_results}
    else:
        checks_by_id = {candidate["id"]: [] for candidate in candidate_inputs}

    candidates = []
    targets = []
    for candidate_input, detection in zip(candidate_inputs, detections):
        candidate_id = candidate_input["id"]
        checks = checks_by_id[candidate_id]
        verified = all(check["status"] == "satisfied" for check in checks)
        reason = "；".join(check["evidence"] for check in checks)
        candidate = {
            "id": candidate_id,
            "text_label": detection["text_label"],
            "bbox": detection["bbox"],
            "dino_confidence": detection["confidence"],
            "verification_checks": checks,
            "verified": verified,
            "verification_reason": reason,
        }
        candidates.append(candidate)
        if verified:
            targets.append(
                {
                    "label": plan["label"],
                    "text_label": detection["text_label"],
                    "bbox": detection["bbox"],
                    "confidence": detection["confidence"],
                    "reason": reason,
                }
            )

    result = {
        "prompt": prompt,
        "plan": plan,
        "candidates": candidates,
        "targets": targets,
    }
    return save_results(image_path, result, Path("images/output_images"))
