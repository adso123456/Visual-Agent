import json
import os
import re
from collections.abc import Mapping

from openai import OpenAI

from visual_agent.transport import (
    merge_transport_telemetry,
    request_with_transport_retry,
)


PLANNER_MODEL_ENV = "PLANNER_MODEL"
PLANNER_BASE_URL_ENV = "PLANNER_BASE_URL"
PLANNER_API_KEY_ENV = "PLANNER_API_KEY"
DEFAULT_PLANNER_MODEL = "deepseek-v4-pro"
DEFAULT_PLANNER_BASE_URL = "https://api.deepseek.com"
MODEL_NAME = DEFAULT_PLANNER_MODEL
BASE_URL = DEFAULT_PLANNER_BASE_URL
TOOL_NAME = "execute_visual_task"
ACTION_TYPES = {"highlight", "outline", "box", "blur_target", "dim_background", "cutout"}
CONSTRAINT_ROUTES = {"attribute", "behavior", "relation"}
HELD_BY_PROMPT_MARKERS = ("手持", "拿着", "撑着")
FINAL_RESPONSE_MAX_CONTENT_ATTEMPTS = 2

EXECUTE_VISUAL_TASK_TOOL = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "把用户的自然语言图片请求转换为受控视觉任务计划。",
        "parameters": {
            "type": "object",
            "properties": {
                "target_object": {
                    "type": "string",
                    "description": "英文基础可检测实体，人物统一使用 person。",
                },
                "label": {"type": "string", "description": "简短中文目标名称。"},
                "constraints": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "minLength": 1},
                            "route": {
                                "type": "string",
                                "enum": sorted(CONSTRAINT_ROUTES),
                            },
                        },
                        "required": ["text", "route"],
                        "additionalProperties": False,
                    },
                    "description": "按用户原顺序排列的原子中文语义约束及其视觉证据路由。",
                },
                "action": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": sorted(ACTION_TYPES),
                        },
                        "color": {
                            "type": "string",
                            "pattern": "^#[0-9A-Fa-f]{6}$",
                            "description": "仅 box、outline、highlight 可用；用户指定颜色时输出 #RRGGBB。",
                        },
                    },
                    "required": ["type"],
                    "additionalProperties": False,
                },
                "related_objects": {
                    "type": "array",
                    "maxItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "object": {"type": "string"},
                            "relation": {
                                "type": "string",
                                "enum": ["held_by_target"],
                            },
                        },
                        "required": ["object", "relation"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": [
                "target_object",
                "label",
                "constraints",
                "action",
                "related_objects",
            ],
            "additionalProperties": False,
        },
    },
}

PLANNER_SYSTEM_PROMPT = (
    "你是 Visual Agent 的语言规划器。你看不到图片，只能根据用户原始文本规划，"
    "不得猜测图片内容、目标数量、位置或视觉事实。必须且只能调用 execute_visual_task 一次。"
    "target_object 必须是 1 到 3 个英文单词组成的基础可检测实体，不能包含属性、行为或关系。"
    "男人、女人、男孩、女孩、儿童、老人、工人等所有人物类目标一律使用 person；"
    "人物子类、属性、行为和关系放入 constraints。每条原子语义必须单独输出 text 和 route，"
    "并严格保持用户语义原顺序。route 只表示该约束需要的视觉证据，不表示语义判断结果。"
    "attribute 用于依赖目标本人即可判断的外观或属性，例如儿童、女性、穿红衣、戴眼镜、戴帽子；"
    "behavior 用于需要目标附近姿态、物体、交互或局部上下文的语义，例如钓鱼、骑车、打电话、跑步；"
    "relation 当前只能用于受支持的 held_by_target 手持关系。constraints 不得重复人、人物或 person，"
    "也不得加入图片操作。"
    "action.type 只能使用工具 schema 的白名单：找到、定位、标红或高亮使用 highlight；"
    "框出、框选或框起来使用 box；只描边使用 outline；用户明确指定框选、描边或高亮颜色时，"
    "在 action.color 中输出对应的 #RRGGBB，未指定颜色时不得输出 color；color 只能与 box、"
    "outline 或 highlight 同时使用。"
    "目标以外背景变暗使用 dim_background；"
    "单独抠出使用 cutout。不得生成图像参数、代码或命令。label 使用简短中文目标名。"
    "related_objects 始终必填。仅当用户要求人物明确手持、拿着或撑着一个无生命手持物体时，"
    "返回一个基础英文物体和 relation=held_by_target；否则必须返回空数组。生成关联物体时，"
    "constraints 必须恰好包含一条 route=relation 的完整关系语义，与 related_objects[0] 形成 1:1 ownership。"
    "没有关联物体时不得输出 relation route。骑自行车、戴安全帽、靠近汽车、抱着狗等关系不受支持，"
    "必须 related_objects=[]，不得映射为 held_by_target。"
)

