import pytest

from visual_agent import vlm_client


def test_cloud_defaults_preserve_dashscope_behavior():
    config = vlm_client.load_vlm_config({"DASHSCOPE_API_KEY": "cloud-key"})

    assert config == vlm_client.VlmConfig(
        model="qwen3-vl-flash",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="cloud-key",
        timeout=None,
    )


def test_local_config_parses_model_endpoint_key_and_timeout():
    config = vlm_client.load_vlm_config(
        {
            "VLM_MODEL": "qwen3.8:27b-mtp-q4_K_M",
            "VLM_BASE_URL": "http://192.168.250.9:11434/v1",
            "VLM_API_KEY": "ollama",
            "VLM_TIMEOUT": "120.5",
            "DASHSCOPE_API_KEY": "cloud-key",
        }
    )

    assert config == vlm_client.VlmConfig(
        model="qwen3.8:27b-mtp-q4_K_M",
        base_url="http://192.168.250.9:11434/v1",
        api_key="ollama",
        timeout=120.5,
    )


def test_client_only_passes_timeout_when_configured(monkeypatch):
    calls = []
    monkeypatch.setattr(vlm_client, "OpenAI", lambda **kwargs: calls.append(kwargs) or kwargs)

    cloud = vlm_client.VlmConfig("model", "https://cloud.example/v1", "key", None)
    local = vlm_client.VlmConfig("model", "http://local.example/v1", "ollama", 90.0)

    vlm_client.create_vlm_client(cloud)
    vlm_client.create_vlm_client(local)

    assert calls == [
        {"api_key": "key", "base_url": "https://cloud.example/v1"},
        {"api_key": "ollama", "base_url": "http://local.example/v1", "timeout": 90.0},
    ]


@pytest.mark.parametrize("timeout", ["zero", "0", "-1", "nan", "inf"])
def test_invalid_timeout_is_rejected(timeout):
    with pytest.raises(RuntimeError, match="VLM_TIMEOUT"):
        vlm_client.load_vlm_config(
            {
                "VLM_API_KEY": "key",
                "VLM_TIMEOUT": timeout,
            }
        )


def test_missing_cloud_and_vlm_keys_is_rejected():
    with pytest.raises(RuntimeError, match="VLM_API_KEY.*DASHSCOPE_API_KEY"):
        vlm_client.load_vlm_config({})
