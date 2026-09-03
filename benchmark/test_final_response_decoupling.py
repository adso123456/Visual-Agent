import json
from types import SimpleNamespace

import cv2
import httpx
import numpy as np
from openai import InternalServerError

from visual_agent import pipeline, transport
from visual_agent.deepseek_agent import (
    FINAL_RESPONSE_EMPTY_CORRECTION,
    DeepSeekAgent,
)


class CompletionStub:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        outcome = self.outcomes[len(self.calls)]
        self.calls.append(kwargs)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _response(*, content=None):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _status_error(error_type, status):
    response = httpx.Response(
        status,
        request=httpx.Request("POST", "http://provider.test/v1/chat/completions"),
    )
    return error_type(f"HTTP {status}", response=response, body=None)


def _agent(outcomes):
    completions = CompletionStub(outcomes)
    agent = DeepSeekAgent.__new__(DeepSeekAgent)
    agent.client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    agent.model = "qwen3.8:27b-mtp-q4_K_M"
    agent.base_url = "http://provider.test/v1"
    agent.provider = "openai_compatible"
    agent.plan_attempts = 0
    agent.plan_transport_calls = []
    agent.final_response_transport_calls = []
    return agent, completions


def test_empty_final_response_retries_once_and_recovers():
    agent, completions = _agent(
        [_response(content=""), _response(content=" 已完成 ")]
    )

    result = agent.build_final_response("找到人", {"targets_count": 1})

    assert result == "已完成"
    assert len(completions.calls) == 2
    assert completions.calls[0]["model"] == "qwen3.8:27b-mtp-q4_K_M"
    assert not any(
        message.get("content") == FINAL_RESPONSE_EMPTY_CORRECTION
        for message in completions.calls[0]["messages"]
    )
    assert any(
        message.get("content") == FINAL_RESPONSE_EMPTY_CORRECTION
        for message in completions.calls[1]["messages"]
    )
    assert agent.final_response_content_telemetry() == {
        "content_attempts": 2,
        "content_retry_count": 1,
        "content_recovered": True,
        "first_content_error": "empty_response",
        "final_content_status": "success",
    }
    assert agent.final_response_transport_telemetry()["transport_attempts"] == 2
    assert agent.final_response_transport_telemetry()["transport_retry_count"] == 0


def test_two_empty_final_responses_return_explicit_failure():
    agent, completions = _agent(
        [_response(content=None), _response(content="   ")]
    )

    result = agent.build_final_response("找到人", {"targets_count": 1})

    assert result is None
    assert len(completions.calls) == 2
    assert agent.final_response_content_telemetry() == {
        "content_attempts": 2,
        "content_retry_count": 1,
        "content_recovered": False,
        "first_content_error": "empty_response",
        "final_content_status": "failed_empty_response",
    }


def test_content_retry_has_its_own_transport_budget(monkeypatch):
    monkeypatch.setattr(transport.time, "sleep", lambda _seconds: None)
    agent, completions = _agent(
        [
            _response(content=""),
            _status_error(InternalServerError, 502),
            _response(content="完成"),
        ]
    )

    assert agent.build_final_response("找到人", {"targets_count": 1}) == "完成"
    assert len(completions.calls) == 3
    content = agent.final_response_content_telemetry()
    transport_metadata = agent.final_response_transport_telemetry()
    assert content["content_attempts"] == 2
    assert content["content_retry_count"] == 1
    assert content["content_recovered"] is True
    assert transport_metadata["transport_attempts"] == 3
    assert transport_metadata["transport_retry_count"] == 1
    assert transport_metadata["transport_recovered"] is True


class DetectorStub:
    device = "cpu"
    load_seconds = 0.0
    memory_after_load_mb = 0.0

    def detect(self, _image_path, target_text, threshold=0.3):
        return [
            {
                "bbox": [4.0, 4.0, 20.0, 28.0],
                "text_label": target_text,
                "confidence": 0.9,
            }
        ]


def test_pipeline_preserves_artifacts_when_final_response_stays_empty(
    tmp_path,
    monkeypatch,
):
    image_path = tmp_path / "input.jpg"
    cv2.imwrite(str(image_path), np.zeros((32, 32, 3), dtype=np.uint8))
    agent, completions = _agent(
        [_response(content=""), _response(content=None)]
    )

    class AgentFactory(DeepSeekAgent):
        def __new__(cls):
            return agent

    monkeypatch.setattr(pipeline, "DeepSeekAgent", AgentFactory)
    monkeypatch.setattr(
        pipeline,
        "get_detector",
        lambda fresh=False: (DetectorStub(), True),
    )

    image_output, json_output = pipeline.run_pipeline(
        image_path,
        "框出人",
        plan={
            "target_object": "person",
            "label": "人",
            "constraints": [],
            "action": {"type": "box"},
            "related_objects": [],
        },
        verify=False,
        final_response=True,
        output_dir=tmp_path / "output",
    )

    saved = json.loads(json_output.read_text(encoding="utf-8"))
    assert len(completions.calls) == 2
    assert image_output.is_file()
    assert json_output.is_file()
    assert saved["agent_response"] is None
    assert saved["targets"]
    assert saved["agent"]["final_response_content"] == {
        "content_attempts": 2,
        "content_retry_count": 1,
        "content_recovered": False,
        "first_content_error": "empty_response",
        "final_content_status": "failed_empty_response",
    }
    assert saved["agent"]["final_response_transport"][
        "transport_attempts"
    ] == 2
