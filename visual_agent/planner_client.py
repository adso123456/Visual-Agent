"""Planner 的最小共享配置与 OpenAI-compatible client 工厂。

与 vlm_client.py 保持同一模式：默认指向本地 Ollama 端点上的
qwen3.8:27b-mtp-q4_K_M；通过环境变量可切回云端 DeepSeek。

- PLANNER_MODEL    默认 qwen3.8:27b-mtp-q4_K_M
- PLANNER_BASE_URL 默认 http://192.168.250.9:11434/v1
- PLANNER_API_KEY  自定义端点必须显式设置
- PLANNER_TIMEOUT  正数秒，可选

密钥规则（与 VLM 层一致，禁止凭据回退）：
- 显式 PLANNER_API_KEY 优先；
- base_url 为 DeepSeek 云端时回退使用 DEEPSEEK_API_KEY；
- base_url 为默认本地 Ollama 端点时使用占位密钥 "ollama"
  （Ollama 不校验密钥，此占位不会发送任何真实凭据）；
- 其他自定义端点必须显式设置 PLANNER_API_KEY，不允许任何回退。
"""

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass

from openai import OpenAI


DEFAULT_PLANNER_MODEL = "qwen3.8:27b-mtp-q4_K_M"
DEFAULT_PLANNER_BASE_URL = "http://192.168.250.9:11434/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


@dataclass(frozen=True)
class PlannerConfig:
    model: str
    base_url: str
    api_key: str
    timeout: float | None


def load_planner_config(environ: Mapping[str, str] | None = None) -> PlannerConfig:
    values = os.environ if environ is None else environ
    model = values.get("PLANNER_MODEL", "").strip() or DEFAULT_PLANNER_MODEL
    base_url = values.get("PLANNER_BASE_URL", "").strip() or DEFAULT_PLANNER_BASE_URL
    planner_api_key = values.get("PLANNER_API_KEY", "").strip()
    deepseek_api_key = values.get("DEEPSEEK_API_KEY", "").strip()
    normalized_base_url = base_url.rstrip("/")
    if planner_api_key:
        api_key = planner_api_key
    elif normalized_base_url == DEEPSEEK_BASE_URL.rstrip("/"):
        api_key = deepseek_api_key
    elif normalized_base_url == DEFAULT_PLANNER_BASE_URL.rstrip("/"):
        api_key = "ollama"
    else:
        raise RuntimeError("非默认 PLANNER_BASE_URL 必须显式设置 PLANNER_API_KEY")
    if not api_key:
        raise RuntimeError("未设置环境变量 PLANNER_API_KEY 或 DEEPSEEK_API_KEY")

    timeout_text = values.get("PLANNER_TIMEOUT", "").strip()
    timeout = None
    if timeout_text:
        try:
            timeout = float(timeout_text)
        except ValueError as error:
            raise RuntimeError("PLANNER_TIMEOUT 必须是正数秒") from error
        if not math.isfinite(timeout) or timeout <= 0:
            raise RuntimeError("PLANNER_TIMEOUT 必须是正数秒")

    return PlannerConfig(
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
    )


def create_planner_client(config: PlannerConfig | None = None) -> OpenAI:
    resolved = config or load_planner_config()
    kwargs = {
        "api_key": resolved.api_key,
        "base_url": resolved.base_url,
    }
    if resolved.timeout is not None:
        kwargs["timeout"] = resolved.timeout
    return OpenAI(**kwargs)


def get_planner_model_name(environ: Mapping[str, str] | None = None) -> str:
    values = os.environ if environ is None else environ
    return values.get("PLANNER_MODEL", "").strip() or DEFAULT_PLANNER_MODEL
