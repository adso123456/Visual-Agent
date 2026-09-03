import json
import math
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

from visual_agent.deepseek_agent import MODEL_NAME, TOOL_NAME, DeepSeekAgent
from visual_agent.evidence import (
    build_behavior_evidence,
    build_candidate_marked_full_scene_evidence,
    build_isolated_instance_evidence,
    build_subject_conditioned_grounding_view,
    build_target_anchored_behavior_evidence,
    build_target_anchored_full_scene_evidence,
    identity_contamination_risk,
)
from visual_agent.grounding import MODEL_NAME as DETECTOR_MODEL_NAME
from visual_agent.models import get_detector, get_segmenter
from visual_agent.qwen_protocol import skipped_protocol_metadata
from visual_agent.relations import verify_focused_ownership, verify_relations
from visual_agent.renderer import save_results
from visual_agent.transport import merge_transport_telemetry
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


OBJECT_MEDIATED_BEHAVIOR_MARKER = "正在钓鱼"
HAND_CONDITIONED_THRESHOLD = 0.30
HAND_MAX_CANDIDATES = 2
HAND_VIEW_EXPANSION = 1.0
HAND_ADMISSION_IOU = 0.80
HAND_DETECTOR_SHORTEST_EDGE = 800
HAND_DETECTOR_LONGEST_EDGE = 1333


def _object_mediated_behavior_constraint_indices(plan: dict) -> tuple[int, ...]:
    """冻结 marker：normalized behavior constraint text 与 '正在钓鱼' 精确相等（合同 §1.2）。

    返回 behavior route 约束列表中命中的 positions；与 case id、模型文本、关键词
    模糊匹配无关。每个 plan 在 first-pass 前计算一次并固化。
    """
    behavior_items = [
        item
        for item in plan.get("constraints", [])
        if item.get("route") == "behavior"
    ]
    return tuple(
        index
        for index, item in enumerate(behavior_items)
        if item.get("text", "").strip() == OBJECT_MEDIATED_BEHAVIOR_MARKER
    )


def _person_masks_for(
    candidate: dict,
    runtime_candidates: list[dict],
    mask_cache: dict,
) -> list[np.ndarray]:
    """target-anchored 证据的 person_masks：同图其余全部 runtime candidate 的 SAM masks。"""
    return [
        mask_cache[("subject", other["id"])]["mask"]
        for other in runtime_candidates
        if other["id"] != candidate["id"]
    ]


def _bbox_iou(box_a: list[float], box_b: list[float]) -> float:
    """IoU（合同 §1.5 去重与 admission 判定）。"""
    inter_width = max(0.0, min(box_a[2], box_b[2]) - max(box_a[0], box_b[0]))
    inter_height = max(0.0, min(box_a[3], box_b[3]) - max(box_a[1], box_b[1]))
    intersection = inter_width * inter_height
    area_a = max(0.0, box_a[2] - box_a[0]) * max(0.0, box_a[3] - box_a[1])
    area_b = max(0.0, box_b[2] - box_b[0]) * max(0.0, box_b[3] - box_b[1])
    union = area_a + area_b - intersection
    if union <= 0:
        return 0.0
    return intersection / union


def _stable_hand_candidate_admission(
    hand_candidates: list[dict],
    old_candidates: list[dict],
) -> list[dict]:
    """冻结 admission：按 (-confidence, *bbox) 排序；与全部旧候选任一 IoU>=0.80 拒绝；
    再对保留候选按同样顺序做稳定 IoU>=0.80 去重（合同 §2.2 P2.1）。"""
    ordered = sorted(
        hand_candidates,
        key=lambda item: (-item["dino_confidence"], *item["bbox"]),
    )
    admitted: list[dict] = []
    for candidate in ordered:
        if any(
            _bbox_iou(candidate["bbox"], old["bbox"]) >= HAND_ADMISSION_IOU
            for old in old_candidates
        ):
            continue
        if any(
            _bbox_iou(candidate["bbox"], kept["bbox"]) >= HAND_ADMISSION_IOU
            for kept in admitted
        ):
            continue
        admitted.append(candidate)
    return admitted


