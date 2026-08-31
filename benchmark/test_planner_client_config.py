"""planner_client 配置解析的契约测试（不发起网络请求）。"""

from visual_agent import planner_client


def test_default_is_local_qwen():
    config = planner_client.load_planner_config({})
    assert config.model == "qwen3.8:27b-mtp-q4_K_M"
    assert config.base_url == "http://192.168.250.9:11434/v1"
    assert config.api_key == "ollama"
    assert config.timeout is None


def test_explicit_planner_key_wins():
    config = planner_client.load_planner_config(
        {"PLANNER_API_KEY": "sk-custom", "DEEPSEEK_API_KEY": "sk-deepseek"}
    )
    assert config.api_key == "sk-custom"


def test_deepseek_base_url_falls_back_to_deepseek_key():
    config = planner_client.load_planner_config(
        {
            "PLANNER_BASE_URL": "https://api.deepseek.com",
            "DEEPSEEK_API_KEY": "sk-deepseek",
        }
    )
    assert config.model == "qwen3.8:27b-mtp-q4_K_M"
    assert config.base_url == "https://api.deepseek.com"
    assert config.api_key == "sk-deepseek"


def test_deepseek_base_url_requires_key():
    try:
        planner_client.load_planner_config({"PLANNER_BASE_URL": "https://api.deepseek.com"})
    except RuntimeError as error:
        assert "PLANNER_API_KEY" in str(error) or "DEEPSEEK_API_KEY" in str(error)
    else:
        raise AssertionError("应要求 PLANNER_API_KEY 或 DEEPSEEK_API_KEY")


def test_custom_base_url_requires_explicit_key():
    try:
        planner_client.load_planner_config(
            {"PLANNER_BASE_URL": "http://10.0.0.8:11434/v1", "DEEPSEEK_API_KEY": "sk-deepseek"}
        )
    except RuntimeError as error:
        assert "PLANNER_API_KEY" in str(error)
    else:
        raise AssertionError("自定义端点不得回退 DEEPSEEK_API_KEY")


def test_model_and_timeout_overrides():
    config = planner_client.load_planner_config(
        {
            "PLANNER_MODEL": "deepseek-v4-pro",
            "PLANNER_TIMEOUT": "30",
        }
    )
    assert config.model == "deepseek-v4-pro"
    assert config.timeout == 30.0


def test_invalid_timeout_rejected():
    for value in ("abc", "0", "-1", "inf", "nan"):
        try:
            planner_client.load_planner_config({"PLANNER_TIMEOUT": value})
        except RuntimeError as error:
            assert "PLANNER_TIMEOUT" in str(error)
        else:
            raise AssertionError(f"非法超时应被拒绝：{value}")
