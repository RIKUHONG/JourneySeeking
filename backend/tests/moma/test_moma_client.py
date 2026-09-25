import json
from dataclasses import dataclass

import httpx
import pytest

from backend.app.config.settings import Settings
from backend.app.integrations.moma_client import (
    MomaAuthenticationError,
    MomaClient,
    MomaRateLimitError,
    MomaServiceError,
)


@dataclass
class FakeResponse:
    status_code: int
    body: object | None = None
    text: str = ""
    headers: dict[str, str] | None = None

    def __post_init__(self):
        if self.headers is None:
            self.headers = {}
        if not self.text and self.body is not None:
            self.text = json.dumps(self.body, ensure_ascii=False)

    def json(self):
        if isinstance(self.body, BaseException):
            raise self.body
        return self.body


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture
def settings():
    return Settings(
        moma_api_url="https://moma.test/v1/chat/completions",
        moma_model="test-model",
        moma_api_key="test-key",
        moma_timeout_seconds=3.5,
        moma_max_retries=2,
    )


def success_body(content='{"ok":true}'):
    return {
        "id": "chatcmpl_test",
        "model": "test-model",
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 11},
    }


def test_chat_sends_openai_compatible_request_and_extracts_result(settings):
    response = FakeResponse(
        status_code=200,
        body=success_body(),
        headers={"x-request-id": "req_header"},
    )
    session = FakeSession([response])
    client = MomaClient(config=settings, session=session)

    result = client.chat([{"role": "user", "content": "生成行程"}], max_tokens=512)

    assert result.content == '{"ok":true}'
    assert result.model == "test-model"
    assert result.request_id == "req_header"
    assert result.usage == {"prompt_tokens": 7, "completion_tokens": 11}
    assert result.raw == success_body()

    url, kwargs = session.calls[0]
    assert url == settings.moma_api_url
    assert kwargs["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }
    assert kwargs["timeout"] == 3.5
    assert kwargs["json"] == {
        "model": "test-model",
        "messages": [{"role": "user", "content": "生成行程"}],
        "max_tokens": 512,
        "stream": False,
        "temperature": 0.2,
        "top_p": 0.9,
    }


def test_chat_uses_body_id_when_request_header_is_missing(settings):
    response = FakeResponse(status_code=200, body=success_body())
    result = MomaClient(config=settings, session=FakeSession([response])).chat([])

    assert result.request_id == "chatcmpl_test"


def test_chat_retries_network_errors_and_returns_later_success(settings, monkeypatch):
    response = FakeResponse(status_code=200, body=success_body())
    network_error = httpx.ConnectError(
        "temporary", request=httpx.Request("POST", settings.moma_api_url)
    )
    session = FakeSession([network_error, response])
    sleeps = []
    monkeypatch.setattr("backend.app.integrations.moma_client.time.sleep", sleeps.append)

    result = MomaClient(config=settings, session=session).chat([])

    assert result.content == '{"ok":true}'
    assert len(session.calls) == 2
    assert sleeps == [1]


def test_chat_retries_server_errors_until_success(settings, monkeypatch):
    response = FakeResponse(status_code=200, body=success_body())
    session = FakeSession([FakeResponse(503, text="busy"), response])
    sleeps = []
    monkeypatch.setattr("backend.app.integrations.moma_client.time.sleep", sleeps.append)

    MomaClient(config=settings, session=session).chat([])

    assert len(session.calls) == 2
    assert sleeps == [1]


def test_chat_raises_service_error_after_server_retries(settings, monkeypatch):
    session = FakeSession([FakeResponse(503, text="busy")] * 3)
    sleeps = []
    monkeypatch.setattr("backend.app.integrations.moma_client.time.sleep", sleeps.append)

    with pytest.raises(MomaServiceError) as exc_info:
        MomaClient(config=settings, session=session).chat([])

    assert len(session.calls) == 3
    assert sleeps == [1, 2]
    assert "HTTP 503" in str(exc_info.value)


def test_chat_retries_rate_limit_until_limit_then_raises(settings, monkeypatch):
    session = FakeSession([FakeResponse(429, text="limited")] * 3)
    sleeps = []
    monkeypatch.setattr("backend.app.integrations.moma_client.time.sleep", sleeps.append)

    with pytest.raises(MomaRateLimitError):
        MomaClient(config=settings, session=session).chat([])

    assert len(session.calls) == 3
    assert sleeps == [1, 2]


def test_chat_does_not_retry_authentication_errors(settings):
    session = FakeSession([FakeResponse(401, text="secret details")])

    with pytest.raises(MomaAuthenticationError) as exc_info:
        MomaClient(config=settings, session=session).chat([])

    assert len(session.calls) == 1
    assert "secret details" not in str(exc_info.value)


def test_chat_raises_service_error_after_network_retries(settings, monkeypatch):
    timeout_error = httpx.ReadTimeout(
        "upstream timeout", request=httpx.Request("POST", settings.moma_api_url)
    )
    session = FakeSession([timeout_error] * 3)
    sleeps = []
    monkeypatch.setattr("backend.app.integrations.moma_client.time.sleep", sleeps.append)

    with pytest.raises(MomaServiceError) as exc_info:
        MomaClient(config=settings, session=session).chat([])

    assert len(session.calls) == 3
    assert sleeps == [1, 2]
    assert "upstream timeout" in str(exc_info.value)


def test_chat_converts_malformed_success_response_to_service_error(settings):
    response = FakeResponse(status_code=200, body={"choices": []})

    with pytest.raises(MomaServiceError):
        MomaClient(config=settings, session=FakeSession([response])).chat([])


def test_chat_rejects_empty_content(settings):
    response = FakeResponse(status_code=200, body=success_body(content="  "))

    with pytest.raises(MomaServiceError):
        MomaClient(config=settings, session=FakeSession([response])).chat([])


def test_chat_converts_non_success_response_to_service_error_without_leaking_long_body(settings):
    response = FakeResponse(status_code=400, text="x" * 1000)

    with pytest.raises(MomaServiceError) as exc_info:
        MomaClient(config=settings, session=FakeSession([response])).chat([])

    assert len(str(exc_info.value)) < 600
