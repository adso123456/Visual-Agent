import json
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
)

from visual_agent import deepseek_agent as da
from visual_agent import relations, transport, vlm
from visual_agent.deepseek_agent import DeepSeekAgent
from visual_agent.transport import request_with_transport_retry
from visual_agent.vlm_client import VlmConfig, create_vlm_client


def _status_error(error_type, status):
    response = httpx.Response(
        status,
        request=httpx.Request("POST", "http://provider.test/v1/chat/completions"),
    )
    return error_type(f"HTTP {status}", response=response, body=None)


def _response(*, content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class CompletionStub:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def create(self, **_kwargs):
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client(outcomes):
    completions = CompletionStub(outcomes)
    return SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
        completions_stub=completions,
    )


@pytest.mark.parametrize(
    "error",
    [
        _status_error(InternalServerError, 502),
        APITimeoutError(
            httpx.Request("POST", "http://provider.test/v1/chat/completions")
        ),
        APIConnectionError(
            request=httpx.Request(
                "POST", "http://provider.test/v1/chat/completions"
            )
        ),
        _status_error(RateLimitError, 429),
    ],
)
def test_retryable_transport_failure_recovers(error):
    outcomes = iter([error, "ok"])
    telemetry = []
    delays = []

    def request_once():
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    result = request_with_transport_retry(
        request_once,
        telemetry=telemetry,
        sleep=delays.append,
    )

    assert result == "ok"
    assert delays == [1.0]
    assert telemetry == [
        {
            "transport_attempts": 2,
            "transport_retry_count": 1,
            "transport_recovered": True,
            "first_transport_error": type(error).__name__,
            "first_http_status": getattr(error, "status_code", None),
            "final_transport_status": "success",
        }
    ]


def test_retryable_transport_failure_stops_after_three_attempts():
    errors = [
        _status_error(InternalServerError, 502),
        _status_error(InternalServerError, 503),
        _status_error(InternalServerError, 504),
    ]
    calls = 0
    telemetry = []

    def request_once():
        nonlocal calls
        error = errors[calls]
        calls += 1
        raise error

    with pytest.raises(InternalServerError) as caught:
        request_with_transport_retry(
            request_once,
            telemetry=telemetry,
            sleep=lambda _seconds: None,
        )

    assert calls == 3
    assert telemetry[0]["transport_attempts"] == 3
    assert telemetry[0]["transport_retry_count"] == 2
    assert telemetry[0]["transport_recovered"] is False
    assert telemetry[0]["first_http_status"] == 502
    assert telemetry[0]["final_transport_status"] == "retryable_failure_exhausted"
    assert caught.value.transport_telemetry == telemetry[0]


@pytest.mark.parametrize(
    ("error_type", "status"),
    [
        (BadRequestError, 400),
        (AuthenticationError, 401),
        (PermissionDeniedError, 403),
    ],
)
def test_non_retryable_4xx_fails_immediately(error_type, status):
    error = _status_error(error_type, status)
    calls = 0

    def request_once():
        nonlocal calls
        calls += 1
        raise error

    with pytest.raises(error_type) as caught:
        request_with_transport_retry(
            request_once,
            sleep=lambda _seconds: pytest.fail("普通 4xx 不得 sleep/retry"),
        )

    assert calls == 1
    assert caught.value.transport_telemetry["transport_attempts"] == 1
    assert caught.value.transport_telemetry["transport_retry_count"] == 0
    assert caught.value.transport_telemetry["final_transport_status"] == (
        "non_retryable_failure"
    )


def test_clients_explicitly_disable_sdk_retry():
    planner, *_ = da.build_planner_client(
        environ={
            "PLANNER_BASE_URL": "http://provider.test/v1",
            "PLANNER_API_KEY": "test",
        }
    )
    visual = create_vlm_client(
        VlmConfig(
            model="test-vlm",
            base_url="http://provider.test/v1",
            api_key="test",
            timeout=None,
        )
    )
    assert planner.max_retries == 0
    assert visual.max_retries == 0


