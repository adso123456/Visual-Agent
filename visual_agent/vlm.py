import base64
import json
import mimetypes
import os
from pathlib import Path

from openai import OpenAI


MODEL_NAME = "qwen3-vl-flash"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _image_data_url(image_path: Path) -> str:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def understand_target(image_path: Path, prompt: str) -> dict[str, str]:
    """让 Qwen3-VL 理解场景，并生成 Grounding DINO 使用的英文描述。"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("未设置环境变量 DASHSCOPE_API_KEY")

    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是图片目标理解器。结合图片理解用户真正想找的可见目标。"
                    "只返回一个 JSON 对象，不要 Markdown："
                    '{"grounding_text":"适合开放词汇检测器的简短英文名词短语",'
                    '"label":"简短中文目标名","reason":"基于图片的简短中文解释"}。'
                    "不要输出坐标，不要虚构图片中不存在的细节。"
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
                    {"type": "text", "text": prompt},
                ],
            },
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Qwen3-VL 返回了空响应")

    result = json.loads(content)
    required = ("grounding_text", "label", "reason")
    if any(not isinstance(result.get(key), str) or not result[key].strip() for key in required):
        raise RuntimeError(f"Qwen3-VL 返回缺少必要字段：{content}")
    return {key: result[key].strip() for key in required}

