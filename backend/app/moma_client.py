"""Server-side adapter for MoMA's OpenAI-compatible Chat Completions API."""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import requests

from .config.settings import Settings, settings


class MomaError(RuntimeError):
    """Base class for MoMA integration errors."""


class MomaAuthenticationError(MomaError):
    """The API key is invalid or lacks permission."""


class MomaRateLimitError(MomaError):
    """The service rate-limited the request."""


class MomaServiceError(MomaError):
    """The upstream MoMA service returned an error."""


@dataclass(frozen=True)
class MomaResult:
    content: str
    model: str | None
    request_id: str | None
    usage: Mapping[str, Any]
    raw: Mapping[str, Any]


class MomaClient:
    """Call MoMA without exposing the API key or reasoning field to callers."""

    def __init__(self, config: Settings = settings, session: requests.Session | None = None) -> None:
        config.validate_moma()
        self.config = config
        self.session = session or requests.Session()

    def chat(
        self,
        messages: Iterable[Mapping[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        top_p: float = 0.9,
    ) -> MomaResult:
        payload = {
            "model": self.config.moma_model,
            "messages": [dict(message) for message in messages],
            "max_tokens": max_tokens,
            "stream": False,
            "temperature": temperature,
            "top_p": top_p,
        }
        headers = {
            "Authorization": f"Bearer {self.config.moma_api_key}",
            "Content-Type": "application/json",
        }

        last_response: requests.Response | None = None
        for attempt in range(self.config.moma_max_retries + 1):
            try:
                response = self.session.post(
                    self.config.moma_api_url,
                    headers=headers,
                    json=payload,
                    timeout=self.config.moma_timeout_seconds,
                )
            except requests.RequestException as exc:
                if attempt >= self.config.moma_max_retries:
                    raise MomaServiceError(f"MoMA 网络请求失败：{exc}") from exc
                time.sleep(2**attempt)
                continue

            last_response = response
            if response.status_code == 200:
                return self._parse_response(response)
            if response.status_code in (401, 403):
                raise MomaAuthenticationError(f"MoMA 认证或权限失败（HTTP {response.status_code}）。")
            if response.status_code == 429:
                if attempt < self.config.moma_max_retries:
                    time.sleep(2**attempt)
                    continue
                raise MomaRateLimitError("MoMA 请求频率或额度受限。")
            if response.status_code >= 500 and attempt < self.config.moma_max_retries:
                time.sleep(2**attempt)
                continue
            break

        detail = self._safe_error_detail(last_response)
        status = last_response.status_code if last_response is not None else "unknown"
        raise MomaServiceError(f"MoMA 服务调用失败（HTTP {status}）：{detail}")

    @staticmethod
    def _parse_response(response: requests.Response) -> MomaResult:
        try:
            body = response.json()
            content = body["choices"][0]["message"].get("content")
            if not isinstance(content, str) or not content.strip():
                raise MomaServiceError(
                    "MoMA 未返回最终回答，可能是 max_tokens 太小导致推理未完成。"
                )
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise MomaServiceError("MoMA 返回了无法解析的响应。") from exc
        return MomaResult(
            content=str(content),
            model=body.get("model"),
            request_id=response.headers.get("x-request-id") or body.get("id"),
            usage=body.get("usage") or {},
            raw=body,
        )

    @staticmethod
    def _safe_error_detail(response: requests.Response | None) -> str:
        if response is None:
            return "没有收到响应。"
        text = response.text.strip()
        return text[:500] if text else "服务端未返回错误正文。"
