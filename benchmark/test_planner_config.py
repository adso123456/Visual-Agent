"""PLANNER_SEAM_V1: DeepSeekAgent 规划器端点/模型/密钥的 env 可配置合同。"""

import pytest

from visual_agent import deepseek_agent as da


def test_planner_defaults_stay_frozen():
    assert da.DEFAULT_PLANNER_MODEL == "deepseek-v4-pro"
    assert da.DEFAULT_PLANNER_BASE_URL == "https://api.deepseek.com"
    assert da.MODEL_NAME == da.DEFAULT_PLANNER_MODEL
    assert da.BASE_URL == da.DEFAULT_PLANNER_BASE_URL


def test_planner_config_requires_api_key():
    env = {}
    with pytest.raises(RuntimeError, match="PLANNER_API_KEY 或 DEEPSEEK_API_KEY"):
        da.build_planner_client(environ=env)


def test_planner_config_falls_back_to_deepseek_api_key():
    client, model, base_url = da.build_planner_client(
        environ={"DEEPSEEK_API_KEY": "sk-test"}
    )
    assert model == "deepseek-v4-pro"
    assert base_url == "https://api.deepseek.com"
    assert str(client.base_url).rstrip("/") == "https://api.deepseek.com"


def test_planner_config_switches_to_local_qwen():
    client, model, base_url = da.build_planner_client(
        environ={
            "PLANNER_MODEL": "qwen3.8:27b-mtp-q4_K_M",
            "PLANNER_BASE_URL": "http://192.168.250.9:11434/v1",
            "PLANNER_API_KEY": "ollama",
        }
    )
    assert model == "qwen3.8:27b-mtp-q4_K_M"
    assert base_url == "http://192.168.250.9:11434/v1"
    assert str(client.base_url).rstrip("/") == "http://192.168.250.9:11434/v1"
