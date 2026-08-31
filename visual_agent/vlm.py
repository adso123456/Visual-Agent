import base64
import io
import json
import math
import mimetypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from visual_agent.qwen_protocol import request_validated_json
from visual_agent.vlm_client import (
    DEFAULT_VLM_BASE_URL,
    DEFAULT_VLM_MODEL,
    create_vlm_client,
    get_vlm_model_name,
)


MODEL_NAME = DEFAULT_VLM_MODEL
BASE_URL = DEFAULT_VLM_BASE_URL
ACTION_TYPES = {"highlight", "outline", "box", "blur_target", "dim_background", "cutout"}
SEMANTIC_ROUTES = {"attribute", "behavior"}
SEMANTIC_STATUSES = {"satisfied", "not_satisfied", "uncertain"}
VALIDITY_STATUSES = {"valid", "invalid", "uncertain"}


def _image_data_url(image_path: Path) -> str:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


_DATA_URI_PNG_PREFIX = "data:image/png;base64,"
# Qwen provider caps: decoded data-uri bytes 20 MiB / base64 string length
# ~28M chars.  Internal safe limit on the actual sent payload (base64 chars)
# keeps headroom without sitting near the provider limit.
EVIDENCE_PAYLOAD_SAFE_LIMIT = 18 * 1024 * 1024
EVIDENCE_NORMALIZE_TARGET_PIXELS = 4_000_000

_EVIDENCE_TELEMETRY: dict | None = None


def _encode_png_data_url(image: Image.Image) -> tuple[str, int]:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"{_DATA_URI_PNG_PREFIX}{encoded}", len(encoded)


