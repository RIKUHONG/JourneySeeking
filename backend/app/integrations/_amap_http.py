"""Shared HTTP handling for Amap's Web Service APIs."""

import time
from contextlib import nullcontext
from typing import Any

import httpx

from .errors import ExternalServiceError, FailureReason


def request_amap(
    path: str,
    params: dict[str, Any],
    *,
    base_url: str,
    api_key: str,
    timeout_seconds: float,
    max_retries: int,
    error_type: type[ExternalServiceError],
    session: httpx.Client | None = None,
) -> dict[str, Any]:
    request_params = {**params, "key": api_key}
    context = nullcontext(session) if session is not None else httpx.Client()
    with context as client:
        for attempt in range(max_retries + 1):
            try:
                response = client.get(
                    f"{base_url.rstrip('/')}/{path.lstrip('/')}",
                    params=request_params,
                    timeout=timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                reason = FailureReason.TIMEOUT
                if attempt == max_retries:
                    raise error_type(reason) from exc
            except httpx.RequestError as exc:
                reason = FailureReason.NETWORK
                if attempt == max_retries:
                    raise error_type(reason) from exc
            else:
                if response.status_code in (429,) or response.status_code >= 500:
                    if attempt == max_retries:
                        raise error_type(FailureReason.PROVIDER)
                elif response.status_code != 200:
                    raise error_type(FailureReason.PROVIDER)
                else:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise error_type(FailureReason.INVALID_RESPONSE) from exc
                    if not isinstance(payload, dict):
                        raise error_type(FailureReason.INVALID_RESPONSE)
                    if payload.get("status") != "1":
                        raise error_type(FailureReason.PROVIDER)
                    return payload
            time.sleep(2**attempt)

    raise AssertionError("Unreachable: every request attempt returns or raises")
