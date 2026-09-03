import json
from types import SimpleNamespace

from visual_agent import deepseek_agent as da
from visual_agent.deepseek_agent import DeepSeekAgent


def _tool_call(arguments: dict):
    return SimpleNamespace(
        function=SimpleNamespace(
            name=da.TOOL_NAME,
            arguments=json.dumps(arguments, ensure_ascii=False),
        )
    )


def _response(arguments: dict):
    message = SimpleNamespace(tool_calls=[_tool_call(arguments)])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _plan(constraints, related_objects):
    return {
        "target_object": "person",
        "label": "人",
        "constraints": constraints,
        "action": {"type": "outline"},
        "related_objects": related_objects,
    }


def test_qwen_uses_ollama_supported_reasoning_controls():
    assert da._completion_controls("qwen3.8:27b-mtp-q4_K_M") == {
        "reasoning_effort": "none",
        "temperature": 0,
        "seed": 0,
    }


def test_non_qwen_keeps_existing_thinking_control():
    assert da._completion_controls("deepseek-v4-pro") == {
        "extra_body": {"thinking": {"type": "disabled"}}
    }


def test_planner_correction_includes_previous_invalid_tool_call():
    invalid = _plan(
        [{"text": "拿着鱼", "route": "behavior"}],
        [],
    )
    valid = _plan(
        [{"text": "拿着鱼", "route": "relation"}],
        [{"object": "fish", "relation": "held_by_target"}],
    )
    responses = [_response(invalid), _response(valid)]
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    agent = DeepSeekAgent.__new__(DeepSeekAgent)
    agent.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create)
        )
    )
    agent.model = "qwen3.8:27b-mtp-q4_K_M"
    agent.plan_attempts = 0

    assert agent.plan_request("把拿着鱼的人标出来") == valid
    correction = calls[1]["messages"][1]["content"]
    assert "上一次工具调用" in correction
    assert "behavior" in correction
    assert "held_by_target" in correction
    assert all(call["reasoning_effort"] == "none" for call in calls)
    assert all(call["temperature"] == 0 for call in calls)
    assert all(call["seed"] == 0 for call in calls)


def test_planner_prompt_gives_held_relation_precedence_and_supports_fish():
    assert "不得把该手持语义路由为 behavior，必须优先使用 relation" in da.PLANNER_SYSTEM_PROMPT
    assert "包括鱼、鱼竿、雨伞等物体" in da.PLANNER_SYSTEM_PROMPT


def test_final_prompt_defines_mixed_complete_and_incomplete_state():
    assert "complete_semantic_targets_count 大于 0" in da.FINAL_SYSTEM_PROMPT
    assert "incomplete_semantic_groups 只表示其他候选未完成" in da.FINAL_SYSTEM_PROMPT
    assert "不得因此否定已执行操作" in da.FINAL_SYSTEM_PROMPT
