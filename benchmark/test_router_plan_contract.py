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