def _hand_detector_size(image_size: tuple[int, int]) -> tuple[int, int]:
    width, height = image_size
    scale = min(
        1.0,
        HAND_DETECTOR_SHORTEST_EDGE / min(width, height),
        HAND_DETECTOR_LONGEST_EDGE / max(width, height),
    )
    return (
        max(1, round(width * scale)),
        max(1, round(height * scale)),
    )


def _scaled_hand_detector_view(
    view: Image.Image,
) -> tuple[Image.Image, float, float]:
    """按 GroundingDINO processor 的 800/1333 边界预缩小，仅供 hand Detector。"""
    width, height = view.size
    detector_size = _hand_detector_size(view.size)
    if detector_size == view.size:
        return view, 1.0, 1.0
    detector_view = view.resize(detector_size, Image.Resampling.BILINEAR)
    return detector_view, width / detector_size[0], height / detector_size[1]


def _hand_conditioned_candidates(
    image_path: Path,
    subject: dict,
    related_object: str,
    old_candidates: list[dict],
    detector,
) -> tuple[list[dict], dict]:
    """对单个 incomplete subject 执行一次 hand-conditioned related-object
    localization（合同 §1.5 步骤 1-10）。返回 (admitted, telemetry)。"""
    telemetry = {
        "hand_detector_calls": 1,
        "admitted_count": 0,
        "new_candidate_ids": [],
    }
    view, crop_bbox = build_subject_conditioned_grounding_view(
        image_path,
        subject["bbox"],
    )
    view_width, view_height = view.size
    subject_box = subject["bbox"]
    subject_view_box = [
        subject_box[0] - crop_bbox[0],
        subject_box[1] - crop_bbox[1],
        subject_box[2] - crop_bbox[0],
        subject_box[3] - crop_bbox[1],
    ]
    detector_view, scale_x, scale_y = _scaled_hand_detector_view(view)
    telemetry["subject_view_dimensions"] = [view_width, view_height]
    telemetry["hand_detector_dimensions"] = list(detector_view.size)
    telemetry["hand_detector_resized"] = detector_view is not view

    try:
        with tempfile.TemporaryDirectory(prefix="visual_agent_relation_") as temporary_dir:
            subject_view_path = Path(temporary_dir) / "subject_context.png"
            detector_view.save(subject_view_path, format="PNG")
            detector_hand_detections = detector.detect(
                subject_view_path,
                "hand",
                threshold=HAND_CONDITIONED_THRESHOLD,
            )
    finally:
        if detector_view is not view:
            detector_view.close()

    hand_detections = [
        {
            **detection,
            "bbox": [
                detection["bbox"][0] * scale_x,
                detection["bbox"][1] * scale_y,
                detection["bbox"][2] * scale_x,
                detection["bbox"][3] * scale_y,
            ],
        }
        for detection in detector_hand_detections
    ]

    filtered_hands = []
    for detection in hand_detections:
        box = detection["bbox"]
        center_x = (box[0] + box[2]) / 2.0
        center_y = (box[1] + box[3]) / 2.0
        if (
            subject_view_box[0] <= center_x <= subject_view_box[2]
            and subject_view_box[1] <= center_y <= subject_view_box[3]
        ):
            filtered_hands.append(detection)
    filtered_hands.sort(
        key=lambda item: (-item["confidence"], *item["bbox"])
    )
    filtered_hands = filtered_hands[:HAND_MAX_CANDIDATES]

    raw_related: list[dict] = []
    for hand in filtered_hands:
        hand_box = hand["bbox"]
        width = hand_box[2] - hand_box[0]
        height = hand_box[3] - hand_box[1]
        hand_view_box = [
            max(0, math.floor(hand_box[0] - HAND_VIEW_EXPANSION * width)),
            max(0, math.floor(hand_box[1] - HAND_VIEW_EXPANSION * height)),
            min(view_width, math.ceil(hand_box[2] + HAND_VIEW_EXPANSION * width)),
            min(view_height, math.ceil(hand_box[3] + HAND_VIEW_EXPANSION * height)),
        ]
        if hand_view_box[0] >= hand_view_box[2] or hand_view_box[1] >= hand_view_box[3]:
            continue
        hand_view_image = view.crop(tuple(hand_view_box))
        with tempfile.TemporaryDirectory(
            prefix="visual_agent_relation_"
        ) as temporary_dir:
            hand_view_path = Path(temporary_dir) / "hand_context.png"
            hand_view_image.save(hand_view_path, format="PNG")
            related_detections = detector.detect(
                hand_view_path,
                related_object,
                threshold=HAND_CONDITIONED_THRESHOLD,
            )
        for detection in related_detections:
            x1, y1, x2, y2 = detection["bbox"]
            raw_related.append(
                {
                    "object": related_object,
                    "text_label": detection["text_label"],
                    "bbox": [
                        x1 + hand_view_box[0] + crop_bbox[0],
                        y1 + hand_view_box[1] + crop_bbox[1],
                        x2 + hand_view_box[0] + crop_bbox[0],
                        y2 + hand_view_box[1] + crop_bbox[1],
                    ],
                    "dino_confidence": detection["confidence"],
                }
            )

    admitted = _stable_hand_candidate_admission(raw_related, old_candidates)
    telemetry["admitted_count"] = len(admitted)
    return admitted, telemetry


