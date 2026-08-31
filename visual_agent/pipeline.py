import json
import time
from pathlib import Path

import numpy as np

from visual_agent.planner_client import get_planner_model_name
from visual_agent.deepseek_agent import TOOL_NAME, DeepSeekAgent
from visual_agent.evidence import (
    build_behavior_evidence,
    build_isolated_instance_evidence,
)
from visual_agent.grounding import MODEL_NAME as DETECTOR_MODEL_NAME
from visual_agent.models import get_detector, get_segmenter
from visual_agent.qwen_protocol import skipped_protocol_metadata
from visual_agent.relations import verify_focused_ownership, verify_relations
from visual_agent.renderer import save_results
from visual_agent.vlm import (
    verify_candidate_constraints,
    verify_subject_instance,
)


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
    incomplete = public_visual_result.get("incomplete_semantic_groups", [])
    if incomplete:
        details = "；".join(
            f"{item.get('label', '目标')}:{item.get('completion_reason', '关联对象不完整')}"
            for item in incomplete
        )
        return f"已找到主体候选，但关系语义不完整（{details}），未执行图片操作。"
    return "未找到满足条件的目标。"


def _relation_evidence(bindings: list[dict], fallback: str) -> str:
    evidence = "；".join(
        item["evidence"].strip()
        for item in bindings
        if isinstance(item.get("evidence"), str) and item["evidence"].strip()
    )
    return evidence or fallback


def resolve_relation_outcomes(
    subjects: list[dict],
    related_candidates: list[dict],
    relation_bindings: list[dict],
    plan: dict,
) -> dict[str, dict]:
    """为每个主体只计算一次关系三态、证据与 semantic group。"""
    related_plan = plan["related_objects"]
    if not related_plan:
        raise ValueError("relation resolver 需要 related_objects")
    relation = related_plan[0]["relation"]
    related_object = related_plan[0]["object"]

    satisfied = [item for item in relation_bindings if item["status"] == "satisfied"]
    subject_counts = {
        subject["id"]: sum(item["subject_id"] == subject["id"] for item in satisfied)
        for subject in subjects
    }
    related_counts = {
        related["id"]: sum(item["related_id"] == related["id"] for item in satisfied)
        for related in related_candidates
    }
    conflict_subjects = {
        item["subject_id"]
        for item in satisfied
        if subject_counts[item["subject_id"]] > 1
        or related_counts[item["related_id"]] > 1
    }
    related_by_id = {item["id"]: item for item in related_candidates}
    outcomes = {}
    for subject in subjects:
        subject_id = subject["id"]
        subject_bindings = [
            item for item in relation_bindings if item["subject_id"] == subject_id
        ]
        subject_satisfied = [
            item for item in subject_bindings if item["status"] == "satisfied"
        ]
        related_member = None
        composite_bbox = None
        if not related_candidates:
            status = "uncertain"
            completion_reason = "related_object_not_detected"
            evidence = f"未检测到关联对象 {related_object}，无法确认 {relation}。"
        elif subject_id in conflict_subjects:
            status = "uncertain"
            completion_reason = "binding_conflict"
            evidence = _relation_evidence(
                subject_satisfied,
                "存在多个相互冲突的明确关系绑定，无法唯一归属。",
            )
        elif len(subject_satisfied) == 1:
            binding = subject_satisfied[0]
            related = related_by_id[binding["related_id"]]
            status = "satisfied"
            completion_reason = None
            evidence = binding["evidence"]
            related_member = {
                "candidate_id": related["id"],
                "object": related_object,
                "relation": relation,
                "bbox": related["bbox"],
            }
            composite_bbox = _union_bbox([subject["bbox"], related["bbox"]])
        elif any(item["status"] == "uncertain" for item in subject_bindings):
            status = "uncertain"
            completion_reason = "binding_uncertain"
            evidence = _relation_evidence(
                [item for item in subject_bindings if item["status"] == "uncertain"],
                "关系证据不足，无法可靠确认归属。",
            )
        else:
            status = "not_satisfied"
            completion_reason = "binding_not_satisfied"
            evidence = _relation_evidence(
                subject_bindings,
                "所有关联对象候选均明确不满足关系。",
            )

        related_members = [related_member] if related_member is not None else []
        group = {
            "id": subject_id,
            "label": plan["label"],
            "subject": {
                "candidate_id": subject_id,
                "object": plan["target_object"],
                "bbox": subject["bbox"],
            },
            "related_members": related_members,
            "composite_bbox": composite_bbox,
            "composite_complete": status == "satisfied",
            "completion_reason": completion_reason,
        }
        outcomes[subject_id] = {
            "status": status,
            "evidence": evidence,
            "completion_reason": completion_reason,
            "related_member": related_member,
            "group": group,
        }
    return outcomes


