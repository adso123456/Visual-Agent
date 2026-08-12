import base64
import io
import json
import mimetypes
import os
from pathlib import Path

from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont


MODEL_NAME = "qwen3-vl-flash"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _image_data_url(image_path: Path) -> str:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _marked_candidates_data_url(image_path: Path, candidates: list[dict]) -> str:
    image = Image.open(image_path).convert("RGB")
    scale = max(1.0, 1024 / max(image.size))
    if scale > 1:
        image = image.resize(
            (round(image.width * scale), round(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(20, min(image.size) // 18))
    colors = ["#ff0000", "#00a000", "#0066ff", "#ff00ff", "#ff8800", "#00aaaa"]
    line_width = max(3, min(image.size) // 150)
    for index, candidate in enumerate(candidates):
        color = colors[index % len(colors)]
        bbox = [coordinate * scale for coordinate in candidate["bbox"]]
        candidate_id = candidate["id"]
        draw.rectangle(bbox, outline=color, width=line_width)
        text_bbox = draw.textbbox((0, 0), candidate_id, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        x1, y1 = bbox[:2]
        label_x = max(0, int(x1))
        label_y = max(0, int(y1) - text_height - 4)
        draw.rectangle(
            (label_x, label_y, label_x + text_width + 6, label_y + text_height + 4),
            fill=color,
        )
        draw.text((label_x + 3, label_y + 2), candidate_id, fill="white", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _client() -> OpenAI:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("未设置环境变量 DASHSCOPE_API_KEY")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


def _json_response(messages: list[dict]) -> dict:
    response = _client().chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Qwen3-VL 返回了空响应")
    return json.loads(content)


def understand_target(image_path: Path, prompt: str) -> dict:
    """仅根据用户原始要求拆分基础视觉实体和语义约束。"""
    result = _json_response(
        [
            {
                "role": "system",
                "content": (
                    "你是视觉任务规划器。只根据用户原始要求生成任务计划，不参考或猜测任何具体图片内容。"
                    "只返回 JSON，不要 Markdown、分析过程、"
                    "候选方案、自我讨论或推理过程。只允许字段 target_object、label、constraints。"
                    "target_object 必须是适合开放词汇检测的简短英文基础实体，通常 1 到 3 个英文单词，"
                    "不得包含行为、环境或复杂关系。label 是简短中文目标名。constraints 是中文字符串数组，"
                    "只拆解用户要求中的行为、属性、空间关系、对象关系和否定条件，不得加入用户未要求的"
                    "衣着、姿势或场景细节。所有人物目标统一使用 person，不使用 man、woman、boy 或 girl。"
                    "constraints 只保留基础实体之外的剩余语义，不得重复 target_object、label 或实体类别。"
                    "不要输出坐标或 reason。"
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]
    )
    target_object = result.get("target_object")
    label = result.get("label")
    constraints = result.get("constraints")
    if not isinstance(target_object, str) or not target_object.strip():
        raise RuntimeError(f"Qwen3-VL 返回无效 target_object：{result}")
    if not isinstance(label, str) or not label.strip():
        raise RuntimeError(f"Qwen3-VL 返回无效 label：{result}")
    if not isinstance(constraints, list) or any(
        not isinstance(item, str) or not item.strip() for item in constraints
    ):
        raise RuntimeError(f"Qwen3-VL 返回无效 constraints：{result}")
    if not 1 <= len(target_object.split()) <= 3:
        raise RuntimeError(f"Qwen3-VL target_object 不是简短基础实体：{target_object}")
    return {
        "target_object": target_object.strip(),
        "label": label.strip(),
        "constraints": [item.strip() for item in constraints],
    }


def verify_candidates(
    image_path: Path,
    prompt: str,
    plan: dict,
    candidates: list[dict],
) -> list[dict]:
    """在同一完整场景中对所有候选进行相对验证。"""
    result = _json_response(
        [
            {
                "role": "system",
                "content": (
                    "你是群组候选目标验证器。图片保留完整场景，多个检测框使用不同颜色和 A/B/C 等字母标识。"
                    "同时比较所有候选，逐一判断每个候选自身是否满足给定语义约束。必须区分行为、装备、"
                    "属性和对象关系究竟属于哪个候选，不得借用相邻候选的证据。"
                    "每个候选的每条约束必须各返回一个 check，顺序和原文必须与输入 constraints 完全一致，"
                    "不得合并或新增。如果候选区域只显示局部身体，或关键行为、属性、装备归属或对象关系"
                    "无法确认，对应 status 必须为 uncertain。"
                    "当基础目标是 person 时，只包含手、手臂、腿等局部肢体的检测框不是有效人物实例，"
                    "即使局部动作看似相关，各项 status 也必须为 not_satisfied。"
                    "只返回 JSON，顶层字段仅为 candidates。每个候选只能包含 id、checks；每个 check 只能包含"
                    "constraint、status、evidence。status 只能是 satisfied、not_satisfied 或 uncertain。"
                    "satisfied 表示有明确可见证据；not_satisfied 表示有明确反证；uncertain 表示证据不足或归属不清。"
                    "evidence 使用中文，只写该候选的可见证据。"
                    "不要输出 Markdown、思维过程、备选答案、自我讨论，也不要使用‘首先’‘进一步分析’"
                    "‘综合判断’‘最终决定’‘可能的其他选择’。不得凭空补充事实或推断。"
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": _marked_candidates_data_url(image_path, candidates)},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"用户原始要求：{prompt}\n目标名称：{plan['label']}\n"
                            f"语义约束：{json.dumps(plan['constraints'], ensure_ascii=False)}\n"
                            f"候选列表：{json.dumps([candidate['id'] for candidate in candidates], ensure_ascii=False)}\n"
                            "请按候选 ID 分别判断，证据不足或无法确认装备归属时使用 uncertain。"
                        ),
                    },
                ],
            },
        ]
    )
    returned_candidates = result.get("candidates")
    if not isinstance(returned_candidates, list) or len(returned_candidates) != len(candidates):
        raise RuntimeError(f"Qwen3-VL candidates 数量与输入不一致：{result}")
    candidates_by_id = {item.get("id"): item for item in returned_candidates if isinstance(item, dict)}
    if set(candidates_by_id) != {candidate["id"] for candidate in candidates}:
        raise RuntimeError(f"Qwen3-VL candidates ID 与输入不一致：{result}")

    normalized_candidates = []
    for candidate in candidates:
        candidate_id = candidate["id"]
        checks = candidates_by_id[candidate_id].get("checks")
        if not isinstance(checks, list) or len(checks) != len(plan["constraints"]):
            raise RuntimeError(f"Qwen3-VL checks 数量与 constraints 不一致：{result}")
        normalized_checks = []
        for expected_constraint, check in zip(plan["constraints"], checks):
            if not isinstance(check, dict) or check.get("constraint") != expected_constraint:
                raise RuntimeError(f"Qwen3-VL check 未对应原始 constraint：{result}")
            status = check.get("status")
            if status not in {"satisfied", "not_satisfied", "uncertain"}:
                raise RuntimeError(f"Qwen3-VL 返回无效 status：{result}")
            evidence = check.get("evidence")
            if not isinstance(evidence, str) or not evidence.strip():
                raise RuntimeError(f"Qwen3-VL 返回无效 evidence：{result}")
            normalized_checks.append(
                {
                    "constraint": expected_constraint,
                    "status": status,
                    "evidence": evidence.strip(),
                }
            )
        normalized_candidates.append({"id": candidate_id, "checks": normalized_checks})
    return normalized_candidates
