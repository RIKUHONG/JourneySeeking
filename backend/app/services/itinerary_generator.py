"""Structured itinerary generation through a replaceable MoMA client."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from pydantic import ValidationError

from .model_call_metadata import ModelCallRecord, make_record, summarize_calls
from .prompt_builder import PromptBuilder
from .prompt_registry import CRITIC_REPAIR, GENERATION, STRUCTURED_REPAIR, get_prompt
from .prompt_schemas import ItineraryDraft

logger = logging.getLogger(__name__)

_AUTO_CANDIDATE_POOL = object()


@dataclass(frozen=True)
class ItineraryGenerationError(RuntimeError):
    """Stable error raised at the MoMA itinerary-generation boundary."""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class ItineraryGenerator:
    """Generate JSON itinerary text while keeping MoMA concerns out of the API layer.

    The optional validator is injected by the caller. Member A's service can
    provide the canonical Itinerary/Pydantic validation without making this
    service maintain a second copy of the domain model.
    """

    supports_prompt_repair = True

    def __init__(
        self,
        client: Any,
        prompt_builder: PromptBuilder | None = None,
        validator: Callable[[dict[str, Any]], Any] | None = None,
        max_repair_attempts: int = 1,
        candidate_provider: Callable[[Any], Any] | None = None,
        structured_repair_version: str = "v1",
        critic_repair_version: str = "v1",
    ) -> None:
        if max_repair_attempts < 0:
            raise ValueError("max_repair_attempts must be non-negative")
        self.client = client
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.validator = validator
        self.max_repair_attempts = max_repair_attempts
        self.candidate_provider = candidate_provider
        self.structured_repair_version = get_prompt(
            STRUCTURED_REPAIR, structured_repair_version
        ).version
        self.critic_repair_version = get_prompt(CRITIC_REPAIR, critic_repair_version).version
        self.last_candidate_pool = None
        self.last_candidate_diagnostics = None
        self.last_knowledge_chunks = ()
        self.last_usage: Mapping[str, Any] = {}
        self.last_provider_request_id: str | None = None
        self.last_raw_content = ""
        self.last_validation_paths: tuple[str, ...] = ()
        self.call_records: list[ModelCallRecord] = []
        self.execution_context: dict[str, str] = {}

    def set_execution_context(self, *, request_id: str, runtime: str, graph_version: str) -> None:
        self.execution_context = {
            "request_id": request_id,
            "runtime": runtime,
            "graph_version": graph_version,
        }

    def mark_validation(self, status: str, code: str | None = None) -> None:
        if self.call_records:
            self.call_records[-1] = replace(
                self.call_records[-1], validation=status, failure_code=code
            )
            logger.info(
                "model_validation context=%s metadata=%s",
                self.execution_context,
                self.call_records[-1].as_log_fields(),
            )

    def set_validation_paths(self, paths: Sequence[str]) -> None:
        self.last_validation_paths = tuple(str(path)[:120] for path in paths[:20])

    def generate(
        self,
        request: Any,
        *,
        knowledge_chunks: Sequence[Any] = (),
        candidate_pool: Any = _AUTO_CANDIDATE_POOL,
        planning_context: Mapping[str, Any] | None = None,
        candidate_diagnostics: Any = _AUTO_CANDIDATE_POOL,
        allow_repair: bool = True,
        repair_kind: str | None = None,
        repair_findings: Sequence[Mapping[str, str]] = (),
        repair_failure_code: str = "ITINERARY_VALIDATION_ERROR",
    ) -> str:
        """Return normalized JSON text for a trip request."""
        if repair_kind is None:
            self.call_records = []
            self.last_raw_content = ""
            self.last_validation_paths = ()
        elif repair_kind not in {STRUCTURED_REPAIR, CRITIC_REPAIR}:
            raise ValueError("unknown repair kind")
        if candidate_pool is _AUTO_CANDIDATE_POOL:
            candidate_pool = (
                self.candidate_provider(request) if self.candidate_provider is not None else None
            )
            self.last_candidate_diagnostics = candidate_pool
        elif candidate_diagnostics is not _AUTO_CANDIDATE_POOL:
            self.last_candidate_diagnostics = candidate_diagnostics
        # An unavailable or below-threshold map search must not turn the
        # optional candidate constraint into a hard failure for the base
        # itinerary. The pool remains available to callers for diagnostics.
        if candidate_pool is not None and (
            not getattr(candidate_pool, "candidates", ())
            or not getattr(candidate_pool, "meets_minimum", True)
        ):
            candidate_pool = None
        self.last_candidate_pool = candidate_pool
        self.last_knowledge_chunks = tuple(knowledge_chunks)
        spec = (
            get_prompt(
                repair_kind,
                self.structured_repair_version
                if repair_kind == STRUCTURED_REPAIR
                else self.critic_repair_version,
            )
            if repair_kind is not None
            else get_prompt(GENERATION, self.prompt_builder.spec.version)
        )
        if repair_kind is not None:
            messages = self.prompt_builder.build_repair_messages(
                request,
                kind=repair_kind,
                raw_content=self.last_raw_content,
                failure_code=repair_failure_code,
                validation_paths=self.last_validation_paths,
                findings=repair_findings,
                candidate_pool=candidate_pool,
                knowledge_chunks=knowledge_chunks,
                planning_context=planning_context,
                version=spec.version,
            )
        else:
            messages = self.prompt_builder.build_messages(
                request, candidate_pool, knowledge_chunks, planning_context
            )
        last_raw_content = ""

        repair_limit = self.max_repair_attempts if allow_repair and repair_kind is None else 0
        for repair_attempt in range(repair_limit + 1):
            if repair_attempt > 0:
                spec = get_prompt(STRUCTURED_REPAIR, self.structured_repair_version)
                messages = self.prompt_builder.build_repair_messages(
                    request,
                    kind=STRUCTURED_REPAIR,
                    raw_content=last_raw_content,
                    failure_code="MOMA_INVALID_RESPONSE",
                    validation_paths=self.last_validation_paths,
                    candidate_pool=candidate_pool,
                    knowledge_chunks=knowledge_chunks,
                    planning_context=planning_context,
                    version=spec.version,
                )

            started = time.perf_counter()
            try:
                response = self.client.chat(messages)
            except Exception as exc:
                code = "MOMA_TIMEOUT" if self._is_timeout(exc) else "MOMA_PROVIDER_ERROR"
                self._record_call(
                    spec,
                    None,
                    (time.perf_counter() - started) * 1000,
                    "failed",
                    code,
                    candidate_pool,
                    knowledge_chunks,
                    planning_context,
                )
                if self._is_timeout(exc):
                    raise ItineraryGenerationError(
                        "MOMA_TIMEOUT", "MoMA 行程生成请求超时。"
                    ) from exc
                raise

            self.last_provider_request_id = getattr(response, "request_id", None)

            raw_content = self._content_text(getattr(response, "content", response))
            last_raw_content = raw_content
            self.last_raw_content = raw_content
            try:
                payload, normalized_json = self._parse_payload(raw_content)
                if (spec.prompt_id == GENERATION and spec.version == "v2") or (
                    repair_kind is not None and self.prompt_builder.spec.version == "v2"
                ):
                    ItineraryDraft.model_validate(payload)
                if self.validator is not None:
                    self.validator(payload)
                self.last_raw_content = normalized_json
                self._record_call(
                    spec,
                    response,
                    (time.perf_counter() - started) * 1000,
                    "passed",
                    None,
                    candidate_pool,
                    knowledge_chunks,
                    planning_context,
                )
                if allow_repair:
                    self.last_raw_content = ""
                return normalized_json
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                if isinstance(exc, ValidationError):
                    self.set_validation_paths(
                        [".".join(map(str, error["loc"])) for error in exc.errors()]
                    )
                else:
                    self.set_validation_paths(("root",))
                self._record_call(
                    spec,
                    response,
                    (time.perf_counter() - started) * 1000,
                    "rejected",
                    "MOMA_INVALID_RESPONSE",
                    candidate_pool,
                    knowledge_chunks,
                    planning_context,
                )
                logger.warning(
                    "MoMA itinerary response rejected before API validation "
                    "(attempt=%d, chars=%d, reason=%s)",
                    repair_attempt + 1,
                    len(raw_content),
                    "invalid_json_or_schema",
                )

        if allow_repair:
            self.last_raw_content = ""
        raise ItineraryGenerationError("MOMA_INVALID_RESPONSE", "MoMA 返回的行程无法通过结构校验。")

    def _record_call(
        self,
        spec: Any,
        response: Any | None,
        duration_ms: float,
        validation: str,
        failure_code: str | None,
        candidate_pool: Any,
        knowledge_chunks: Sequence[Any],
        planning_context: Mapping[str, Any] | None,
    ) -> None:
        weather = (planning_context or {}).get("weather_context", {})
        self.call_records.append(
            make_record(
                prompt_key=spec.key,
                schema_version=spec.schema_version,
                model=getattr(response, "model", None),
                duration_ms=duration_ms,
                usage=getattr(response, "usage", None),
                validation=validation,
                failure_code=failure_code,
                candidate_count=len(getattr(candidate_pool, "candidates", ()) or ()),
                weather_available_count=sum(
                    item.get("status") == "available" for item in weather.values()
                ),
                knowledge_count=len(knowledge_chunks),
                request_id=self.execution_context.get("request_id"),
                runtime=self.execution_context.get("runtime"),
                graph_version=self.execution_context.get("graph_version"),
            )
        )
        summary = summarize_calls(self.call_records)
        self.last_usage = {
            "prompt_tokens": summary["prompt_tokens"],
            "completion_tokens": summary["completion_tokens"],
            "total_tokens": summary["prompt_tokens"] + summary["completion_tokens"],
        }
        logger.info(
            "model_call context=%s metadata=%s",
            self.execution_context,
            self.call_records[-1].as_log_fields(),
        )

    @staticmethod
    def _content_text(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, Sequence) and not isinstance(content, (bytes, bytearray)):
            parts: list[str] = []
            for item in content:
                if isinstance(item, Mapping):
                    text = item.get("text")
                    if text is not None:
                        parts.append(str(text))
                elif item is not None:
                    parts.append(str(item))
            return "".join(parts)
        return str(content)

    @classmethod
    def _parse_payload(cls, raw_content: str) -> tuple[dict[str, Any], str]:
        text = raw_content.strip()
        if not text:
            raise ValueError("MoMA 返回为空。")

        json_text = cls._extract_json_object(text)
        payload = json.loads(json_text)

        if not isinstance(payload, dict):
            raise TypeError("MoMA 行程根节点必须是 JSON 对象。")

        return payload, json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _extract_json_object(raw_text: str) -> str:
        """Extract the first balanced JSON object from model text."""
        decoder = json.JSONDecoder()
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
            if text.lower().startswith("json"):
                text = text[4:].lstrip()

        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                _, end_index = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            return text[index : index + end_index]

        raise ValueError("MoMA 返回中未找到 JSON 对象。")

    @staticmethod
    def _is_timeout(exc: Exception) -> bool:
        if isinstance(exc, TimeoutError):
            return True
        name = type(exc).__name__.lower()
        message = str(exc).lower()
        return (
            "timeout" in name or "timedout" in name or "timed out" in message or "超时" in message
        )