def _build_semantic_groups(
    verified_subjects: list[dict],
    related_candidates: list[dict],
    relation_bindings: list[dict],
    plan: dict,
) -> list[dict]:
    """兼容现有测试；Production main path 对关系只调用一次 shared resolver。"""
    if not plan["related_objects"]:
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
    outcomes = resolve_relation_outcomes(
        verified_subjects,
        related_candidates,
        relation_bindings,
        plan,
    )
    return [outcomes[subject["id"]]["group"] for subject in verified_subjects]


def _merge_sam_metrics(
    current: dict | None,
    new: dict,
    *,
    cached: bool,
) -> dict:
    normalized = dict(new)
    normalized["cached"] = cached
    if cached:
        normalized["load_seconds"] = 0.0
    normalized["batch_calls"] = 1
    if current is None:
        return normalized
    merged = dict(current)
    merged["inference_seconds"] = round(
        current.get("inference_seconds", 0.0)
        + normalized.get("inference_seconds", 0.0),
        3,
    )
    merged["peak_memory_mb"] = max(
        current.get("peak_memory_mb", 0.0),
        normalized.get("peak_memory_mb", 0.0),
    )
    merged["batch_calls"] = current.get("batch_calls", 1) + 1
    return merged


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
    """端到端执行视觉任务；verify=False 仅为本地调试语义旁路。"""
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

    plan = DeepSeekAgent._validated_plan_arguments(plan)

    constraints = plan["constraints"]
    relation_constraints = [
        (index, item)
        for index, item in enumerate(constraints)
        if item["route"] == "relation"
    ]
    routed_constraints = {
        route: [
            (index, item)
            for index, item in enumerate(constraints)
            if item["route"] == route
        ]
        for route in ("attribute", "behavior")
    }

    detector, detector_cached = get_detector(fresh=fresh_models)
    started_at = time.perf_counter()
    detections = detector.detect(image_path, plan["target_object"])
    grounding_seconds = time.perf_counter() - started_at
    runtime_candidates = []
    for index, detection in enumerate(detections):
        candidate_id = chr(ord("A") + index) if index < 26 else str(index + 1)
        runtime_candidates.append(
            {
                "id": candidate_id,
                "text_label": detection["text_label"],
                "bbox": detection["bbox"],
                "dino_confidence": detection["confidence"],
                "mask": None,
                "mask_score": None,
                "subject_validity": None,
                "checks_by_index": [None] * len(constraints),
                "non_relation_passed": False,
                "relation_eligible": False,
                "final_verified": False,
            }
        )

    mask_cache: dict[tuple[str, str], dict] = {}
    segmenter = None
    sam_metrics = None
    segmenter_is_warm = False

    def ensure_masks(component_specs: list[dict]) -> None:
        nonlocal segmenter, sam_metrics, segmenter_is_warm
        missing = [
            component
            for component in component_specs
            if (component["role"], component["candidate_id"]) not in mask_cache
        ]
        if not missing:
            return
        if segmenter is None:
            segmenter, cached = get_segmenter(fresh=fresh_models)
            segmenter_is_warm = cached
        else:
            cached = True
        segmentations, metrics = segmenter.segment(
            image_path,
            [component["bbox"] for component in missing],
        )
        sam_metrics = _merge_sam_metrics(sam_metrics, metrics, cached=cached)
        segmenter_is_warm = True
        for component, segmentation in zip(missing, segmentations):
            mask_cache[(component["role"], component["candidate_id"])] = segmentation

    validity_protocols = {}
    routed_protocols = {}
    validity_seconds = 0.0
    route_seconds = {"attribute": 0.0, "behavior": 0.0}
    verification_started_at = time.perf_counter()

    if constraints and runtime_candidates and verify:
        ensure_masks(
            [
                {
                    "role": "subject",
                    "candidate_id": candidate["id"],
                    "bbox": candidate["bbox"],
                }
                for candidate in runtime_candidates
            ]
        )
        for candidate in runtime_candidates:
            segmentation = mask_cache[("subject", candidate["id"])]
            candidate["mask"] = segmentation["mask"]
            candidate["mask_score"] = segmentation["score"]
            isolated = build_isolated_instance_evidence(
                image_path,
                candidate["mask"],
            )
            started_at = time.perf_counter()
            validity, protocol = verify_subject_instance(
                {"id": candidate["id"], "bbox": candidate["bbox"]},
                plan["target_object"],
                isolated,
            )
            validity_seconds += time.perf_counter() - started_at
            validity_protocols[candidate["id"]] = protocol
            candidate["subject_validity"] = validity
            if validity["status"] != "valid":
                propagated_status = (
                    "not_satisfied"
                    if validity["status"] == "invalid"
                    else "uncertain"
                )
                for index, constraint in enumerate(constraints):
                    candidate["checks_by_index"][index] = {
                        "constraint": constraint["text"],
                        "status": propagated_status,
                        "evidence": (
                            f"候选基础实例状态为 {validity['status']}："
                            f"{validity['evidence']}；未执行该语义验证。"
                        ),
                    }
                continue

            routed_protocols[candidate["id"]] = {}
            for route in ("attribute", "behavior"):
                indexed_constraints = routed_constraints[route]
                if not indexed_constraints:
                    continue
                route_items = [item for _, item in indexed_constraints]
                evidence = (
                    isolated
                    if route == "attribute"
                    else build_behavior_evidence(
                        image_path,
                        candidate["bbox"],
                        candidate["mask"],
                    )
                )
                started_at = time.perf_counter()
                checks, protocol = verify_candidate_constraints(
                    {"id": candidate["id"], "bbox": candidate["bbox"]},
                    route_items,
                    evidence,
                    route,
                )
                route_seconds[route] += time.perf_counter() - started_at
                routed_protocols[candidate["id"]][route] = protocol
                for (index, _), check in zip(indexed_constraints, checks):
                    candidate["checks_by_index"][index] = check

            non_relation_checks = [
                candidate["checks_by_index"][index]
                for route in ("attribute", "behavior")
                for index, _ in routed_constraints[route]
            ]
            candidate["non_relation_passed"] = all(
                check["status"] == "satisfied" for check in non_relation_checks
            )
            candidate["relation_eligible"] = bool(relation_constraints) and candidate[
                "non_relation_passed"
            ]
    elif not verify:
        for candidate in runtime_candidates:
            candidate["non_relation_passed"] = True
            candidate["relation_eligible"] = bool(relation_constraints)
    else:
        for candidate in runtime_candidates:
            candidate["non_relation_passed"] = True

    verification_seconds = time.perf_counter() - verification_started_at

    relation_candidates = []
    relation_bindings = []
    relation_outcomes = {}
    relation_grounding_seconds = 0.0
    relation_verification_seconds = 0.0
    relation_protocol = skipped_protocol_metadata()
    relation_eligible = [
        candidate
        for candidate in runtime_candidates
        if candidate["relation_eligible"]
    ]
    if relation_constraints and verify:
        for candidate in runtime_candidates:
            if (
                candidate["subject_validity"]
                and candidate["subject_validity"]["status"] == "valid"
                and not candidate["relation_eligible"]
            ):
                index, constraint = relation_constraints[0]
                candidate["checks_by_index"][index] = {
                    "constraint": constraint["text"],
                    "status": "uncertain",
                    "evidence": "非关系约束未全部满足，未执行关系验证。",
                }
        if relation_eligible:
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
            relation_subjects = [
                {
                    "id": candidate["id"],
                    "label": plan["label"],
                    "text_label": candidate["text_label"],
                    "bbox": candidate["bbox"],
                    "confidence": candidate["dino_confidence"],
                }
                for candidate in relation_eligible
            ]
            if relation_candidates:
                started_at = time.perf_counter()
                relation_protocols = []
                for relation_subject in relation_subjects:
                    subject_bindings, subject_protocol = verify_relations(
                        image_path,
                        [relation_subject],
                        relation_candidates,
                        related_plan["object"],
                        related_plan["relation"],
                    )
                    relation_bindings.extend(subject_bindings)
                    relation_protocols.append(subject_protocol)

                # many-to-one satisfied conflict：按 related object 触发 focused ownership
                conflict_subjects_by_related: dict[str, set[str]] = {}
                for binding in relation_bindings:
                    if binding["status"] == "satisfied":
                        conflict_subjects_by_related.setdefault(
                            binding["related_id"], set()
                        ).add(binding["subject_id"])
                related_by_id = {
                    item["id"]: item for item in relation_candidates
                }
                for related_id, subject_ids in conflict_subjects_by_related.items():
                    if len(subject_ids) <= 1:
                        continue
                    conflict_subjects = [
                        subject
                        for subject in relation_subjects
                        if subject["id"] in subject_ids
                    ]
                    if len(conflict_subjects) != len(subject_ids):
                        raise RuntimeError(
                            "Focused conflict subjects 与 relation bindings 不一致"
                        )
                    focused_bindings, focused_protocol = verify_focused_ownership(
                        image_path,
                        conflict_subjects,
                        [related_by_id[related_id]],
                        related_plan["object"],
                        related_plan["relation"],
                    )
                    relation_protocols.append(focused_protocol)
                    focused_by_pair = {
                        (binding["subject_id"], binding["related_id"]): binding
                        for binding in focused_bindings
                    }
                    relation_bindings = [
                        focused_by_pair[
                            (binding["subject_id"], binding["related_id"])
                        ]
                        if (
                            binding["related_id"] == related_id
                            and binding["subject_id"] in subject_ids
                        )
                        else binding
                        for binding in relation_bindings
                    ]

                relation_protocol = {
                    "attempts": sum(item.get("attempts", 0) for item in relation_protocols),
                    "retry_count": sum(item.get("retry_count", 0) for item in relation_protocols),
                    "recovered": any(item.get("recovered", False) for item in relation_protocols),
                    "first_error_code": next(
                        (
                            item.get("first_error_code")
                            for item in relation_protocols
                            if item.get("first_error_code") is not None
                        ),
                        None,
                    ),
                }
                relation_verification_seconds = time.perf_counter() - started_at
            relation_outcomes = resolve_relation_outcomes(
                relation_subjects,
                relation_candidates,
                relation_bindings,
                plan,
            )
            relation_index, relation_constraint = relation_constraints[0]
            for candidate in relation_eligible:
                outcome = relation_outcomes[candidate["id"]]
                candidate["checks_by_index"][relation_index] = {
                    "constraint": relation_constraint["text"],
                    "status": outcome["status"],
                    "evidence": outcome["evidence"],
                }

    final_subjects = []
    if verify:
        for candidate in runtime_candidates:
            checks = candidate["checks_by_index"]
            candidate["final_verified"] = (
                all(check is not None and check["status"] == "satisfied" for check in checks)
                if constraints
                else True
            )
            if candidate["final_verified"]:
                reason = "；".join(check["evidence"] for check in checks)
                final_subjects.append(
                    {
                        "id": candidate["id"],
                        "label": plan["label"],
                        "text_label": candidate["text_label"],
                        "bbox": candidate["bbox"],
                        "confidence": candidate["dino_confidence"],
                        "reason": reason,
                    }
                )
    elif not plan["related_objects"]:
        for candidate in runtime_candidates:
            candidate["final_verified"] = True
            final_subjects.append(
                {
                    "id": candidate["id"],
                    "label": plan["label"],
                    "text_label": candidate["text_label"],
                    "bbox": candidate["bbox"],
                    "confidence": candidate["dino_confidence"],
                    "reason": "",
                }
            )

    if plan["related_objects"]:
        if verify:
            semantic_groups = [
                relation_outcomes[candidate["id"]]["group"]
                for candidate in relation_eligible
            ]
        else:
            debug_subjects = [
                {
                    "id": candidate["id"],
                    "bbox": candidate["bbox"],
                }
                for candidate in runtime_candidates
            ]
            semantic_groups = _build_semantic_groups(
                debug_subjects,
                [],
                [],
                plan,
            )
    else:
        semantic_groups = _build_semantic_groups(
            final_subjects,
            [],
            [],
            plan,
        )

    subjects_by_id = {subject["id"]: subject for subject in final_subjects}
    targets = []
    for group in semantic_groups:
        if not group["composite_complete"] or group["id"] not in subjects_by_id:
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

    if targets and plan["action"]["type"] != "box":
        component_specs_by_key = {}
        for target in targets:
            for component in target["_component_specs"]:
                key = (component["role"], component["candidate_id"])
                component_specs_by_key.setdefault(key, component)
        ensure_masks(list(component_specs_by_key.values()))
        for target in targets:
            component_masks = []
            components = []
            for component in target.pop("_component_specs"):
                key = (component["role"], component["candidate_id"])
                segmentation = mask_cache[key]
                component_masks.append(segmentation["mask"])
                component_data = {
                    item_key: value
                    for item_key, value in component.items()
                    if item_key != "bbox"
                }
                component_data["mask_score"] = round(segmentation["score"], 4)
                component_data["mask_area_pixels"] = int(
                    segmentation["mask"].sum()
                )
                components.append(component_data)
            target["components"] = components
            target["_mask"] = np.logical_or.reduce(component_masks)
            target["_mask_score"] = min(
                mask_cache[(item["role"], item["candidate_id"])]["score"]
                for item in components
            )

    final_ids = {subject["id"] for subject in final_subjects}
    candidates = []
    for candidate in runtime_candidates:
        checks = [
            check for check in candidate["checks_by_index"] if check is not None
        ]
        candidates.append(
            {
                "id": candidate["id"],
                "text_label": candidate["text_label"],
                "bbox": candidate["bbox"],
                "dino_confidence": candidate["dino_confidence"],
                "verification_checks": checks,
                "verified": candidate["id"] in final_ids,
                "verification_reason": "；".join(
                    check["evidence"] for check in checks
                ),
            }
        )

    result = {
        "prompt": prompt,
        "agent": {
            "provider": (
                "deepseek"
                if agent is not None and agent.is_deepseek
                else "local_ollama"
                if agent is not None
                else "skipped"
            ),
            "model": (
                agent.config.model if agent is not None else get_planner_model_name()
            ),
            "planner_tool": TOOL_NAME,
            "plan_attempts": agent.plan_attempts if agent is not None else 0,
        },
        "plan": plan,
        "candidates": candidates,
        "verified_subjects": final_subjects,
        "relation_candidates": relation_candidates,
        "relation_bindings": relation_bindings,
        "semantic_groups": semantic_groups,
        "targets": targets,
        "qwen_protocol": {
            "subject_validity": validity_protocols or skipped_protocol_metadata(),
            "candidate_verification": routed_protocols
            or skipped_protocol_metadata(),
            "relation_verification": relation_protocol,
        },
        "timings": {
            "deepseek_plan_seconds": round(plan_seconds, 3),
            "detector": {
                "model": DETECTOR_MODEL_NAME,
                "device": detector.device,
                "load_seconds": round(detector.load_seconds, 3)
                if not detector_cached
                else 0.0,
                "cached": detector_cached,
                "memory_after_load_mb": round(detector.memory_after_load_mb, 1),
            },
            "grounding_dino_seconds": round(grounding_seconds, 3),
            "subject_validity_seconds": round(validity_seconds, 3),
            "attribute_verification_seconds": round(
                route_seconds["attribute"], 3
            ),
            "behavior_verification_seconds": round(route_seconds["behavior"], 3),
            "group_verification_seconds": round(verification_seconds, 3),
            "relation_grounding_seconds": round(relation_grounding_seconds, 3),
            "relation_verification_seconds": round(
                relation_verification_seconds, 3
            ),
            "sam2": sam_metrics,
        },
    }
    image_output, json_output = save_results(
        image_path,
        result,
        output_dir if output_dir is not None else Path("images/output_images"),
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
        "execution_success": bool(saved_result["targets"])
        and image_output.is_file(),
    }
    if final_response:
        started_at = time.perf_counter()
        saved_result["agent_response"] = agent.build_final_response(
            prompt,
            public_visual_result,
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
