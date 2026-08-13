import json
from collections.abc import Callable


MAX_ATTEMPTS = 2


def skipped_protocol_metadata() -> dict:
    return {
        "attempts": 0,
        "retry_count": 0,
        "recovered": False,
        "first_error_code": None,
    }


def request_validated_json(
    request_once: Callable[[str | None], str | None],
    validator: Callable[[dict], object],
    contract_name: str,
    schema_hint: str,
) -> tuple[object, dict]:
    first_error_code = None
    last_error_code = None
    last_message = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        correction = None
        if last_error_code:
            correction = (
                "FORMAT CORRECTION ONLY。上一次响应违反结构契约："
                f"{last_error_code}: {last_message}。"
                "请重新完成完全相同的视觉判断，只修正输出结构；不得改变任务、候选、约束、关系或判断标准。"
                f"必须严格返回以下结构：{schema_hint}"
            )
        content = request_once(correction)
        try:
            if not content:
                raise ValueError("empty_response")
            try:
                result = json.loads(content)
            except json.JSONDecodeError as error:
                last_error_code = "json_decode_error"
                last_message = str(error)[:200]
                if first_error_code is None:
                    first_error_code = last_error_code
                continue
            try:
                validated = validator(result)
            except RuntimeError as error:
                last_error_code = "contract_validation_error"
                last_message = str(error)[:200]
                if first_error_code is None:
                    first_error_code = last_error_code
                continue
            return validated, {
                "attempts": attempt,
                "retry_count": attempt - 1,
                "recovered": attempt > 1,
                "first_error_code": first_error_code,
            }
        except ValueError as error:
            if str(error) != "empty_response":
                raise
            last_error_code = "empty_response"
            last_message = "Qwen 返回空响应"
            if first_error_code is None:
                first_error_code = last_error_code
    raise RuntimeError(
        f"Qwen {contract_name} structured output failed after {MAX_ATTEMPTS} attempts: "
        f"{last_error_code}: {last_message}"
    )