def _run_hand_conditioned_fallback(
    *,
    image_path: Path,
    relation_subjects: list[dict],
    relation_candidates: list[dict],
    relation_bindings: list[dict],
    related_plan: dict,
    detector,
    relation_protocols: list[dict],
) -> dict:
    """合同 §1.5 / §2.2 P2 编排：每个 incomplete subject 至多一次 hand-conditioned
    localization；admission 全局累积；有新增时对全部 relation-eligible subjects
    建立完整 binding matrix（含已 satisfied subject，且不触发其 hand Detector）。"""
    subjects_with_satisfied = {
        binding["subject_id"]
        for binding in relation_bindings
        if binding["status"] == "satisfied"
    }
    incomplete_subjects = [
        subject
        for subject in relation_subjects
        if subject["id"] not in subjects_with_satisfied
    ]
    related_object = related_plan["object"]
    relation = related_plan["relation"]

    fallback = {
        "relation_candidates": relation_candidates,
        "relation_bindings": relation_bindings,
        "relation_protocols": relation_protocols,
        "telemetry": {
            "attempts": 0,
            "detector_calls": 0,
            "admitted_count": 0,
            "hand_relation_calls": 0,
            "max_per_subject": 1,
            "subjects": {},
        },
    }
    for subject in relation_subjects:
        fallback["telemetry"]["subjects"][subject["id"]] = {
            "attempted": False,
            "hand_detector_calls": 0,
            "admitted_count": 0,
            "new_candidate_ids": [],
            "hand_relation_calls": 0,
            "subject_view_dimensions": None,
            "hand_detector_dimensions": None,
            "hand_detector_resized": False,
        }
    if not incomplete_subjects:
        return fallback

    working_candidates = list(relation_candidates)
    admitted_by_subject: dict[str, list[dict]] = {}
    for subject in incomplete_subjects:
        admitted, telemetry = _hand_conditioned_candidates(
            image_path,
            subject,
            related_object,
            working_candidates,
            detector,
        )
        fallback["telemetry"]["attempts"] += 1
        fallback["telemetry"]["detector_calls"] += telemetry["hand_detector_calls"]
        fallback["telemetry"]["subjects"][subject["id"]]["attempted"] = True
        fallback["telemetry"]["subjects"][subject["id"]][
            "hand_detector_calls"
        ] = telemetry["hand_detector_calls"]
        fallback["telemetry"]["subjects"][subject["id"]][
            "admitted_count"
        ] = telemetry["admitted_count"]
        fallback["telemetry"]["subjects"][subject["id"]][
            "subject_view_dimensions"
        ] = telemetry["subject_view_dimensions"]
        fallback["telemetry"]["subjects"][subject["id"]][
            "hand_detector_dimensions"
        ] = telemetry["hand_detector_dimensions"]
        fallback["telemetry"]["subjects"][subject["id"]][
            "hand_detector_resized"
        ] = telemetry["hand_detector_resized"]
        if admitted:
            for candidate in admitted:
                candidate["id"] = f"R{len(working_candidates) + 1}"
                working_candidates.append(candidate)
            admitted_by_subject[subject["id"]] = admitted
            fallback["telemetry"]["subjects"][subject["id"]][
                "new_candidate_ids"
            ] = [candidate["id"] for candidate in admitted]

    new_candidates = [
        candidate
        for candidate in working_candidates
        if candidate["id"] not in {
            item["id"] for item in relation_candidates
        }
    ]
    if not new_candidates:
        fallback["telemetry"]["admitted_count"] = 0
        return fallback

    fallback["telemetry"]["admitted_count"] = len(new_candidates)
    working_bindings = list(relation_bindings)
    working_protocols = list(relation_protocols)
    for relation_subject in relation_subjects:
        subject_bindings, subject_protocol = verify_relations(
            image_path,
            [relation_subject],
            new_candidates,
            related_object,
            relation,
        )
        working_bindings.extend(subject_bindings)
        working_protocols.append(subject_protocol)
        fallback["telemetry"]["subjects"][relation_subject["id"]][
            "hand_relation_calls"
        ] = 1
        fallback["telemetry"]["hand_relation_calls"] += 1
    working_bindings = _resolve_focused_ownership(
        image_path,
        working_bindings,
        working_candidates,
        relation_subjects,
        related_object,
        relation,
        working_protocols,
        only_related_ids={candidate["id"] for candidate in new_candidates},
    )
    fallback["relation_candidates"] = working_candidates
    fallback["relation_bindings"] = working_bindings
    fallback["relation_protocols"] = working_protocols
    return fallback


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


