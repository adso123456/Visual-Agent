import json
import os
import re

from openai import OpenAI


MODEL_NAME = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com"
TOOL_NAME = "execute_visual_task"
ACTION_TYPES = {"highlight", "outline", "blur_target", "dim_background", "cutout"}

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
                    "items": {"type": "string"},
                    "description": "基础实体之外、需要视觉验证的中文语义约束。",
                },
                "action": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": sorted(ACTION_TYPES),
                        }
                    },
                    "required": ["type"],
                    "additionalProperties": False,
                },
            },
            "required": ["target_object", "label", "constraints", "action"],
            "additionalProperties": False,
        },
    },
}

PLANNER_SYSTEM_PROMPT = (
    "你是 Visual Agent 的语言规划器。你看不到图片，只能根据用户原始文本规划，"
    "不得猜测图片内容、目标数量、位置或视觉事实。必须且只能调用 execute_visual_task 一次。"
    "target_object 必须是 1 到 3 个英文单词组成的基础可检测实体，不能包含属性、行为或关系。"
    "男人、女人、男孩、女孩、儿童、老人、工人等所有人物类目标一律使用 person；"
    "人物子类、属性、行为和关系放入 constraints，例如儿童、女性、穿红色衣服、正在钓鱼、手持雨伞。"
    "constraints 只保留基础实体之外的用户语义，不得重复人、人物或 person，也不得加入图片操作。"
    "action.type 只能使用工具 schema 的白名单：找到、定位、标红或高亮使用 highlight；"
    "只描边使用 outline；模糊目标使用 blur_target；目标以外背景变暗使用 dim_background；"
    "单独抠出使用 cutout。不得生成图像参数、代码或命令。label 使用简短中文目标名。"
)

FINAL_SYSTEM_PROMPT = (
    "你是 Visual Agent 的结果汇总器。只能根据提供的已执行计划和结构化视觉结果，"
    "生成一句简短中文回答。不得增加结果中没有的视觉事实，不得猜身份、年龄、地点、颜色或数量，"
    "不得声称执行了不存在的动作。如果 targets_count 为 0，必须明确没有找到满足条件的目标。"
    "你不能修改计划、候选、验证结论、动作或触发重新执行。只输出给用户的最终回答。"
)


class DeepSeekAgent:
    def __init__(self) -> None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("未设置环境变量 DEEPSEEK_API_KEY")
        self.client = OpenAI(api_key=api_key, base_url=BASE_URL)
        self.plan_attempts = 0

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
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=[EXECUTE_VISUAL_TASK_TOOL],
                tool_choice={"type": "function", "function": {"name": TOOL_NAME}},
                max_tokens=1024,
                extra_body={"thinking": {"type": "disabled"}},
            )
            try:
                return self._validated_plan(response.choices[0].message.tool_calls)
            except (json.JSONDecodeError, RuntimeError) as error:
                validation_error = str(error)
        raise RuntimeError(f"DeepSeek Planner 两次均违反契约：{validation_error}")

    def build_final_response(self, prompt: str, visual_result: dict) -> str:
        response = self.client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": FINAL_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"prompt": prompt, "tool_result": visual_result},
                        ensure_ascii=False,
                    ),
                },
            ],
            max_tokens=256,
            extra_body={"thinking": {"type": "disabled"}},
        )
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("DeepSeek Final Response 返回了空内容")
        return content.strip()

    @staticmethod
    def _validated_plan(tool_calls: list | None) -> dict:
        if not tool_calls or len(tool_calls) != 1:
            raise RuntimeError("必须且只能返回一个 tool call")
        tool_call = tool_calls[0]
        if tool_call.function.name != TOOL_NAME:
            raise RuntimeError(f"tool name 必须为 {TOOL_NAME}")
        arguments = json.loads(tool_call.function.arguments)
        if not isinstance(arguments, dict):
            raise RuntimeError("tool arguments 必须是 JSON 对象")
        if set(arguments) != {"target_object", "label", "constraints", "action"}:
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
        if not isinstance(constraints, list) or any(
            not isinstance(item, str) or not item.strip() for item in constraints
        ):
            raise RuntimeError("constraints 必须是非空字符串组成的数组")
        constraints = [item.strip() for item in constraints]
        if target_object == "person" and any(
            item.lower() in {"人", "人物", "person"} for item in constraints
        ):
            raise RuntimeError("person 的 constraints 不得重复基础人物实体")

        action = arguments["action"]
        if (
            not isinstance(action, dict)
            or set(action) != {"type"}
            or action.get("type") not in ACTION_TYPES
        ):
            raise RuntimeError("action 只能包含白名单 type")
        return {
            "target_object": target_object,
            "label": label.strip(),
            "constraints": constraints,
            "action": {"type": action["type"]},
        }
