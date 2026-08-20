import json
from types import SimpleNamespace

import pytest
from PIL import Image

from visual_agent import vlm


CANDIDATE = {"id": "A", "bbox": [1, 2, 9, 12]}
ATTRIBUTE_CONSTRAINTS = [
    {"text": "穿红色衣服", "route": "attribute"},
    {"text": "戴眼镜", "route": "attribute"},
]


class _Completions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.responses.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class _Client:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=_Completions(responses))


def _evidence():
    return Image.new("RGB", (12, 16), (128, 128, 128))


@pytest.mark.parametrize("status", ["valid", "invalid", "uncertain"])
def test_validate_subject_instance_accepts_three_states(status):
    result = {
        "candidate_id": "A",
        "target_object": "person",
        "status": status,
        "evidence": "可见证据",
    }
    assert vlm.validate_subject_instance(result, CANDIDATE, "person")["status"] == status


@pytest.mark.parametrize(
    "result",
    [
        {"candidate_id": "B", "target_object": "person", "status": "valid", "evidence": "证据"},
        {"candidate_id": "A", "target_object": "dog", "status": "valid", "evidence": "证据"},
        {"candidate_id": "A", "target_object": "person", "status": "satisfied", "evidence": "证据"},
        {"candidate_id": "A", "target_object": "person", "status": "valid", "evidence": ""},
        {"candidate_id": "A", "target_object": "person", "status": "valid", "evidence": "证据", "extra": True},
    ],
)
def test_validate_subject_instance_rejects_schema_errors(result):
    with pytest.raises(RuntimeError):
        vlm.validate_subject_instance(result, CANDIDATE, "person")


def test_validate_routed_checks_preserves_multiple_constraints():
    result = {
        "candidate_id": "A",
        "checks": [
            {"constraint": "穿红色衣服", "status": "satisfied", "evidence": "红衣"},
            {"constraint": "戴眼镜", "status": "uncertain", "evidence": "面部不清"},
        ],
    }
    checks = vlm.validate_candidate_constraints(
        result,
        CANDIDATE,
        ATTRIBUTE_CONSTRAINTS,
        "attribute",
    )
    assert [item["constraint"] for item in checks] == ["穿红色衣服", "戴眼镜"]
    assert [item["status"] for item in checks] == ["satisfied", "uncertain"]


def test_routed_validator_rejects_cross_route_constraints():
    with pytest.raises(ValueError, match="route"):
        vlm.validate_candidate_constraints(
            {"candidate_id": "A", "checks": []},
            CANDIDATE,
            [{"text": "正在跑步", "route": "behavior"}],
            "attribute",
        )


def test_validity_request_contains_no_user_semantics_and_does_not_retry_semantics(monkeypatch):
    response = json.dumps(
        {
            "candidate_id": "A",
            "target_object": "person",
            "status": "uncertain",
            "evidence": "实例证据不足",
        },
        ensure_ascii=False,
    )
    client = _Client([response])
    monkeypatch.setattr(vlm, "_client", lambda: client)

    result, metadata = vlm.verify_subject_instance(CANDIDATE, "person", _evidence())

    assert result["status"] == "uncertain"
    assert metadata["attempts"] == 1
    assert len(client.chat.completions.calls) == 1
    request_text = json.dumps(
        client.chat.completions.calls[0]["messages"], ensure_ascii=False
    )
    assert "穿红色衣服" not in request_text
    assert "held_by_target" not in request_text
    assert "related_object" not in request_text


def test_routed_request_groups_same_route_and_retries_only_invalid_schema(monkeypatch):
    valid = json.dumps(
        {
            "candidate_id": "A",
            "checks": [
                {"constraint": "穿红色衣服", "status": "satisfied", "evidence": "红衣"},
                {"constraint": "戴眼镜", "status": "not_satisfied", "evidence": "未见眼镜"},
            ],
        },
        ensure_ascii=False,
    )
    client = _Client([json.dumps({"checks": []}), valid])
    monkeypatch.setattr(vlm, "_client", lambda: client)

    checks, metadata = vlm.verify_candidate_constraints(
        CANDIDATE,
        ATTRIBUTE_CONSTRAINTS,
        _evidence(),
        "attribute",
    )

    assert len(checks) == 2
    assert metadata["attempts"] == 2
    assert metadata["retry_count"] == 1
    assert len(client.chat.completions.calls) == 2
    assert "FORMAT CORRECTION ONLY" in json.dumps(
        client.chat.completions.calls[1]["messages"], ensure_ascii=False
    )


def test_behavior_prompt_preserves_frozen_evidence_contract(monkeypatch):
    response = json.dumps(
        {
            "candidate_id": "A",
            "checks": [
                {"constraint": "正在钓鱼", "status": "satisfied", "evidence": "姿态与鱼竿可见"}
            ],
        },
        ensure_ascii=False,
    )
    client = _Client([response])
    monkeypatch.setattr(vlm, "_client", lambda: client)

    vlm.verify_candidate_constraints(
        CANDIDATE,
        [{"text": "正在钓鱼", "route": "behavior"}],
        _evidence(),
        "behavior",
    )

    request_text = json.dumps(
        client.chat.completions.calls[0]["messages"], ensure_ascii=False
    )
    assert "可以使用当前局部图中与该人物直接相关的物体、姿态和交互上下文作为证据" in request_text
    assert "行为判断只能归属于当前轮廓对应的人物" in request_text
    assert "不得把附近其他人物的行为归给当前人物" in request_text
    assert "证据不足或归属不清必须 uncertain" in request_text
    assert "必须看到明确手握" not in request_text
    assert "必须看到直接接触" not in request_text
    assert "必须看到完整动作链" not in request_text
