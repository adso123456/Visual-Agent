import json
import time
from pathlib import Path

import numpy as np

from visual_agent.deepseek_agent import MODEL_NAME, TOOL_NAME, DeepSeekAgent
from visual_agent.grounding import MODEL_NAME as DETECTOR_MODEL_NAME
from visual_agent.models import get_detector, get_segmenter
from visual_agent.relations import verify_relations
from visual_agent.renderer import save_results
from visual_agent.vlm import verify_candidates
from visual_agent.qwen_protocol import skipped_protocol_metadata


ACTION_LABELS = {
    "highlight": "高亮标注",
    "outline": "描边",
    "box": "矩形框选",
    "blur_target": "模糊",
    "dim_background": "背景变暗",
    "cutout": "抠图",
}


def _union_bbox(boxes: list[list[float]]) -> list[float]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def _local_summary(public_visual_result: dict) -> str:
    """确定性本地汇总：不调用 DeepSeek，不声称结果中没有的视觉事实。"""
    action = public_visual_result.get("action", {}).get("type", "highlight")
    action_label = ACTION_LABELS.get(action, action)
    target_count = public_visual_result.get("complete_semantic_targets_count", 0)
    if target_count > 0:
        return f"已在图片中找到 {target_count} 个满足条件的目标，并完成{action_label}。"
    verified_count = public_visual_result.get("verified_subjects_count", 0)
    if verified_count > 0:
        details = "；".join(
            f"{item.get('label', '目标')}:{item.get('completion_reason', '关联对象不完整')}"
            for item in public_visual_result.get("incomplete_semantic_groups", [])
        )
        return (
            f"已找到 {verified_count} 个主体候选，但关联对象不完整（{details}），"
            "未执行图片操作。"
        )
    return "未找到满足条件的目标。"


def _build_semantic_groups(
    verified_subjects: list[dict],
    related_candidates: list[dict],
    relation_bindings: list[dict],
    plan: dict,
) -> list[dict]:
    related_plan = plan["related_objects"]
    if not related_plan:
        return [
            {
                "id": subject["id"],
                "label": plan["label"],
                "subject": {
                    "candidate_id": subject["id"],
                    "object": plan["target_object"],
                    "bbox": subject["bbox"],
                },
                "related_members": [],
                "composite_bbox": subject["bbox"],
                "composite_complete": True,
                "completion_reason": None,
            }
            for subject in verified_subjects
        ]
    if not related_candidates:
        return [
            {
                "id": subject["id"],
                "label": plan["label"],
                "subject": {
                    "candidate_id": subject["id"],
                    "object": plan["target_object"],
                    "bbox": subject["bbox"],
                },
                "related_members": [],
                "composite_bbox": None,
                "composite_complete": False,
                "completion_reason": "related_object_not_detected",
            }
            for subject in verified_subjects
        ]

    satisfied = [item for item in relation_bindings if item["status"] == "satisfied"]
    subject_counts = {
        subject["id"]: sum(item["subject_id"] == subject["id"] for item in satisfied)
        for subject in verified_subjects
    }
    related_counts = {
        related["id"]: sum(item["related_id"] == related["id"] for item in satisfied)
        for related in related_candidates
    }
    conflict_subjects = {
        item["subject_id"]
        for item in satisfied
        if subject_counts[item["subject_id"]] > 1 or related_counts[item["related_id"]] > 1
    }
    related_by_id = {item["id"]: item for item in related_candidates}
    relation = related_plan[0]["relation"]
    related_object = related_plan[0]["object"]
    groups = []
    for subject in verified_subjects:
        subject_id = subject["id"]
        subject_bindings = [
            item for item in relation_bindings if item["subject_id"] == subject_id
        ]
        subject_satisfied = [item for item in subject_bindings if item["status"] == "satisfied"]
        related_members = []
        composite_bbox = None
        complete = False
        if subject_id in conflict_subjects:
            completion_reason = "binding_conflict"
        elif len(subject_satisfied) == 1:
            binding = subject_satisfied[0]
            related = related_by_id[binding["related_id"]]
            related_members = [
                {
                    "candidate_id": related["id"],
                    "object": related_object,
                    "relation": relation,
                    "bbox": related["bbox"],
                }
            ]
            composite_bbox = _union_bbox([subject["bbox"], related["bbox"]])
            complete = True
            completion_reason = None
        elif any(item["status"] == "uncertain" for item in subject_bindings):
            completion_reason = "binding_uncertain"
        else:
            completion_reason = "binding_not_satisfied"
        groups.append(
            {
                "id": subject_id,
                "label": plan["label"],
                "subject": {
                    "candidate_id": subject_id,
                    "object": plan["target_object"],
                    "bbox": subject["bbox"],
                },
                "related_members": related_members,
                "composite_bbox": composite_bbox,
                "composite_complete": complete,
                "completion_reason": completion_reason,
            }
        )
    return groups


