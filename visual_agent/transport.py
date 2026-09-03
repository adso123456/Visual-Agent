"""OpenAI-compatible completion 的显式、可观测 transport retry。"""

import time
from collections.abc import Callable
from typing import TypeVar

from openai import APIConnectionError, APIStatusError, APITimeoutError


MAX_TRANSPORT_ATTEMPTS = 3
RETRYABLE_HTTP_STATUSES = {408, 409, 429}

T = TypeVar("T")


def _http_status(error: Exception) -> int | None:
    status = getattr(error, "status_code", None)
    return status if isinstance(status, int) else None


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, (APITimeoutError, TimeoutError)):
        return True
    if isinstance(error, (APIConnectionError, ConnectionError)):
        return True
    if isinstance(error, APIStatusError):
        status = _http_status(error)
        return status in RETRYABLE_HTTP_STATUSES or (
            status is not None and status >= 500
        )
    return False


def _metadata(
    *,
    attempts: int,
    first_error: str | None,
    first_http_status: int | None,
    final_status: str,
) -> dict:
    return {
        "transport_attempts": attempts,
        "transport_retry_count": max(0, attempts - 1),
        "transport_recovered": attempts > 1 and final_status == "success",
        "first_transport_error": first_error,
        "first_http_status": first_http_status,
        "final_transport_status": final_status,
    }


def request_with_transport_retry(
    request_once: Callable[[], T],
    *,
    telemetry: list[dict] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """执行一次 logical completion；每次最多发出三个 transport 请求。"""
    sleeper = sleep or time.sleep
    first_error = None
    first_http_status = None
    for attempt in range(1, MAX_TRANSPORT_ATTEMPTS + 1):
        try:
            result = request_once()
        except Exception as error:
            if first_error is None:
                first_error = type(error).__name__
                first_http_status = _http_status(error)
            retryable = _is_retryable(error)
            exhausted = attempt == MAX_TRANSPORT_ATTEMPTS
            if not retryable or exhausted:
                final_status = (
                    "retryable_failure_exhausted"
                    if retryable
                    else "non_retryable_failure"
                )
                metadata = _metadata(
                    attempts=attempt,
                    first_error=first_error,
                    first_http_status=first_http_status,
                    final_status=final_status,
                )
                if telemetry is not None:
                    telemetry.append(metadata)
                setattr(error, "transport_telemetry", metadata)
                raise
            sleeper(float(2 ** (attempt - 1)))
            continue

        metadata = _metadata(
            attempts=attempt,
            first_error=first_error,
            first_http_status=first_http_status,
            final_status="success",
        )
        if telemetry is not None:
            telemetry.append(metadata)
        return result

    raise AssertionError("transport retry 循环不应到达此处")


def merge_transport_telemetry(items: list[dict]) -> dict:
    """合并多个 logical completion，不改变 contract retry 的计数语义。"""
    if not items:
        return {
            "transport_attempts": 0,
            "transport_retry_count": 0,
            "transport_recovered": False,
            "first_transport_error": None,
            "first_http_status": None,
            "final_transport_status": "not_started",
        }
    return {
        "transport_attempts": sum(
            item.get("transport_attempts", 0) for item in items
        ),
        "transport_retry_count": sum(
            item.get("transport_retry_count", 0) for item in items
        ),
        "transport_recovered": any(
            item.get("transport_recovered", False) for item in items
        ),
        "first_transport_error": next(
            (
                item.get("first_transport_error")
                for item in items
                if item.get("first_transport_error") is not None
            ),
            None,
        ),
        "first_http_status": next(
            (
                item.get("first_http_status")
                for item in items
                if item.get("first_http_status") is not None
            ),
            None,
        ),
        "final_transport_status": items[-1].get(
            "final_transport_status", "not_started"
        ),
    }