def _merge_protocol_metadata(protocols: list[dict]) -> dict:
    """合并同一逻辑 route 的有界多次调用，保持既有 qwen_protocol 顶层合同。"""
    merged = {
        "attempts": sum(item.get("attempts", 0) for item in protocols),
        "retry_count": sum(item.get("retry_count", 0) for item in protocols),
        "recovered": any(item.get("recovered", False) for item in protocols),
        "first_error_code": next(
            (
                item.get("first_error_code")
                for item in protocols
                if item.get("first_error_code") is not None
            ),
            None,
        ),
    }
    merged.update(merge_transport_telemetry(protocols))
    payload_items = []
    for protocol in protocols:
        payload = protocol.get("evidence_payload")
        if not payload:
            continue
        payload_items.extend(payload.get("items", [payload]))
    if payload_items:
        largest = max(
            payload_items,
            key=lambda item: item["normalized_payload_bytes"],
        )
        merged["evidence_payload"] = {
            "normalization_triggered": any(
                item["normalization_triggered"] for item in payload_items
            ),
            "original_dimensions": largest["original_dimensions"],
            "original_payload_bytes": sum(
                item["original_payload_bytes"] for item in payload_items
            ),
            "normalized_dimensions": largest["normalized_dimensions"],
            "normalized_payload_bytes": sum(
                item["normalized_payload_bytes"] for item in payload_items
            ),
            "target_pixels_first_pass": largest["target_pixels_first_pass"],
            "unit": largest["unit"],
            "evidence_count": len(payload_items),
            "items": payload_items,
        }
    return merged