def _normalize_evidence_payload(
    image: Image.Image,
) -> tuple[str, dict]:
    """把超限临时 evidence 缩小后重新 PNG 编码，直至实际 payload <= safe limit。

    仅作用于序列化边界的临时副本：保持宽高比、禁止放大；evidence 构造语义不变，
    原始图片 / Detector / SAM 输入输出分辨率均不受影响。
    """
    data_url, payload = _encode_png_data_url(image)
    original_size = (image.width, image.height)
    original_payload = payload
    if payload <= EVIDENCE_PAYLOAD_SAFE_LIMIT:
        return data_url, {
            "normalization_triggered": False,
            "original_dimensions": list(original_size),
            "original_payload_bytes": original_payload,
            "normalized_dimensions": list(original_size),
            "normalized_payload_bytes": original_payload,
            "target_pixels_first_pass": EVIDENCE_NORMALIZE_TARGET_PIXELS,
            "unit": "base64_payload_chars",
        }
    current = image
    target_pixels = EVIDENCE_NORMALIZE_TARGET_PIXELS
    normalized_dims = None
    normalized_payload = None
    normalized_url = None
    guard = 0
    while guard < 64:
        guard += 1
        area = current.width * current.height
        if area <= 256:
            break
        scale = min(math.sqrt(target_pixels / area), 1.0)
        if scale <= 0.0:
            break
        new_size = (
            max(1, round(current.width * scale)),
            max(1, round(current.height * scale)),
        )
        if tuple(new_size) == current.size:
            break
        resized = current.convert("RGB").resize(
            new_size,
            Image.Resampling.LANCZOS,
        )
        data_url, payload = _encode_png_data_url(resized)
        normalized_dims = list(new_size)
        normalized_payload = payload
        normalized_url = data_url
        if payload <= EVIDENCE_PAYLOAD_SAFE_LIMIT:
            break
        current = resized
        target_pixels = max(1, target_pixels // 2)
    if normalized_url is None:
        normalized_url, normalized_payload = _encode_png_data_url(current)
        normalized_dims = list(current.size)
    if normalized_payload is None or normalized_payload > EVIDENCE_PAYLOAD_SAFE_LIMIT:
        raise RuntimeError(
            "Qwen evidence payload normalization failed to satisfy safe limit: "
            f"{normalized_payload} > {EVIDENCE_PAYLOAD_SAFE_LIMIT} bytes; "
            "refusing to send oversized data-uri to provider"
        )
    return normalized_url, {
        "normalization_triggered": True,
        "original_dimensions": list(original_size),
        "original_payload_bytes": original_payload,
        "normalized_dimensions": normalized_dims,
        "normalized_payload_bytes": normalized_payload,
        "target_pixels_first_pass": EVIDENCE_NORMALIZE_TARGET_PIXELS,
        "unit": "base64_payload_chars",
    }


def _pil_image_data_url(image: Image.Image) -> str:
    global _EVIDENCE_TELEMETRY
    data_url, telemetry = _normalize_evidence_payload(image)
    _EVIDENCE_TELEMETRY = telemetry
    return data_url


def _take_evidence_telemetry() -> dict | None:
    global _EVIDENCE_TELEMETRY
    telemetry = _EVIDENCE_TELEMETRY
    _EVIDENCE_TELEMETRY = None
    return telemetry


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


def _client():
    return create_vlm_client()


def validate_subject_instance(
    result: dict,
    candidate: dict,
    target_object: str,
) -> dict:
    if not isinstance(result, dict) or set(result) != {
        "candidate_id",
        "target_object",
        "status",
        "evidence",
    }:
        raise RuntimeError("Qwen instance validity 字段不正确")
    if result["candidate_id"] != candidate["id"]:
        raise RuntimeError("Qwen instance validity candidate_id 与输入不一致")
    if result["target_object"] != target_object:
        raise RuntimeError("Qwen instance validity target_object 与输入不一致")
    if result["status"] not in VALIDITY_STATUSES:
        raise RuntimeError("Qwen instance validity status 不在三态枚举中")
    evidence = result["evidence"]
    if not isinstance(evidence, str) or not evidence.strip():
        raise RuntimeError("Qwen instance validity evidence 必须是非空字符串")
    return {
        "candidate_id": candidate["id"],
        "target_object": target_object,
        "status": result["status"],
        "evidence": evidence.strip(),
    }


def verify_subject_instance(
    candidate: dict,
    target_object: str,
    evidence_image: Image.Image,
) -> tuple[dict, dict]:
    """只判断候选是否为一个可独立评价的基础目标实例。"""
    messages = [
        {
            "role": "system",
            "content": (
                "你是基础目标实例有效性验证器。输入图只保留当前候选实例像素，其他区域为中性灰。"
                "只判断该视觉证据是否主要对应一个合理、独立、可作为指定 target_object 的实例。"
                "不得判断任何用户属性、行为、关系或任务是否满足。合理截断或遮挡但仍可独立识别的实例"
                "可以是 valid；明确只有手、手臂、腿等局部碎片、明确非目标、或明确混合多个目标实例且"
                "无法形成单独实例时是 invalid；证据不足时是 uncertain。只返回 JSON，字段必须且只能是"
                "candidate_id、target_object、status、evidence。status 只能是 valid、invalid、uncertain，"
                "evidence 必须使用中文并只描述实例有效性证据。不要输出 Markdown 或分析过程。"
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": _pil_image_data_url(evidence_image)},
                },
                {
                    "type": "text",
                    "text": (
                        f"candidate_id：{candidate['id']}\n"
                        f"target_object：{target_object}\n"
                        "请判断该候选是否为一个有效、独立的基础目标实例。"
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
            model=get_vlm_model_name(),
            messages=request_messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    validated, protocol = request_validated_json(
        request_once,
        lambda result: validate_subject_instance(result, candidate, target_object),
        "subject instance validity",
        '{"candidate_id":"A","target_object":"person","status":"<valid|invalid|uncertain>","evidence":"<非空证据>"}',
    )
    telemetry = _take_evidence_telemetry()
    if telemetry is not None:
        protocol["evidence_payload"] = telemetry
    return validated, protocol


def validate_candidate_constraints(
    result: dict,
    candidate: dict,
    constraints: list[dict],
    route: str,
) -> list[dict]:
    if route not in SEMANTIC_ROUTES:
        raise ValueError(f"不支持的 semantic route：{route}")
    if not constraints or any(item.get("route") != route for item in constraints):
        raise ValueError("routed constraints 必须非空且全部匹配当前 route")
    if not isinstance(result, dict) or set(result) != {"candidate_id", "checks"}:
        raise RuntimeError("Qwen routed verification 顶层字段不正确")
    if result["candidate_id"] != candidate["id"]:
        raise RuntimeError("Qwen routed verification candidate_id 与输入不一致")
    checks = result["checks"]
    if not isinstance(checks, list) or len(checks) != len(constraints):
        raise RuntimeError("Qwen routed checks 数量与 constraints 不一致")
    normalized = []
    for constraint, check in zip(constraints, checks):
        if not isinstance(check, dict) or set(check) != {
            "constraint",
            "status",
            "evidence",
        }:
            raise RuntimeError("Qwen routed check 字段不正确")
        if check["constraint"] != constraint["text"]:
            raise RuntimeError("Qwen routed check 未对应原始 constraint")
        if check["status"] not in SEMANTIC_STATUSES:
            raise RuntimeError("Qwen routed check status 不在三态枚举中")
        evidence = check["evidence"]
        if not isinstance(evidence, str) or not evidence.strip():
            raise RuntimeError("Qwen routed check evidence 必须是非空字符串")
        normalized.append(
            {
                "constraint": constraint["text"],
                "status": check["status"],
                "evidence": evidence.strip(),
            }
        )
    return normalized


def verify_candidate_constraints(
    candidate: dict,
    constraints: list[dict],
    evidence_image: Image.Image,
    route: str,
) -> tuple[list[dict], dict]:
    """使用单候选、单 evidence route 判断同 route 下的多条约束。"""
    if route not in SEMANTIC_ROUTES:
        raise ValueError(f"不支持的 semantic route：{route}")
    route_instruction = {
        "attribute": (
            "图像只保留当前候选实例像素。只根据该候选本人的外观、衣着、颜色、装备等可见证据判断，"
            "不得使用灰色区域或想象相邻人物属性。"
        ),
        "behavior": (
            "图中轮廓标出当前需要判断的人物实例。行为判断只能归属于当前轮廓对应的人物。"
            "可以使用当前局部图中与该人物直接相关的物体、姿态和交互上下文作为证据，"
            "不得把附近其他人物的行为归给当前人物。"
        ),
    }[route]
    constraint_texts = [item["text"] for item in constraints]
    messages = [
        {
            "role": "system",
            "content": (
                f"你是单候选 {route} 语义验证器。{route_instruction}"
                "逐条判断输入 constraints，顺序和原文必须完全一致，不得合并或新增。"
                "status 只能是 satisfied、not_satisfied、uncertain；证据不足或归属不清必须 uncertain。"
                "只返回 JSON，顶层字段必须且只能是 candidate_id、checks；每个 check 只能包含"
                "constraint、status、evidence，evidence 必须为非空中文证据。不要输出 Markdown 或分析过程。"
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": _pil_image_data_url(evidence_image)},
                },
                {
                    "type": "text",
                    "text": (
                        f"candidate_id：{candidate['id']}\nroute：{route}\n"
                        f"constraints：{json.dumps(constraint_texts, ensure_ascii=False)}\n"
                        "请返回每条约束的独立三态判断。"
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
            model=get_vlm_model_name(),
            messages=request_messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    validated, protocol = request_validated_json(
        request_once,
        lambda result: validate_candidate_constraints(
            result,
            candidate,
            constraints,
            route,
        ),
        f"{route} candidate verification",
        '{"candidate_id":"A","checks":[{"constraint":"<原始约束>","status":"<三态之一>","evidence":"<非空证据>"}]}',
    )
    telemetry = _take_evidence_telemetry()
    if telemetry is not None:
        protocol["evidence_payload"] = telemetry
    return validated, protocol


def _json_response(messages: list[dict]) -> dict:
    response = _client().chat.completions.create(
        model=get_vlm_model_name(),
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
                    "候选方案、自我讨论或推理过程。只允许字段 target_object、label、constraints、action。"
                    "target_object 必须是适合开放词汇检测的简短英文基础实体，通常 1 到 3 个英文单词，"
                    "不得包含行为、环境或复杂关系。label 是简短中文目标名。constraints 是中文字符串数组，"
                    "只拆解用户要求中的行为、属性、空间关系、对象关系和否定条件，不得加入用户未要求的"
                    "衣着、姿势或场景细节。所有人物目标统一使用 person，不使用 man、woman、boy 或 girl。"
                    "constraints 只保留基础实体之外的剩余语义，不得重复 target_object、label 或实体类别。"
                    "标红、高亮、框选、描边、模糊、背景变暗、抠图等图片操作不是目标的视觉约束，"
                    "只能表达在 action.type 中，严禁写入 constraints。"
                    "action 必须包含 type，且 type 必须是以下白名单之一："
                    "highlight 表示标红、高亮或只要求找到/定位；box 表示框出、框选或框起来；"
                    "用户明确指定框选、描边或高亮颜色时，box、outline、highlight 可额外包含"
                    "#RRGGBB 格式的 color，未指定时省略 color；其他动作不得包含 color。"
                    "outline 表示只描边；"
                    "blur_target 表示模糊目标；dim_background 表示保持目标原样并让目标以外背景变暗；"
                    "cutout 表示抠出目标并使用透明背景。用户没有明确图片操作、只要求找到或定位时，"
                    "action.type 必须为 highlight。不要输出坐标、reason 或任何图像处理参数。"
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
    action = result.get("action")
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
    if (
        not isinstance(action, dict)
        or not {"type"} <= set(action) <= {"type", "color"}
        or action.get("type") not in ACTION_TYPES
    ):
        raise RuntimeError(f"Qwen3-VL 返回无效 action：{result}")
    color = action.get("color")
    if color is not None and (
        action["type"] not in {"box", "outline", "highlight"}
        or not isinstance(color, str)
        or not color.startswith("#")
        or len(color) != 7
        or any(character not in "0123456789abcdefABCDEF" for character in color[1:])
    ):
        raise RuntimeError(f"Qwen3-VL 返回无效 action.color：{result}")
    normalized_action = {"type": action["type"]}
    if color is not None:
        normalized_action["color"] = color.lower()
    return {
        "target_object": target_object.strip(),
        "label": label.strip(),
        "constraints": [item.strip() for item in constraints],
        "action": normalized_action,
    }


def verify_candidates(
    image_path: Path,
    prompt: str,
    plan: dict,
    candidates: list[dict],
) -> tuple[list[dict], dict]:
    """在同一完整场景中对所有候选进行相对验证。"""
    messages = [
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
                    "candidates 的值必须是 JSON 数组，不得返回以 A/B/C 为 key 的对象。"
                    "结构必须为 {\"candidates\":[{\"id\":\"A\",\"checks\":[{\"constraint\":\"<原始约束>\","
                    "\"status\":\"<三态之一>\",\"evidence\":\"<非空证据>\"}]}]}。"
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

    def request_once(correction: str | None) -> str | None:
        request_messages = [*messages]
        if correction:
            request_messages.append({"role": "user", "content": correction})
        response = _client().chat.completions.create(
            model=get_vlm_model_name(),
            messages=request_messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    return request_validated_json(
        request_once,
        lambda result: validate_candidate_verification(result, candidates, plan["constraints"]),
        "candidate verification",
        '{"candidates":[{"id":"A","checks":[{"constraint":"<原始约束>","status":"<三态之一>","evidence":"<非空证据>"}]}]}',
    )


def validate_candidate_verification(
    result: dict,
    candidates: list[dict],
    constraints: list[str],
) -> list[dict]:
    if not isinstance(result, dict):
        raise RuntimeError("result 必须是 JSON object")
    returned_candidates = result.get("candidates")
    if not isinstance(returned_candidates, list) or len(returned_candidates) != len(candidates):
        raise RuntimeError(f"Qwen3-VL candidates 数量与输入不一致：{result}")
    for item in returned_candidates:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise RuntimeError(f"Qwen3-VL candidate id 必须是字符串：{result}")
        if not isinstance(item.get("checks"), list):
            raise RuntimeError(f"Qwen3-VL checks 必须是数组：{result}")
    candidates_by_id = {item["id"]: item for item in returned_candidates}
    if set(candidates_by_id) != {candidate["id"] for candidate in candidates}:
        raise RuntimeError(f"Qwen3-VL candidates ID 与输入不一致：{result}")

    normalized_candidates = []
    for candidate in candidates:
        candidate_id = candidate["id"]
        checks = candidates_by_id[candidate_id].get("checks")
        if not isinstance(checks, list) or len(checks) != len(constraints):
            raise RuntimeError(f"Qwen3-VL checks 数量与 constraints 不一致：{result}")
        normalized_checks = []
        for expected_constraint, check in zip(constraints, checks):
            if not isinstance(check, dict) or check.get("constraint") != expected_constraint:
                raise RuntimeError(f"Qwen3-VL check 未对应原始 constraint：{result}")
            status = check.get("status")
            if not isinstance(status, str) or status not in {
                "satisfied",
                "not_satisfied",
                "uncertain",
            }:
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
