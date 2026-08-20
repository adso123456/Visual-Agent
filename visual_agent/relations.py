import base64
import io
import json
import os
from pathlib import Path

from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

from visual_agent.qwen_protocol import request_validated_json


MODEL_NAME = "qwen3-vl-flash"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
RELATION = "held_by_target"
STATUSES = {"satisfied", "not_satisfied", "uncertain"}


def _client() -> OpenAI:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("未设置环境变量 DASHSCOPE_API_KEY")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


def _marked_scene_data_url(
    image_path: Path,
    subjects: list[dict],
    related_candidates: list[dict],
) -> str:
    image = Image.open(image_path).convert("RGB")
    scale = max(1.0, 1024 / max(image.size))
    if scale > 1:
        image = image.resize(
            (round(image.width * scale), round(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(20, min(image.size) // 18))
    line_width = max(3, min(image.size) // 150)
    marked = [
        *((subject, "#ff0000", "主体") for subject in subjects),
        *((candidate, "#0066ff", "关联对象") for candidate in related_candidates),
    ]
    for candidate, color, role in marked:
        bbox = [coordinate * scale for coordinate in candidate["bbox"]]
        label = f"{candidate['id']} {role}"
        draw.rectangle(bbox, outline=color, width=line_width)
        text_bbox = draw.textbbox((0, 0), label, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        label_x = max(0, int(bbox[0]))
        label_y = max(0, int(bbox[1]) - text_height - 4)
        draw.rectangle(
            (label_x, label_y, label_x + text_width + 6, label_y + text_height + 4),
            fill=color,
        )
        draw.text((label_x + 3, label_y + 2), label, fill="white", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def validate_relation_bindings(
    result: dict,
    subjects: list[dict],
    related_candidates: list[dict],
    relation: str,
) -> list[dict]:
    bindings = result.get("bindings") if isinstance(result, dict) else None
    expected_pairs = {
        (subject["id"], related["id"])
        for subject in subjects
        for related in related_candidates
    }
    if not isinstance(bindings, list) or len(bindings) != len(expected_pairs):
        raise RuntimeError("Qwen relation bindings 数量与 S×R matrix 不一致")
    normalized = []
    returned_pairs = set()
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != {
            "subject_id",
            "related_id",
            "relation",
            "status",
            "evidence",
        }:
            raise RuntimeError("Qwen relation binding 字段不正确")
        for field in ["subject_id", "related_id", "relation", "status", "evidence"]:
            if not isinstance(binding[field], str):
                raise RuntimeError(f"Qwen relation binding {field} 必须是字符串")
        pair = (binding["subject_id"], binding["related_id"])
        if pair not in expected_pairs or pair in returned_pairs:
            raise RuntimeError("Qwen relation binding 包含非法或重复组合")
        if binding["relation"] != relation:
            raise RuntimeError("Qwen relation 与输入不一致")
        if binding["status"] not in STATUSES:
            raise RuntimeError("Qwen relation status 不在三态枚举中")
        evidence = binding["evidence"]
        if not isinstance(evidence, str) or not evidence.strip():
            raise RuntimeError("Qwen relation evidence 必须是非空字符串")
        returned_pairs.add(pair)
        normalized.append(
            {
                "subject_id": pair[0],
                "related_id": pair[1],
                "relation": relation,
                "status": binding["status"],
                "evidence": evidence.strip(),
            }
        )
    if returned_pairs != expected_pairs:
        raise RuntimeError("Qwen relation binding 漏掉 S×R 组合")
    return normalized


def verify_relations(
    image_path: Path,
    subjects: list[dict],
    related_candidates: list[dict],
    related_object: str,
    relation: str,
) -> tuple[list[dict], dict]:
    if not subjects or not related_candidates:
        raise ValueError("Relation Verification 需要非空 subjects 和 related candidates")
    if relation != RELATION:
        raise ValueError(f"不支持的 relation：{relation}")
    messages = [
            {
                "role": "system",
                "content": (
                    "你是群组视觉关系验证器。红框 A/B/C 等是已验证主体，蓝框 R1/R2/R3 等是关联对象候选。"
                    "一次判断每个主体与每个关联候选的完整笛卡尔积。held_by_target 表示蓝框物体确实由指定红框主体持有。"
                    "必须关注主体手部、物体手柄、直接抓握或接触和明确归属；物体仅靠近人物不能判定为持有，"
                    "不得把相邻人物的物体借给当前主体，不得根据常识猜测。证据不足必须使用 uncertain。"
                    "只返回 JSON，顶层仅 bindings。每项只能包含 subject_id、related_id、relation、status、evidence。"
                    "status 只能是 satisfied、not_satisfied、uncertain。每个 S×R 组合必须恰好返回一次。"
                    "bindings 的值必须是 JSON 数组，不得返回以候选 ID 为 key 的对象。"
                    "结构必须为 {\"bindings\":[{\"subject_id\":\"A\",\"related_id\":\"R1\","
                    "\"relation\":\"held_by_target\",\"status\":\"<三态之一>\",\"evidence\":\"<非空证据>\"}]}。"
                    "不要输出 Markdown、分析过程或候选之外的视觉事实。"
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": _marked_scene_data_url(
                                image_path,
                                subjects,
                                related_candidates,
                            )
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"relation：{relation}\n关联实体：{related_object}\n"
                            f"主体 IDs：{json.dumps([item['id'] for item in subjects], ensure_ascii=False)}\n"
                            f"关联 IDs：{json.dumps([item['id'] for item in related_candidates], ensure_ascii=False)}\n"
                            "请返回完整 S×R bindings matrix。"
                        ),
                    },
                ],
            },
        ]

    def request_once(correction: str | None) -> str | None:
        request_messages = [*messages]
        if correction:
            request_messages.append({"role": "user", "content": correction})
        response = _client().chat.completions.create(
            model=MODEL_NAME,
            messages=request_messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    return request_validated_json(
        request_once,
        lambda result: validate_relation_bindings(
            result,
            subjects,
            related_candidates,
            relation,
        ),
        "relation verification",
        '{"bindings":[{"subject_id":"A","related_id":"R1","relation":"held_by_target","status":"<三态之一>","evidence":"<非空证据>"}]}',
    )


def verify_focused_ownership(
    image_path: Path,
    subjects: list[dict],
    related_candidates: list[dict],
    related_object: str,
    relation: str,
) -> tuple[list[dict], dict]:
    """对象级归属冲突裁决：一次只裁决多个冲突主体与一个 related object。"""
    if len(subjects) < 2:
        raise ValueError("Focused Ownership 需要至少 2 个冲突 subjects")
    if len(related_candidates) != 1:
        raise ValueError("Focused Ownership 每次只能裁决 1 个 related object")
    if relation != RELATION:
        raise ValueError(f"不支持的 relation：{relation}")
    related_id = related_candidates[0]["id"]
    subject_ids = json.dumps(
        [item["id"] for item in subjects], ensure_ascii=False
    )
    messages = [
        {
            "role": "system",
            "content": (
                f"你是对象级归属冲突裁决器。完整原图中红框 {subject_ids} 是潜在持有主体，"
                f"蓝框 {related_id} 是唯一关联对象。你只裁决 {related_id} 究竟由这些主体中哪些明确持有，"
                "必须同时比较这些潜在持有者与关联对象的相对位置、手部、手柄或接触位置以及明确视觉归属。"
                "只有能从手部、手柄或接触位置和明确视觉归属确认时才返回 satisfied；"
                "相邻、遮挡或仅靠近不得判 satisfied；不能唯一确认时必须使用 uncertain。"
                "不要判断其他未标出的关联对象，也不要根据常识猜测。"
                "只返回 JSON，顶层仅 bindings。每项只能包含 subject_id、related_id、relation、status、evidence。"
                "status 只能是 satisfied、not_satisfied、uncertain。"
                f"每个主体与唯一关联对象 {related_id} 的组合必须恰好返回一次，不得只输出一个 owner ID。"
                "结构必须为 {\"bindings\":[{\"subject_id\":\"B\",\"related_id\":\"R2\","
                "\"relation\":\"held_by_target\",\"status\":\"<三态之一>\",\"evidence\":\"<非空证据>\"}]}。"
                "不要输出 Markdown、分析过程或候选之外的视觉事实。"
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": _marked_scene_data_url(
                            image_path,
                            subjects,
                            related_candidates,
                        )
                    },
                },
                {
                    "type": "text",
                    "text": (
                        f"relation：{relation}\n关联实体：{related_object}\n"
                        f"唯一关联对象 ID：{related_id}\n"
                        f"冲突潜在持有主体 IDs：{subject_ids}\n"
                        f"请判断该关联对象由哪些主体明确持有；每个 subject-{related_id} 组合返回三态。"
                    ),
                },
            ],
        },
    ]

    def request_once(correction: str | None) -> str | None:
        request_messages = [*messages]
        if correction:
            request_messages.append({"role": "user", "content": correction})
        response = _client().chat.completions.create(
            model=MODEL_NAME,
            messages=request_messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    return request_validated_json(
        request_once,
        lambda result: validate_relation_bindings(
            result,
            subjects,
            related_candidates,
            relation,
        ),
        "focused ownership verification",
        '{"bindings":[{"subject_id":"B","related_id":"R2","relation":"held_by_target","status":"<三态之一>","evidence":"<非空证据>"}]}',
    )
