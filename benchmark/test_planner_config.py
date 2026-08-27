"""PLANNER_SEAM_V1: DeepSeekAgent 端点/模型/密钥的 env 可配置合同。

安全边界与 VLM seam 一致：
- 默认 DeepSeek endpoint 允许 PLANNER_API_KEY 或 DEEPSEEK_API_KEY；
- 非默认 endpoint 必须显式 PLANNER_API_KEY，禁止回退 DEEPSEEK_API_KEY。
该 seam 同时决定 Planner 与 Final Response 的 provider/model（显式共用）。
"""

import json
from types import SimpleNamespace

import pytest

from visual_agent import deepseek_agent as da
from visual_agent.deepseek_agent import DeepSeekAgent


def test_planner_defaults_stay_frozen():
    assert da.DEFAULT_PLANNER_MODEL == "deepseek-v4-pro"
    assert da.DEFAULT_PLANNER_BASE_URL == "https://api.deepseek.com"
    assert da.MODEL_NAME == da.DEFAULT_PLANNER_MODEL
    assert da.BASE_URL == da.DEFAULT_PLANNER_BASE_URL


def test_planner_config_requires_api_key():
    with pytest.raises(RuntimeError, match="PLANNER_API_KEY 或 DEEPSEEK_API_KEY"):
        da.build_planner_client(environ={})


def test_planner_config_falls_back_to_deepseek_api_key():
    client, model, base_url, provider = da.build_planner_client(
        environ={"DEEPSEEK_API_KEY": "sk-deepseek"}
    )
    assert model == "deepseek-v4-pro"
    assert base_url == "https://api.deepseek.com"
    assert provider == "deepseek"
    assert str(client.base_url).rstrip("/") == "https://api.deepseek.com"


def test_planner_config_switches_to_local_qwen():
    client, model, base_url, provider = da.build_planner_client(
        environ={
            "PLANNER_MODEL": "qwen3.8:27b-mtp-q4_K_M",
            "PLANNER_BASE_URL": "http://192.168.250.9:11434/v1",
            "PLANNER_API_KEY": "ollama",
        }
    )
    assert model == "qwen3.8:27b-mtp-q4_K_M"
    assert base_url == "http://192.168.250.9:11434/v1"
    assert provider == "openai_compatible"
    assert str(client.base_url).rstrip("/") == "http://192.168.250.9:11434/v1"


def test_non_default_endpoint_must_explicitly_set_planner_api_key():
    # BLOCKING 修复：非默认端点 + 未设置 PLANNER_API_KEY + 存在 DEEPSEEK_API_KEY
    # 必须拒绝，不得把 DeepSeek 密钥发送到自定义端点。
    with pytest.raises(RuntimeError, match="PLANNER_API_KEY"):
        da.build_planner_client(
            environ={
                "PLANNER_BASE_URL": "http://192.168.250.9:11434/v1",
                "DEEPSEEK_API_KEY": "sk-deepseek-secret",
            }
        )


def test_non_default_endpoint_uses_explicit_key_not_deepseek_fallback():
    client, _model, _base_url, provider = da.build_planner_client(
        environ={
            "PLANNER_BASE_URL": "http://192.168.250.9:11434/v1",
            "PLANNER_API_KEY": "ollama",
            "DEEPSEEK_API_KEY": "sk-deepseek-secret",
        }
    )
    assert provider == "openai_compatible"
    assert client.api_key == "ollama"


def test_planner_and_final_response_share_one_configurable_model(monkeypatch):
    agent = DeepSeekAgent.__new__(DeepSeekAgent)
    calls = []
    captured = {}

    def _tool_call(payload):
        return SimpleNamespace(
            function=SimpleNamespace(
                name=da.TOOL_NAME,
                arguments=json.dumps(payload, ensure_ascii=False),
            )
        )

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                message = SimpleNamespace(
                    tool_calls=[
                        _tool_call(
                            {
                                "target_object": "person",
                                "label": "人",
                                "constraints": [],
                                "action": {"type": "highlight"},
                                "related_objects": [],
                            }
                        )
                    ]
                )
            else:
                message = SimpleNamespace(content="完成")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    agent.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    agent.model = "qwen3.8:27b-mtp-q4_K_M"
    agent.plan_attempts = 0

    agent.plan_request("找到人")
    agent.build_final_response("找到人", {"plan": {}, "targets_count": 0})
    assert all(call.get("model") == "qwen3.8:27b-mtp-q4_K_M" for call in calls)
    assert len(calls) == 2


def test_agent_reports_provider_and_model():
    config = da.build_planner_client(
        environ={
            "PLANNER_MODEL": "qwen3.8:27b-mtp-q4_K_M",
            "PLANNER_BASE_URL": "http://192.168.250.9:11434/v1",
            "PLANNER_API_KEY": "ollama",
        }
    )
    assert config[3] == "openai_compatible"
    assert config[1] == "qwen3.8:27b-mtp-q4_K_M"
