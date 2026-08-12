import base64
import io
import json
import mimetypes
import os
from pathlib import Path

from openai import OpenAI
from PIL import Image, ImageDraw


MODEL_NAME = "qwen3-vl-flash"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _image_data_url(image_path: Path) -> str:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _candidate_data_url(image_path: Path, bbox: list[float]) -> str:
    image = Image.open(image_path).convert("RGB")
    x1, y1, x2, y2 = bbox
    padding_x = (x2 - x1) * 0.1
    padding_y = (y2 - y1) * 0.1
    crop = image.crop(
        (
            max(0, x1 - padding_x),
            max(0, y1 - padding_y),
            min(image.width, x2 + padding_x),
            min(image.height, y2 + padding_y),
        )
    )
    buffer = io.BytesIO()
    crop.save(buffer, format="JPEG", quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _marked_image_data_url(image_path: Path, bbox: list[float]) -> str:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.rectangle(bbox, outline="red", width=max(3, min(image.size) // 200))
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
    """把用户任务拆成基础视觉实体和语义约束。"""
    result = _json_response(
        [
            {
                "role": "system",
                "content": (
                    "你是视觉任务规划器。结合图片和用户要求，只返回 JSON，不要 Markdown、分析过程、"
                    "候选方案、自我讨论或推理过程。只允许字段 target_object、label、constraints。"
                    "target_object 必须是适合开放词汇检测的简短英文基础实体，通常 1 到 3 个英文单词，"
                    "不得包含行为、环境或复杂关系。label 是简短中文目标名。constraints 是中文字符串数组，"
                    "只拆解用户要求中的行为、属性、空间关系、对象关系和否定条件，不得加入用户未要求的"
                    "衣着、姿势或场景细节。所有人物目标统一使用 person，不使用 man、woman、boy 或 girl。"
                    "不要输出坐标或 reason。"
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
                    {"type": "text", "text": prompt},
                ],
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


def verify_candidate(
    image_path: Path,
    prompt: str,
    plan: dict,
    bbox: list[float],
) -> dict:
    """结合原图和候选区域，验证候选是否满足用户的完整语义要求。"""
    result = _json_response(
        [
            {
                "role": "system",
                "content": (
                    "你是候选目标验证器。第一张图是保留完整场景并用红框标出当前候选的原图，"
                    "第二张图是该红框候选的局部区域。"
                    "只判断第二张图中的候选自身是否满足用户要求和全部语义约束；第一张图只用于确认该候选"
                    "与环境或其他对象的关系，不得借用其他对象的行为、装备或属性作为当前候选的证据。"
                    "只有全部语义约束都能从红框候选自身得到清楚可见证据时 match 才能为 true。"
                    "如果候选区域只显示局部身体，或任一关键行为、属性或对象关系无法确认，match 必须为 false。"
                    "当基础目标是 person 时，只包含手、手臂、腿等局部肢体的检测框不是有效人物实例，"
                    "即使局部动作看似相关也必须返回 false。"
                    "只返回 JSON，字段仅为 match 和 reason。"
                    "match 必须是 true 或 false。reason 必须是中文一句话、只写可见证据且不超过 50 个中文字符。"
                    "不要输出 Markdown、思维过程、备选答案、自我讨论，也不要使用‘首先’‘进一步分析’"
                    "‘综合判断’‘最终决定’‘可能的其他选择’。证据不足时返回 false，不得凭空补充事实或推断。"
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _marked_image_data_url(image_path, bbox)}},
                    {"type": "image_url", "image_url": {"url": _candidate_data_url(image_path, bbox)}},
                    {
                        "type": "text",
                        "text": (
                            f"用户原始要求：{prompt}\n目标名称：{plan['label']}\n"
                            f"语义约束：{json.dumps(plan['constraints'], ensure_ascii=False)}\n"
                            "红框和第二张图片表示同一个当前候选对象。"
                        ),
                    },
                ],
            },
        ]
    )
    match = result.get("match")
    reason = result.get("reason")
    if not isinstance(match, bool):
        raise RuntimeError(f"Qwen3-VL 返回无效 match：{result}")
    if not isinstance(reason, str) or not reason.strip():
        raise RuntimeError(f"Qwen3-VL 返回无效 reason：{result}")
    if len(reason.strip()) > 50 or "。" in reason.strip()[:-1]:
        raise RuntimeError(f"Qwen3-VL reason 必须是一句且不超过 50 字：{result}")
    return {"match": match, "reason": reason.strip()}
