import json
import time
from pathlib import Path

from visual_agent.deepseek_agent import MODEL_NAME, TOOL_NAME, DeepSeekAgent
from visual_agent.grounding import GroundingDetector
from visual_agent.renderer import save_results
from visual_agent.segmentation import Sam2Segmenter
from visual_agent.vlm import verify_candidates


def run_pipeline(image_path: Path, prompt: str) -> tuple[Path, Path]:
    image_path = image_path.resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"图片不存在：{image_path}")

    agent = DeepSeekAgent()
    started_at = time.perf_counter()
    plan = agent.plan_request(prompt)
    plan_seconds = time.perf_counter() - started_at

    started_at = time.perf_counter()
    detections = GroundingDetector().detect(image_path, plan["target_object"])
    grounding_seconds = time.perf_counter() - started_at
    candidate_inputs = [
        {
            "id": chr(ord("A") + index) if index < 26 else str(index + 1),
            "bbox": detection["bbox"],
        }
        for index, detection in enumerate(detections)
    ]
    started_at = time.perf_counter()
    if plan["constraints"] and candidate_inputs:
        verification_results = verify_candidates(image_path, prompt, plan, candidate_inputs)
        checks_by_id = {item["id"]: item["checks"] for item in verification_results}
    else:
        checks_by_id = {candidate["id"]: [] for candidate in candidate_inputs}
    verification_seconds = time.perf_counter() - started_at

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
                    "id": candidate_id,
                    "label": plan["label"],
                    "text_label": detection["text_label"],
                    "bbox": detection["bbox"],
                    "confidence": detection["confidence"],
                    "reason": reason,
                }
            )

    sam_metrics = None
    if targets:
        segmenter = Sam2Segmenter()
        segmentations, sam_metrics = segmenter.segment(
            image_path,
            [target["bbox"] for target in targets],
        )
        for target, segmentation in zip(targets, segmentations):
            target["_mask"] = segmentation["mask"]
            target["_mask_score"] = segmentation["score"]

    result = {
        "prompt": prompt,
        "agent": {
            "provider": "deepseek",
            "model": MODEL_NAME,
            "planner_tool": TOOL_NAME,
            "plan_attempts": agent.plan_attempts,
        },
        "plan": plan,
        "candidates": candidates,
        "targets": targets,
        "timings": {
            "deepseek_plan_seconds": round(plan_seconds, 3),
            "grounding_dino_seconds": round(grounding_seconds, 3),
            "group_verification_seconds": round(verification_seconds, 3),
            "sam2": sam_metrics,
        },
    }
    image_output, json_output = save_results(image_path, result, Path("images/output_images"))
    saved_result = json.loads(json_output.read_text(encoding="utf-8"))
    public_visual_result = {
        "plan": saved_result["plan"],
        "targets_count": len(saved_result["targets"]),
        "targets": [
            {
                "label": target["label"],
                "verification_reason": target["reason"],
                "verification_checks": next(
                    candidate["verification_checks"]
                    for candidate in saved_result["candidates"]
                    if candidate["id"] == target["id"]
                ),
            }
            for target in saved_result["targets"]
        ],
        "action": saved_result["plan"]["action"],
        "execution_success": image_output.is_file(),
    }
    started_at = time.perf_counter()
    saved_result["agent_response"] = agent.build_final_response(prompt, public_visual_result)
    saved_result["timings"]["deepseek_final_response_seconds"] = round(
        time.perf_counter() - started_at,
        3,
    )
    json_output.write_text(
        json.dumps(saved_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return image_output, json_output