def run_pipeline(
    image_path: Path,
    prompt: str,
    *,
    plan: dict | None = None,
    verify: bool = True,
    final_response: bool = True,
    fresh_models: bool = False,
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    """端到端执行视觉任务。

    - plan：预编译的计划 dict（含 target_object/label/constraints/action/related_objects）。
      传 None 时调用 DeepSeek Planner。传入后可完全跳过 Planner（配合 final_response=False
      实现无 API 的本地延迟测量）。
    - verify：是否调用 Qwen3-VL 做候选/关系验证。False 时所有候选视为已验证
      （仅用于延迟测量/CI，会改变结果语义，生产必须为 True）。
    - final_response：是否调用 DeepSeek 生成最终回答。False 时使用确定性本地模板。
    - fresh_models：True 时强制重新加载 DINO/SAM2（冷启动测量）。
    - output_dir：结果输出目录，默认 images/output_images。
    """
    image_path = image_path.resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"图片不存在：{image_path}")
    total_started_at = time.perf_counter()

    agent = DeepSeekAgent() if (plan is None or final_response) else None
    if plan is None:
        started_at = time.perf_counter()
        plan = agent.plan_request(prompt)
        plan_seconds = time.perf_counter() - started_at
    else:
        plan_seconds = 0.0

    detector, detector_cached = get_detector(fresh=fresh_models)
    started_at = time.perf_counter()
    detections = detector.detect(image_path, plan["target_object"])
    grounding_seconds = time.perf_counter() - started_at
    candidate_inputs = [
        {
            "id": chr(ord("A") + index) if index < 26 else str(index + 1),
            "bbox": detection["bbox"],
        }
        for index, detection in enumerate(detections)
    ]
    started_at = time.perf_counter()
    candidate_protocol = skipped_protocol_metadata()
    if plan["constraints"] and candidate_inputs and verify:
        verification_results, candidate_protocol = verify_candidates(
            image_path, prompt, plan, candidate_inputs
        )
        checks_by_id = {item["id"]: item["checks"] for item in verification_results}
    else:
        checks_by_id = {candidate["id"]: [] for candidate in candidate_inputs}
    verification_seconds = time.perf_counter() - started_at

    candidates = []
    verified_subjects = []
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
            verified_subjects.append(
                {
                    "id": candidate_id,
                    "label": plan["label"],
                    "text_label": detection["text_label"],
                    "bbox": detection["bbox"],
                    "confidence": detection["confidence"],
                    "reason": reason,
                }
            )

    relation_candidates = []
    relation_bindings = []
    relation_grounding_seconds = 0.0
    relation_verification_seconds = 0.0
    relation_protocol = skipped_protocol_metadata()
    if verified_subjects and plan["related_objects"] and verify:
        related_plan = plan["related_objects"][0]
        started_at = time.perf_counter()
        related_detections = detector.detect(image_path, related_plan["object"])
        relation_grounding_seconds = time.perf_counter() - started_at
        relation_candidates = [
            {
                "id": f"R{index + 1}",
                "object": related_plan["object"],
                "text_label": detection["text_label"],
                "bbox": detection["bbox"],
                "dino_confidence": detection["confidence"],
            }
            for index, detection in enumerate(related_detections)
        ]
        if relation_candidates:
            started_at = time.perf_counter()
            relation_bindings, relation_protocol = verify_relations(
                image_path,
                verified_subjects,
                relation_candidates,
                related_plan["object"],
                related_plan["relation"],
            )
            relation_verification_seconds = time.perf_counter() - started_at

    semantic_groups = _build_semantic_groups(
        verified_subjects,
        relation_candidates,
        relation_bindings,
        plan,
    )
    subjects_by_id = {subject["id"]: subject for subject in verified_subjects}
    targets = []
    for group in semantic_groups:
        if not group["composite_complete"]:
            continue
        subject = subjects_by_id[group["id"]]
        targets.append(
            {
                **subject,
                "composite_bbox": group["composite_bbox"],
                "_component_specs": [
                    {
                        "role": "subject",
                        "object": group["subject"]["object"],
                        "candidate_id": group["subject"]["candidate_id"],
                        "bbox": group["subject"]["bbox"],
                    },
                    *[
                        {"role": "related", **member}
                        for member in group["related_members"]
                    ],
                ],
            }
        )

    sam_metrics = None
    if targets and plan["action"]["type"] != "box":
        component_specs_by_key = {}
        for target in targets:
            for component in target["_component_specs"]:
                key = (component["role"], component["candidate_id"])
                component_specs_by_key.setdefault(key, component)
        component_keys = list(component_specs_by_key)
        segmenter, segmenter_cached = get_segmenter(fresh=fresh_models)
        segmentations, sam_metrics = segmenter.segment(
            image_path,
            [component_specs_by_key[key]["bbox"] for key in component_keys],
        )
        sam_metrics["cached"] = segmenter_cached
        if segmenter_cached:
            sam_metrics["load_seconds"] = 0.0
        segmentations_by_key = dict(zip(component_keys, segmentations))
        for target in targets:
            component_masks = []
            components = []
            for component in target.pop("_component_specs"):
                key = (component["role"], component["candidate_id"])
                segmentation = segmentations_by_key[key]
                component_masks.append(segmentation["mask"])
                component_data = {
                    key: value for key, value in component.items() if key != "bbox"
                }
                component_data["mask_score"] = round(segmentation["score"], 4)
                component_data["mask_area_pixels"] = int(segmentation["mask"].sum())
                components.append(component_data)
            composite_mask = np.logical_or.reduce(component_masks)
            target["components"] = components
            target["_mask"] = composite_mask
            target["_mask_score"] = min(
                segmentations_by_key[(item["role"], item["candidate_id"])]["score"]
                for item in components
            )

    result = {
        "prompt": prompt,
        "agent": {
            "provider": "deepseek",
            "model": MODEL_NAME,
            "planner_tool": TOOL_NAME,
            "plan_attempts": agent.plan_attempts if agent is not None else 0,
        },
        "plan": plan,
        "candidates": candidates,
        "verified_subjects": verified_subjects,
        "relation_candidates": relation_candidates,
        "relation_bindings": relation_bindings,
        "semantic_groups": semantic_groups,
        "targets": targets,
        "qwen_protocol": {
            "candidate_verification": candidate_protocol,
            "relation_verification": relation_protocol,
        },
        "timings": {
            "deepseek_plan_seconds": round(plan_seconds, 3),
            "detector": {
                "model": DETECTOR_MODEL_NAME,
                "device": detector.device,
                "load_seconds": round(detector.load_seconds, 3) if not detector_cached else 0.0,
                "cached": detector_cached,
                "memory_after_load_mb": round(detector.memory_after_load_mb, 1),
            },
            "grounding_dino_seconds": round(grounding_seconds, 3),
            "group_verification_seconds": round(verification_seconds, 3),
            "relation_grounding_seconds": round(relation_grounding_seconds, 3),
            "relation_verification_seconds": round(relation_verification_seconds, 3),
            "sam2": sam_metrics,
        },
    }
    image_output, json_output = save_results(
        image_path, result, output_dir if output_dir is not None else Path("images/output_images")
    )
    saved_result = json.loads(json_output.read_text(encoding="utf-8"))
    public_visual_result = {
        "plan": saved_result["plan"],
        "verified_subjects_count": len(saved_result["verified_subjects"]),
        "complete_semantic_targets_count": len(saved_result["targets"]),
        "incomplete_semantic_groups": [
            {
                "label": group["label"],
                "completion_reason": group["completion_reason"],
            }
            for group in saved_result["semantic_groups"]
            if not group["composite_complete"]
        ],
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
        "execution_success": bool(saved_result["targets"]) and image_output.is_file(),
    }
    if final_response:
        started_at = time.perf_counter()
        saved_result["agent_response"] = agent.build_final_response(
            prompt, public_visual_result
        )
        saved_result["timings"]["deepseek_final_response_seconds"] = round(
            time.perf_counter() - started_at,
            3,
        )
    else:
        saved_result["agent_response"] = _local_summary(public_visual_result)
        saved_result["timings"]["deepseek_final_response_seconds"] = 0.0
    saved_result["timings"]["total_seconds"] = round(
        time.perf_counter() - total_started_at,
        3,
    )
    json_output.write_text(
        json.dumps(saved_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return image_output, json_output
