"""Deterministic offline MoMA client for local development and integration tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class MockMomaResponse:
    content: Any
    model: str = "mock-moma"
    request_id: str = "req_mock"
    usage: Mapping[str, int] | None = None


class MockMomaClient:
    """Return queued responses using the same ``chat`` shape as ``MomaClient``.

    Responses may be strings, content-part lists, response objects, or
    exceptions. This keeps endpoint and pipeline tests fully offline.
    """

    def __init__(self, responses: Iterable[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[list[Mapping[str, str]], dict[str, Any]]] = []

    def chat(self, messages: Iterable[Mapping[str, str]], **kwargs: Any) -> MockMomaResponse:
        self.calls.append(([dict(message) for message in messages], dict(kwargs)))
        if not self._responses:
            raise RuntimeError("mock MoMA response queue is empty")
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, MockMomaResponse):
            return response
        return MockMomaResponse(content=response)