FINAL_SYSTEM_PROMPT = (
    "你是 Visual Agent 的结果汇总器。只能根据提供的已执行计划和结构化视觉结果，"
    "生成一句简短中文回答。不得增加结果中没有的视觉事实，不得猜身份、年龄、地点、颜色或数量，"
    "不得声称执行了不存在的动作。如果 complete_semantic_targets_count 为 0、但 incomplete_semantic_groups 非空，"
    "必须根据其中的 completion_reason 说明主体候选的关系语义不完整，因此没有执行图片操作；"
    "不能说没有找到目标。只有 incomplete_semantic_groups 也为空时，才明确没有找到满足条件的目标。"
    "你不能修改计划、候选、验证结论、动作或触发重新执行。只输出给用户的最终回答。"
)

FINAL_RESPONSE_EMPTY_CORRECTION = (
    "上一次最终回答为空。请基于完全相同的已执行计划和结构化视觉结果，"
    "重新输出一句简短中文回答；不得修改或补充视觉事实。"
)


def _not_started_final_response_content_telemetry() -> dict:
    return {
        "content_attempts": 0,
        "content_retry_count": 0,
        "content_recovered": False,
        "first_content_error": None,
        "final_content_status": "not_started",
    }


def build_planner_client(
    environ: Mapping[str, str] | None = None,
) -> tuple[OpenAI, str, str, str]:
    """Agent LLM 最小可配置 seam：PLANNER_MODEL / PLANNER_BASE_URL / PLANNER_API_KEY。

    该 seam 同时决定 Planner（plan_request）与 Final Response（build_final_response）
    的 provider/model —— 两者共用同一可配置模型，避免“Planner seam”隐式改变 Final Response。

    安全边界与 VLM seam 一致：
    - PLANNER_BASE_URL == 默认 DeepSeek：可使用 PLANNER_API_KEY 或 DEEPSEEK_API_KEY；
    - PLANNER_BASE_URL != 默认 DeepSeek：必须显式 PLANNER_API_KEY，
      禁止回退 DEEPSEEK_API_KEY（不得把 DeepSeek 密钥发送到自定义端点）。
    """
    values = os.environ if environ is None else environ
    model = values.get(PLANNER_MODEL_ENV, "").strip() or DEFAULT_PLANNER_MODEL
    base_url = (
        values.get(PLANNER_BASE_URL_ENV, "").strip() or DEFAULT_PLANNER_BASE_URL
    )
    explicit_api_key = values.get(PLANNER_API_KEY_ENV, "").strip()
    deepseek_api_key = values.get("DEEPSEEK_API_KEY", "").strip()
    if base_url.rstrip("/") == DEFAULT_PLANNER_BASE_URL.rstrip("/"):
        api_key = explicit_api_key or deepseek_api_key
    else:
        if not explicit_api_key:
            raise RuntimeError(
                "非默认 PLANNER_BASE_URL 必须显式设置 PLANNER_API_KEY，"
                "禁止回退 DEEPSEEK_API_KEY"
            )
        api_key = explicit_api_key
    if not api_key:
        raise RuntimeError("未设置环境变量 PLANNER_API_KEY 或 DEEPSEEK_API_KEY")
    provider = (
        "deepseek"
        if base_url.rstrip("/") == DEFAULT_PLANNER_BASE_URL.rstrip("/")
        else "openai_compatible"
    )
    return (
        OpenAI(api_key=api_key, base_url=base_url, max_retries=0),
        model,
        base_url,
        provider,
    )


