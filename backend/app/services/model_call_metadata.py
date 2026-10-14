"""Request-local, redacted accounting for model calls."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any


def _safe_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)[:100]
    return text if re.fullmatch(r"[A-Za-z0-9_./:-]+", text) else None


def _token_count(usage: Mapping[str, Any], key: str) -> int:
    value = usage.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


@dataclass(frozen=True, slots=True)
class ModelCallRecord:
    prompt_key: str
    schema_version: str
    model: str | None
    duration_ms: float
    prompt_tokens: int
    completion_tokens: int
    validation: str
    failure_code: str | None
    candidate_count: int = 0
    weather_available_count: int = 0
    knowledge_count: int = 0
    request_id: str | None = None
    runtime: str | None = None
    graph_version: str | None = None

    def as_log_fields(self) -> dict[str, Any]:
        return asdict(self)


def make_record(
    *,
    prompt_key: str,
    schema_version: str,
    model: Any,
    duration_ms: float,
    usage: Mapping[str, Any] | None,
    validation: str,
    failure_code: str | None = None,
    candidate_count: int = 0,
    weather_available_count: int = 0,
    knowledge_count: int = 0,
    request_id: str | None = None,
    runtime: str | None = None,
    graph_version: str | None = None,
) -> ModelCallRecord:
    counts = usage or {}
    return ModelCallRecord(
        prompt_key=prompt_key,
        schema_version=schema_version,
        model=_safe_id(model),
        duration_ms=round(max(0.0, duration_ms), 2),
        prompt_tokens=_token_count(counts, "prompt_tokens"),
        completion_tokens=_token_count(counts, "completion_tokens"),
        validation=validation,
        failure_code=failure_code,
        candidate_count=candidate_count,
        weather_available_count=weather_available_count,
        knowledge_count=knowledge_count,
        request_id=_safe_id(request_id),
        runtime=_safe_id(runtime),
        graph_version=_safe_id(graph_version),
    )


def summarize_calls(records: Sequence[ModelCallRecord]) -> dict[str, Any]:
    return {
        "call_count": len(records),
        "prompt_tokens": sum(record.prompt_tokens for record in records),
        "completion_tokens": sum(record.completion_tokens for record in records),
        "duration_ms": round(sum(record.duration_ms for record in records), 2),
        "calls": [record.as_log_fields() for record in records],
    }
