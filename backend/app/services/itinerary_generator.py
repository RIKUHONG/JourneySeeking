"""Structured itinerary generation through a replaceable MoMA client."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .prompt_builder import PromptBuilder


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

    def __init__(
        self,
        client: Any,
        prompt_builder: PromptBuilder | None = None,
        validator: Callable[[dict[str, Any]], Any] | None = None,
        max_repair_attempts: int = 1,
    ) -> None:
        if max_repair_attempts < 0:
            raise ValueError("max_repair_attempts must be non-negative")
        self.client = client
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.validator = validator
        self.max_repair_attempts = max_repair_attempts

    def generate(self, request: Any) -> str:
        """Return normalized JSON text for a trip request."""
        messages = self.prompt_builder.build_messages(request)
        last_failure = "MoMA 未返回可用的结构化行程。"
        last_raw_content = ""

        for repair_attempt in range(self.max_repair_attempts + 1):
            if repair_attempt > 0:
                messages = self._build_repair_messages(last_raw_content, last_failure)

            try:
                response = self.client.chat(messages)
            except Exception as exc:
                if self._is_timeout(exc):
                    raise ItineraryGenerationError(
                        "MOMA_TIMEOUT", "MoMA 行程生成请求超时。"
                    ) from exc
                raise

            raw_content = self._content_text(getattr(response, "content", response))
            last_raw_content = raw_content
            try:
                payload, normalized_json = self._parse_payload(raw_content)
                if self.validator is not None:
                    self.validator(payload)
                return normalized_json
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                last_failure = self._failure_reason(exc)

        raise ItineraryGenerationError("MOMA_INVALID_RESPONSE", "MoMA 返回的行程无法通过结构校验。")

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
    def _build_repair_messages(
        raw_content: str,
        failure_reason: str,
    ) -> list[dict[str, str]]:
        raw_preview = raw_content[:4000]
        return [
            {
                "role": "system",
                "content": (
                    "你是结构化 JSON 修复器。只返回一个合法 JSON 对象，"
                    "不要返回 Markdown、解释文字或代码块。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请修复下面的 MoMA 行程响应。\n"
                    f"失败原因：{failure_reason}\n"
                    "原始响应开始\n"
                    f"{raw_preview}\n"
                    "原始响应结束\n"
                    "请严格返回符合第一版 Itinerary 契约的 JSON 对象。"
                ),
            },
        ]

    @staticmethod
    def _failure_reason(exc: Exception) -> str:
        if isinstance(exc, json.JSONDecodeError):
            return "返回内容不是合法 JSON。"
        return "返回内容为空、根节点错误或未通过结构校验。"

    @staticmethod
    def _is_timeout(exc: Exception) -> bool:
        if isinstance(exc, TimeoutError):
            return True
        name = type(exc).__name__.lower()
        message = str(exc).lower()
        return (
            "timeout" in name or "timedout" in name or "timed out" in message or "超时" in message
        )