class DeepSeekAgent:
    def __init__(self) -> None:
        self.client, self.model, self.base_url, self.provider = (
            build_planner_client()
        )
        self.plan_attempts = 0
        self.plan_transport_calls: list[dict] = []
        self.final_response_transport_calls: list[dict] = []
        self.final_response_content = (
            _not_started_final_response_content_telemetry()
        )

    def plan_request(self, prompt: str) -> dict:
        validation_error = None
        for attempt in range(1, 3):
            self.plan_attempts = attempt
            messages = [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}]
            if validation_error:
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "上一次工具调用违反契约。只修正以下错误并重新调用工具："
                            f"{validation_error}"
                        ),
                    }
                )
            messages.append({"role": "user", "content": prompt})
            transport_calls = getattr(self, "plan_transport_calls", None)
            if transport_calls is None:
                transport_calls = []
                self.plan_transport_calls = transport_calls
            response = request_with_transport_retry(
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=[EXECUTE_VISUAL_TASK_TOOL],
                    tool_choice={
                        "type": "function",
                        "function": {"name": TOOL_NAME},
                    },
                    max_tokens=1024,
                    extra_body={"thinking": {"type": "disabled"}},
                ),
                telemetry=transport_calls,
            )
            try:
                return self._validated_plan(
                    response.choices[0].message.tool_calls,
                    prompt=prompt,
                )
            except (json.JSONDecodeError, RuntimeError) as error:
                validation_error = str(error)
        raise RuntimeError(f"DeepSeek Planner 两次均违反契约：{validation_error}")

    def build_final_response(
        self,
        prompt: str,
        visual_result: dict,
    ) -> str | None:
        self.final_response_transport_calls = []
        first_content_error = None
        for attempt in range(1, FINAL_RESPONSE_MAX_CONTENT_ATTEMPTS + 1):
            messages = [{"role": "system", "content": FINAL_SYSTEM_PROMPT}]
            if attempt > 1:
                messages.append(
                    {"role": "system", "content": FINAL_RESPONSE_EMPTY_CORRECTION}
                )
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {"prompt": prompt, "tool_result": visual_result},
                        ensure_ascii=False,
                    ),
                }
            )
            response = request_with_transport_retry(
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=256,
                    extra_body={"thinking": {"type": "disabled"}},
                ),
                telemetry=self.final_response_transport_calls,
            )
            content = response.choices[0].message.content
            if isinstance(content, str) and content.strip():
                self.final_response_content = {
                    "content_attempts": attempt,
                    "content_retry_count": attempt - 1,
                    "content_recovered": attempt > 1,
                    "first_content_error": first_content_error,
                    "final_content_status": "success",
                }
                return content.strip()
            if first_content_error is None:
                first_content_error = "empty_response"

        self.final_response_content = {
            "content_attempts": FINAL_RESPONSE_MAX_CONTENT_ATTEMPTS,
            "content_retry_count": FINAL_RESPONSE_MAX_CONTENT_ATTEMPTS - 1,
            "content_recovered": False,
            "first_content_error": first_content_error,
            "final_content_status": "failed_empty_response",
        }
        return None

    def planner_transport_telemetry(self) -> dict:
        return merge_transport_telemetry(
            getattr(self, "plan_transport_calls", [])
        )

    def final_response_transport_telemetry(self) -> dict:
        return merge_transport_telemetry(
            getattr(self, "final_response_transport_calls", [])
        )

    def final_response_content_telemetry(self) -> dict:
        return getattr(
            self,
            "final_response_content",
            _not_started_final_response_content_telemetry(),
        )

    @staticmethod
    def _validated_plan(tool_calls: list | None, prompt: str | None = None) -> dict:
        if not tool_calls or len(tool_calls) != 1:
            raise RuntimeError("必须且只能返回一个 tool call")
        tool_call = tool_calls[0]
        if tool_call.function.name != TOOL_NAME:
            raise RuntimeError(f"tool name 必须为 {TOOL_NAME}")
        arguments = json.loads(tool_call.function.arguments)
        if not isinstance(arguments, dict):
            raise RuntimeError("tool arguments 必须是 JSON 对象")
        return DeepSeekAgent._validated_plan_arguments(arguments, prompt=prompt)

    @staticmethod
    def _validated_plan_arguments(
        arguments: dict,
        prompt: str | None = None,
    ) -> dict:
        """验证并规范化 Planner 或预编译 plan 的唯一正式契约。"""
        if not isinstance(arguments, dict):
            raise RuntimeError("plan 必须是 JSON 对象")
        if set(arguments) != {
            "target_object",
            "label",
            "constraints",
            "action",
            "related_objects",
        }:
            raise RuntimeError("tool arguments 顶层字段不正确")

        target_object = arguments["target_object"]
        if not isinstance(target_object, str) or not target_object.strip():
            raise RuntimeError("target_object 必须是非空字符串")
        target_object = target_object.strip().lower()
        words = target_object.split()
        if not 1 <= len(words) <= 3 or not all(re.fullmatch(r"[a-z]+", word) for word in words):
            raise RuntimeError("target_object 必须是 1 到 3 个英文单词")
        relation_words = {"with", "holding", "wearing", "using", "near"}
        if relation_words.intersection(words):
            raise RuntimeError("target_object 包含属性、行为或关系词")

        label = arguments["label"]
        if not isinstance(label, str) or not label.strip():
            raise RuntimeError("label 必须是非空字符串")
        constraints = arguments["constraints"]
        if not isinstance(constraints, list):
            raise RuntimeError("constraints 必须是 typed object 数组")
        normalized_constraints = []
        for constraint in constraints:
            if not isinstance(constraint, dict) or set(constraint) != {"text", "route"}:
                raise RuntimeError("constraint 字段必须且只能是 text 和 route")
            text = constraint["text"]
            route = constraint["route"]
            if not isinstance(text, str) or not text.strip():
                raise RuntimeError("constraint text 必须是非空字符串")
            if route not in CONSTRAINT_ROUTES:
                raise RuntimeError("constraint route 不在白名单")
            normalized_constraints.append({"text": text.strip(), "route": route})
        if target_object == "person" and any(
            item["text"].lower() in {"人", "人物", "person"}
            for item in normalized_constraints
        ):
            raise RuntimeError("person 的 constraints 不得重复基础人物实体")

        action = arguments["action"]
        if (
            not isinstance(action, dict)
            or not {"type"} <= set(action) <= {"type", "color"}
            or action.get("type") not in ACTION_TYPES
        ):
            raise RuntimeError("action 只能包含白名单 type 和可选 color")
        color = action.get("color")
        if color is not None and (
            action["type"] not in {"box", "outline", "highlight"}
            or not isinstance(color, str)
            or re.fullmatch(r"#[0-9a-fA-F]{6}", color) is None
        ):
            raise RuntimeError("action.color 只能是 box、outline 或 highlight 使用的 #RRGGBB")
        related_objects = arguments["related_objects"]
        if not isinstance(related_objects, list) or len(related_objects) > 1:
            raise RuntimeError("related_objects 必须是长度 0..1 的数组")
        normalized_related_objects = []
        for related in related_objects:
            if not isinstance(related, dict) or set(related) != {"object", "relation"}:
                raise RuntimeError("related object 只能包含 object 和 relation")
            related_object = related["object"]
            if not isinstance(related_object, str) or not related_object.strip():
                raise RuntimeError("related object 必须是非空字符串")
            related_object = related_object.strip().lower()
            related_words = related_object.split()
            if not 1 <= len(related_words) <= 3 or not all(
                re.fullmatch(r"[a-z]+", word) for word in related_words
            ):
                raise RuntimeError("related object 必须是 1 到 3 个英文单词")
            if related["relation"] != "held_by_target":
                raise RuntimeError("Phase 7 relation 只能是 held_by_target")
            normalized_related_objects.append(
                {"object": related_object, "relation": "held_by_target"}
            )
        relation_constraints = [
            item for item in normalized_constraints if item["route"] == "relation"
        ]
        if len(relation_constraints) != len(normalized_related_objects):
            raise RuntimeError(
                "relation constraint 与 related_objects 必须保持 1:1 ownership"
            )
        if (
            isinstance(prompt, str)
            and any(marker in prompt for marker in HELD_BY_PROMPT_MARKERS)
            and (
                len(relation_constraints) != 1
                or len(normalized_related_objects) != 1
                or normalized_related_objects[0]["relation"] != "held_by_target"
            )
        ):
            raise RuntimeError(
                "显式手持语义（手持/拿着/撑着）必须编译为 relation + held_by_target"
            )
        normalized_action = {"type": action["type"]}
        if color is not None:
            normalized_action["color"] = color.lower()
        return {
            "target_object": target_object,
            "label": label.strip(),
            "constraints": normalized_constraints,
            "action": normalized_action,
            "related_objects": normalized_related_objects,
        }
