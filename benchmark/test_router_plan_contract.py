import json
from types import SimpleNamespace

import pytest

from visual_agent.deepseek_agent import DeepSeekAgent, TOOL_NAME


def _tool_call(plan: dict):
    return SimpleNamespace(
        function=SimpleNamespace(
            name=TOOL_NAME,
            arguments=json.dumps(plan, ensure_ascii=False),
        )
    )


def _plan(constraints: list[dict], related_objects: list[dict] | None = None) -> dict:
    return {
        "target_object": "person",
        "label": "测试目标",
        "constraints": constraints,
        "action": {"type": "outline"},
        "related_objects": related_objects or [],
    }


def _validate(plan: dict) -> dict:
    return DeepSeekAgent._validated_plan([_tool_call(plan)])


def _validate_with_prompt(plan: dict, prompt: str) -> dict:
    return DeepSeekAgent._validated_plan([_tool_call(plan)], prompt=prompt)


def _must_fail(plan: dict, expected: str) -> None:
    with pytest.raises(RuntimeError, match=expected):
        _validate(plan)


def test_typed_constraints_preserve_order_and_routes():
    constraints = [
        {"text": "穿红色衣服", "route": "attribute"},
        {"text": "正在跑步", "route": "behavior"},
    ]
    assert _validate(_plan(constraints))["constraints"] == constraints


@pytest.mark.parametrize("route", ["attribute", "behavior"])
def test_non_relation_routes_are_accepted(route):
    assert _validate(_plan([{"text": "测试约束", "route": route}]))[
        "constraints"
    ][0]["route"] == route


def test_relation_constraint_has_exactly_one_related_object():
    related = [{"object": "umbrella", "relation": "held_by_target"}]
    plan = _plan([{"text": "拿着雨伞", "route": "relation"}], related)
    assert _validate(plan) == plan


@pytest.mark.parametrize(
    ("constraint", "message"),
    [
        ({"text": "穿红衣服"}, "route"),
        ({"text": "穿红衣服", "route": "unknown"}, "route"),
        ({"text": "", "route": "attribute"}, "text"),
        ({"text": "穿红衣服", "route": "attribute", "extra": True}, "字段"),
    ],
)
def test_invalid_typed_constraint_is_rejected(constraint, message):
    _must_fail(_plan([constraint]), message)


def test_legacy_string_constraint_is_rejected():
    _must_fail(_plan(["穿红衣服"]), "constraint")


def test_relation_without_related_object_is_rejected():
    _must_fail(_plan([{"text": "拿着雨伞", "route": "relation"}]), "1:1")


def test_related_object_without_relation_constraint_is_rejected():
    _must_fail(
        _plan(
            [{"text": "穿红衣服", "route": "attribute"}],
            [{"object": "umbrella", "relation": "held_by_target"}],
        ),
        "1:1",
    )


def test_multiple_relation_constraints_are_rejected():
    _must_fail(
        _plan(
            [
                {"text": "拿着雨伞", "route": "relation"},
                {"text": "撑着雨伞", "route": "relation"},
            ],
            [{"object": "umbrella", "relation": "held_by_target"}],
        ),
        "1:1",
    )


@pytest.mark.parametrize("marker", ["手持", "拿着", "撑着"])
def test_explicit_held_by_prompt_requires_canonical_relation_route(marker):
    invalid = _plan([{"text": f"{marker}雨伞", "route": "behavior"}])
    with pytest.raises(RuntimeError, match="held_by_target"):
        _validate_with_prompt(invalid, f"框出{marker}雨伞的人")

    valid = _plan(
        [{"text": f"{marker}雨伞", "route": "relation"}],
        [{"object": "umbrella", "relation": "held_by_target"}],
    )
    assert _validate_with_prompt(valid, f"框出{marker}雨伞的人") == valid


def test_non_held_behavior_prompt_is_not_forced_into_relation():
    plan = _plan([{"text": "正在钓鱼", "route": "behavior"}])
    assert _validate_with_prompt(plan, "框出正在钓鱼的人") == plan


def test_planner_retries_invalid_held_by_route_and_accepts_canonical_correction():
    invalid = _plan([{"text": "拿着雨伞", "route": "behavior"}])
    valid = _plan(
        [{"text": "拿着雨伞", "route": "relation"}],
        [{"object": "umbrella", "relation": "held_by_target"}],
    )
    responses = [invalid, valid]
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        tool_calls=[_tool_call(responses.pop(0))]
                    )
                )
            ]
        )

    agent = DeepSeekAgent.__new__(DeepSeekAgent)
    agent.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create)
        )
    )
    agent.plan_attempts = 0

    assert agent.plan_request("框出拿着雨伞的人") == valid
    assert agent.plan_attempts == 2
    assert "held_by_target" in json.dumps(
        calls[1]["messages"],
        ensure_ascii=False,
    )