def _resolve_focused_ownership(
    image_path: Path,
    relation_bindings: list[dict],
    relation_candidates: list[dict],
    relation_subjects: list[dict],
    related_object: str,
    relation: str,
    relation_protocols: list[dict],
    *,
    only_related_ids: set[str] | None = None,
) -> list[dict]:
    """同一 related candidate 被多个 subjects satisfied 时执行 focused ownership 裁决。

    这是 R2.1 唯一保留的跨主体 ownership conflict 路径；R2.3 secondary candidates
    进入正式 universe 后必须经过同一裁决，不得绕过。only_related_ids 限定只裁决
    指定候选，避免对已裁决过的初始候选重复触发。
    """
    conflict_subjects_by_related: dict[str, set[str]] = {}
    for binding in relation_bindings:
        if binding["status"] == "satisfied":
            conflict_subjects_by_related.setdefault(
                binding["related_id"], set()
            ).add(binding["subject_id"])
    related_by_id = {item["id"]: item for item in relation_candidates}
    for related_id, subject_ids in conflict_subjects_by_related.items():
        if only_related_ids is not None and related_id not in only_related_ids:
            continue
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
            related_object,
            relation,
        )
        relation_protocols.append(focused_protocol)
        focused_by_pair = {
            (binding["subject_id"], binding["related_id"]): binding
            for binding in focused_bindings
        }
        relation_bindings = [
            focused_by_pair[(binding["subject_id"], binding["related_id"])]
            if (
                binding["related_id"] == related_id
                and binding["subject_id"] in subject_ids
            )
            else binding
            for binding in relation_bindings
        ]
    return relation_bindings


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
    related_counts = {
        related["id"]: sum(item["related_id"] == related["id"] for item in satisfied)
        for related in related_candidates
    }
    conflict_subjects = {
        item["subject_id"]
        for item in satisfied
        if related_counts[item["related_id"]] > 1
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
        elif subject_satisfied:
            binding = sorted(
                subject_satisfied,
                key=lambda item: (
                    -related_by_id[item["related_id"]].get("dino_confidence", 0.0),
                    item["related_id"],
                ),
            )[0]
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
    with Image.open(image_path) as _image_handle:
        pipeline_image_size = _image_handle.size

    agent = DeepSeekAgent() if (plan is None or final_response) else None
    if plan is None:
        started_at = time.perf_counter()
        plan = agent.plan_request(prompt)
        plan_seconds = time.perf_counter() - started_at
    else:
        plan_seconds = 0.0

    plan = DeepSeekAgent._validated_plan_arguments(plan, prompt=prompt)

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
    behavior_routing: dict[str, dict] = {}
    object_mediated_behavior_indices = _object_mediated_behavior_constraint_indices(
        plan
    )
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
                behavior_evidence = None
                evidence = isolated
                identity_risk = False
                first_pass_arm = None
                if route == "behavior":
                    identity_risk = identity_contamination_risk(
                        pipeline_image_size,
                        candidate["id"],
                        runtime_candidates,
                    )
                    if identity_risk:
                        behavior_evidence = build_target_anchored_behavior_evidence(
                            image_path,
                            candidate["bbox"],
                            candidate["mask"],
                            _person_masks_for(
                                candidate, runtime_candidates, mask_cache
                            ),
                        )
                        first_pass_arm = "B"
                    else:
                        behavior_evidence = build_behavior_evidence(
                            image_path,
                            candidate["bbox"],
                            candidate["mask"],
                        )
                        first_pass_arm = "A"
                    evidence = [isolated, behavior_evidence]
                started_at = time.perf_counter()
                checks, protocol = verify_candidate_constraints(
                    {"id": candidate["id"], "bbox": candidate["bbox"]},
                    route_items,
                    evidence,
                    route,
                )
                if route == "behavior":
                    fallback_arm = None
                    fallback_attempted = False
                    write_back_positions: list[int] = []
                    first_pass_satisfied = bool(checks) and all(
                        check["status"] == "satisfied" for check in checks
                    )
                    uncertain_positions = [
                        position
                        for position, check in enumerate(checks)
                        if check["status"] == "uncertain"
                    ]
                    armed_escalation = (
                        len(route_items) == 1
                        and object_mediated_behavior_indices == (0,)
                        and checks[0]["status"] == "not_satisfied"
                    )
                    contextual_positions = []
                    if len(runtime_candidates) >= 2:
                        if first_pass_satisfied:
                            contextual_positions = list(range(len(checks)))
                        else:
                            contextual_positions = uncertain_positions
                    if contextual_positions:
                        fallback_items = [
                            route_items[position]
                            for position in contextual_positions
                        ]
                        if identity_risk:
                            full_scene = (
                                build_target_anchored_full_scene_evidence(
                                    image_path,
                                    candidate["mask"],
                                    _person_masks_for(
                                        candidate,
                                        runtime_candidates,
                                        mask_cache,
                                    ),
                                )
                            )
                            fallback_arm = "C"
                        else:
                            full_scene = build_candidate_marked_full_scene_evidence(
                                image_path,
                                candidate["mask"],
                            )
                            fallback_arm = "A"
                        fallback_checks, fallback_protocol = verify_candidate_constraints(
                            {"id": candidate["id"], "bbox": candidate["bbox"]},
                            fallback_items,
                            [isolated, behavior_evidence, full_scene],
                            route,
                        )
                        for position, fallback_check in zip(
                            contextual_positions,
                            fallback_checks,
                        ):
                            checks[position] = fallback_check
                        write_back_positions = contextual_positions
                        fallback_attempted = True
                        protocol = _merge_protocol_metadata(
                            [protocol, fallback_protocol]
                        )
                    elif armed_escalation:
                        fallback_items = [route_items[0]]
                        full_scene = build_target_anchored_full_scene_evidence(
                            image_path,
                            candidate["mask"],
                            _person_masks_for(
                                candidate, runtime_candidates, mask_cache
                            ),
                        )
                        fallback_checks, fallback_protocol = verify_candidate_constraints(
                            {"id": candidate["id"], "bbox": candidate["bbox"]},
                            fallback_items,
                            [isolated, behavior_evidence, full_scene],
                            route,
                        )
                        checks[0] = fallback_checks[0]
                        write_back_positions = [0]
                        fallback_arm = "C"
                        fallback_attempted = True
                        protocol = _merge_protocol_metadata(
                            [protocol, fallback_protocol]
                        )
                    behavior_routing[candidate["id"]] = {
                        "identity_risk": identity_risk,
                        "first_pass_arm": first_pass_arm,
                        "route": route,
                        "fallback_arm": fallback_arm,
                        "fallback_attempted": fallback_attempted,
                        "write_back_positions": write_back_positions,
                    }
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
    relation_hand_fallback = {
        "attempts": 0,
        "detector_calls": 0,
        "admitted_count": 0,
        "hand_relation_calls": 0,
        "max_per_subject": 1,
        "subjects": {},
    }
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
            relation_protocols = []
            relation_verification_started_at = time.perf_counter()
            if relation_candidates:
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

                # many-to-one satisfied conflict：按 related object 触发 focused ownership。
                relation_bindings = _resolve_focused_ownership(
                    image_path,
                    relation_bindings,
                    relation_candidates,
                    relation_subjects,
                    related_plan["object"],
                    related_plan["relation"],
                    relation_protocols,
                )

            # R2.3：每个尚无 satisfied binding 的主体最多执行一次固定 35% subject-local
            # grounding；所有新增候选统一进入正式 candidate universe。
            subjects_with_satisfied = {
                binding["subject_id"]
                for binding in relation_bindings
                if binding["status"] == "satisfied"
            }
            secondary_candidates: list[dict] = []
            for relation_subject in relation_subjects:
                if relation_subject["id"] in subjects_with_satisfied:
                    continue
                view, crop_bbox = build_subject_conditioned_grounding_view(
                    image_path,
                    relation_subject["bbox"],
                )
                secondary_grounding_started_at = time.perf_counter()
                with tempfile.TemporaryDirectory(
                    prefix="visual_agent_relation_"
                ) as temporary_dir:
                    view_path = Path(temporary_dir) / "subject_context.png"
                    view.save(view_path, format="PNG")
                    secondary_detections = detector.detect(
                        view_path,
                        related_plan["object"],
                    )
                relation_grounding_seconds += (
                    time.perf_counter() - secondary_grounding_started_at
                )
                for detection in secondary_detections:
                    x1, y1, x2, y2 = detection["bbox"]
                    candidate = {
                        "id": f"R{len(relation_candidates) + 1}",
                        "object": related_plan["object"],
                        "text_label": detection["text_label"],
                        "bbox": [
                            x1 + crop_bbox[0],
                            y1 + crop_bbox[1],
                            x2 + crop_bbox[0],
                            y2 + crop_bbox[1],
                        ],
                        "dino_confidence": detection["confidence"],
                    }
                    relation_candidates.append(candidate)
                    secondary_candidates.append(candidate)

            # R2.3：新增候选对全部 relation-eligible subjects 完成完整 binding matrix
            # （保持每次只传一个 subject 的既有 isolation），并对新增跨 subject 冲突
            # 执行同一 focused ownership，不得绕过跨主体 ownership 路径。
            if secondary_candidates:
                for relation_subject in relation_subjects:
                    secondary_bindings, secondary_protocol = verify_relations(
                        image_path,
                        [relation_subject],
                        secondary_candidates,
                        related_plan["object"],
                        related_plan["relation"],
                    )
                    relation_bindings.extend(secondary_bindings)
                    relation_protocols.append(secondary_protocol)
                relation_bindings = _resolve_focused_ownership(
                    image_path,
                    relation_bindings,
                    relation_candidates,
                    relation_subjects,
                    related_plan["object"],
                    related_plan["relation"],
                    relation_protocols,
                    only_related_ids={
                        candidate["id"] for candidate in secondary_candidates
                    },
                )

            # Production Implementation Contract §1.5 / §2.2 P2：
            # hand-conditioned related-object localization fallback。
            hand_fallback = _run_hand_conditioned_fallback(
                image_path=image_path,
                relation_subjects=relation_subjects,
                relation_candidates=relation_candidates,
                relation_bindings=relation_bindings,
                related_plan=related_plan,
                detector=detector,
                relation_protocols=relation_protocols,
            )
            relation_candidates = hand_fallback["relation_candidates"]
            relation_bindings = hand_fallback["relation_bindings"]
            relation_protocols = hand_fallback["relation_protocols"]
            relation_hand_fallback = hand_fallback["telemetry"]

            if relation_protocols:
                relation_protocol = _merge_protocol_metadata(relation_protocols)
            relation_verification_seconds = (
                time.perf_counter() - relation_verification_started_at
            )
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
            "provider": agent.provider if agent is not None else "deepseek",
            "model": agent.model if agent is not None else MODEL_NAME,
            "planner_tool": TOOL_NAME,
            "plan_attempts": agent.plan_attempts if agent is not None else 0,
            "planner_transport": (
                agent.planner_transport_telemetry()
                if agent is not None
                else merge_transport_telemetry([])
            ),
            "final_response_transport": merge_transport_telemetry([]),
            "final_response_content": (
                agent.final_response_content_telemetry()
                if agent is not None
                else {
                    "content_attempts": 0,
                    "content_retry_count": 0,
                    "content_recovered": False,
                    "first_content_error": None,
                    "final_content_status": "not_started",
                }
            ),
        },
        "plan": plan,
        "candidates": candidates,
        "behavior_routing": behavior_routing,
        "relation_hand_fallback": relation_hand_fallback,
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
        saved_result["agent"]["final_response_transport"] = (
            agent.final_response_transport_telemetry()
        )
        saved_result["agent"]["final_response_content"] = (
            agent.final_response_content_telemetry()
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
