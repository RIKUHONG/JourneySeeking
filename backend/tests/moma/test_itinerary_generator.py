import json
from types import SimpleNamespace

import pytest

from backend.app.services.itinerary_generator import (
    ItineraryGenerationError,
    ItineraryGenerator,
)

VALID_ITINERARY = {
    "destination": "杭州",
    "start_date": "2026-10-01",
    "end_date": "2026-10-04",
    "summary": "轻松的杭州文化美食之旅",
    "days": [],
    "total_estimated_cost": 0,
}


def make_trip_request(**overrides):
    values = {
        "destination": "杭州",
        "start_date": "2026-10-01",
        "end_date": "2026-10-04",
        "travelers": 2,
        "budget": 10000,
        "preferences": ["美食", "历史文化"],
        "pace": "relaxed",
        "dietary_preferences": ["少辣"],
        "hotel_level": "four_star",
        "special_notes": "不要早起",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_result(content):
    return SimpleNamespace(
        content=content,
        model="test-model",
        request_id="req_test",
        usage={"prompt_tokens": 10, "completion_tokens": 20},
        raw={},
    )


class FakeMomaClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return make_result(response)


def test_generate_returns_normalized_json_from_plain_model_response():
    client = FakeMomaClient([json.dumps(VALID_ITINERARY, ensure_ascii=False)])

    result = ItineraryGenerator(client=client).generate(make_trip_request())

    assert json.loads(result) == VALID_ITINERARY
    assert len(client.calls) == 1
    assert client.calls[0][1] == {}


def test_generate_extracts_json_from_markdown_and_explanatory_text():
    response = (
        "生成结果如下:\n```json\n"
        + json.dumps(VALID_ITINERARY, ensure_ascii=False)
        + "\n```\n请查收。"
    )
    client = FakeMomaClient([response])

    result = ItineraryGenerator(client=client).generate(make_trip_request())

    assert json.loads(result) == VALID_ITINERARY


def test_generate_joins_content_parts_like_reference_project():
    content_parts = [
        {"text": "前置说明\n"},
        {"text": json.dumps(VALID_ITINERARY, ensure_ascii=False)},
    ]
    client = FakeMomaClient([content_parts])

    result = ItineraryGenerator(client=client).generate(make_trip_request())

    assert json.loads(result) == VALID_ITINERARY


def test_generate_sends_request_context_through_prompt_builder():
    client = FakeMomaClient([json.dumps(VALID_ITINERARY, ensure_ascii=False)])

    ItineraryGenerator(client=client).generate(make_trip_request())

    messages = client.calls[0][0]
    content = "\n".join(message["content"] for message in messages)
    assert "杭州" in content
    assert "2026-10-01" in content
    assert "2026-10-04" in content
    assert "2" in content
    assert "美食" in content
    assert "历史文化" in content


def test_generate_repairs_invalid_json_once():
    client = FakeMomaClient(
        [
            "这不是 JSON",
            json.dumps(VALID_ITINERARY, ensure_ascii=False),
        ]
    )

    result = ItineraryGenerator(client=client).generate(make_trip_request())

    assert json.loads(result) == VALID_ITINERARY
    assert len(client.calls) == 2
    repair_messages = client.calls[1][0]
    repair_content = "\n".join(message["content"] for message in repair_messages)
    assert "修复" in repair_content
    assert "这不是 JSON" in repair_content


def test_generate_repairs_empty_response_once():
    client = FakeMomaClient(
        [
            "   ",
            json.dumps(VALID_ITINERARY, ensure_ascii=False),
        ]
    )

    result = ItineraryGenerator(client=client).generate(make_trip_request())

    assert json.loads(result) == VALID_ITINERARY
    assert len(client.calls) == 2


def test_generate_uses_validator_and_repairs_validation_failure():
    client = FakeMomaClient(
        [
            json.dumps({"summary": "缺少必要字段"}, ensure_ascii=False),
            json.dumps(VALID_ITINERARY, ensure_ascii=False),
        ]
    )
    validated = []

    def validator(payload):
        validated.append(payload)
        if "days" not in payload:
            raise ValueError("缺少 days")

    result = ItineraryGenerator(client=client, validator=validator).generate(make_trip_request())

    assert json.loads(result) == VALID_ITINERARY
    assert len(validated) == 2
    assert len(client.calls) == 2


def test_generate_raises_stable_error_after_repair_limit():
    client = FakeMomaClient(["坏响应", "仍然不是 JSON"])

    with pytest.raises(ItineraryGenerationError) as exc_info:
        ItineraryGenerator(client=client).generate(make_trip_request())

    assert exc_info.value.code == "MOMA_INVALID_RESPONSE"
    assert len(client.calls) == 2
    assert "坏响应" not in str(exc_info.value)


def test_generate_maps_timeout_to_stable_error_without_repair():
    client = FakeMomaClient([TimeoutError("upstream timed out")])

    with pytest.raises(ItineraryGenerationError) as exc_info:
        ItineraryGenerator(client=client).generate(make_trip_request())

    assert exc_info.value.code == "MOMA_TIMEOUT"
    assert len(client.calls) == 1


def test_generate_does_not_repair_more_than_configured_limit():
    client = FakeMomaClient(["坏响应", "坏响应", json.dumps(VALID_ITINERARY)])

    with pytest.raises(ItineraryGenerationError) as exc_info:
        ItineraryGenerator(client=client, max_repair_attempts=1).generate(make_trip_request())

    assert exc_info.value.code == "MOMA_INVALID_RESPONSE"
    assert len(client.calls) == 2