def _planner_tool_call():
    arguments = {
        "target_object": "person",
        "label": "人",
        "constraints": [],
        "action": {"type": "highlight"},
        "related_objects": [],
    }
    return SimpleNamespace(
        function=SimpleNamespace(
            name=da.TOOL_NAME,
            arguments=json.dumps(arguments, ensure_ascii=False),
        )
    )


def _agent(outcomes):
    agent = DeepSeekAgent.__new__(DeepSeekAgent)
    agent.client = _client(outcomes)
    agent.model = "test-model"
    agent.base_url = "http://provider.test/v1"
    agent.provider = "openai_compatible"
    agent.plan_attempts = 0
    agent.plan_transport_calls = []
    agent.final_response_transport_calls = []
    return agent


def test_planner_path_uses_transport_retry(monkeypatch):
    monkeypatch.setattr(transport.time, "sleep", lambda _seconds: None)
    agent = _agent(
        [
            _status_error(InternalServerError, 502),
            _response(tool_calls=[_planner_tool_call()]),
        ]
    )

    plan = agent.plan_request("找到人")

    assert plan["target_object"] == "person"
    assert agent.client.completions_stub.calls == 2
    assert agent.planner_transport_telemetry()["transport_recovered"] is True


def test_final_response_path_uses_transport_retry(monkeypatch):
    monkeypatch.setattr(transport.time, "sleep", lambda _seconds: None)
    agent = _agent(
        [
            APITimeoutError(
                httpx.Request(
                    "POST", "http://provider.test/v1/chat/completions"
                )
            ),
            _response(content="完成"),
        ]
    )

    assert agent.build_final_response("找到人", {"targets_count": 1}) == "完成"
    metadata = agent.final_response_transport_telemetry()
    assert metadata["transport_attempts"] == 2
    assert metadata["transport_retry_count"] == 1
    assert metadata["transport_recovered"] is True


def test_vlm_contract_retry_keeps_transport_budget_separate(monkeypatch):
    monkeypatch.setattr(transport.time, "sleep", lambda _seconds: None)
    invalid_contract = _response(content='{"candidate_id":"A"}')
    valid_contract = _response(
        content=json.dumps(
            {
                "candidate_id": "A",
                "target_object": "person",
                "status": "valid",
                "evidence": "可确认是完整人物实例",
            },
            ensure_ascii=False,
        )
    )
    client = _client([invalid_contract, valid_contract])
    monkeypatch.setattr(vlm, "_client", lambda: client)

    _, protocol = vlm.verify_subject_instance(
        {"id": "A"},
        "person",
        Image.new("RGB", (16, 16), "white"),
    )

    assert protocol["attempts"] == 2
    assert protocol["retry_count"] == 1
    assert protocol["recovered"] is True
    assert protocol["transport_attempts"] == 2
    assert protocol["transport_retry_count"] == 0
    assert protocol["transport_recovered"] is False


def test_relation_vlm_path_uses_transport_retry(monkeypatch, tmp_path):
    monkeypatch.setattr(transport.time, "sleep", lambda _seconds: None)
    image_path = tmp_path / "scene.png"
    Image.new("RGB", (32, 32), "white").save(image_path)
    valid = _response(
        content=json.dumps(
            {
                "bindings": [
                    {
                        "subject_id": "A",
                        "related_id": "R1",
                        "relation": "held_by_target",
                        "status": "uncertain",
                        "evidence": "证据不足",
                    }
                ]
            },
            ensure_ascii=False,
        )
    )
    client = _client([_status_error(RateLimitError, 429), valid])
    monkeypatch.setattr(relations, "_client", lambda: client)

    _, protocol = relations.verify_relations(
        image_path,
        [{"id": "A", "bbox": [0, 0, 16, 32]}],
        [{"id": "R1", "bbox": [16, 8, 31, 24]}],
        "fish",
        "held_by_target",
    )

    assert protocol["transport_attempts"] == 2
    assert protocol["transport_retry_count"] == 1
    assert protocol["transport_recovered"] is True
    assert protocol["first_http_status"] == 429
