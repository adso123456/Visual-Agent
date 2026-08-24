"""VLM 的最小共享配置与 OpenAI-compatible client 工厂。"""

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass

from openai import OpenAI


DEFAULT_VLM_MODEL = "qwen3-vl-flash"
DEFAULT_VLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass(frozen=True)
class VlmConfig:
    model: str
    base_url: str
    api_key: str
    timeout: float | None


def load_vlm_config(environ: Mapping[str, str] | None = None) -> VlmConfig:
    values = os.environ if environ is None else environ
    model = values.get("VLM_MODEL", "").strip() or DEFAULT_VLM_MODEL
    base_url = values.get("VLM_BASE_URL", "").strip() or DEFAULT_VLM_BASE_URL
    api_key = (
        values.get("VLM_API_KEY", "").strip()
        or values.get("DASHSCOPE_API_KEY", "").strip()
    )
    if not api_key:
        raise RuntimeError("未设置环境变量 VLM_API_KEY 或 DASHSCOPE_API_KEY")

    timeout_text = values.get("VLM_TIMEOUT", "").strip()
    timeout = None
    if timeout_text:
        try:
            timeout = float(timeout_text)
        except ValueError as error:
            raise RuntimeError("VLM_TIMEOUT 必须是正数秒") from error
        if not math.isfinite(timeout) or timeout <= 0:
            raise RuntimeError("VLM_TIMEOUT 必须是正数秒")

    return VlmConfig(
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
    )


def create_vlm_client(config: VlmConfig | None = None) -> OpenAI:
    resolved = config or load_vlm_config()
    kwargs = {
        "api_key": resolved.api_key,
        "base_url": resolved.base_url,
    }
    if resolved.timeout is not None:
        kwargs["timeout"] = resolved.timeout
    return OpenAI(**kwargs)


def get_vlm_model_name(environ: Mapping[str, str] | None = None) -> str:
    values = os.environ if environ is None else environ
    return values.get("VLM_MODEL", "").strip() or DEFAULT_VLM_MODEL
