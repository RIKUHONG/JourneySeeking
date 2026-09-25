from types import SimpleNamespace

from backend.app.services.prompt_builder import PromptBuilder


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


def flatten_message_content(messages):
    return "\n".join(message["content"] for message in messages)


def test_prompt_includes_required_trip_context():
    messages = PromptBuilder().build_messages(make_trip_request())

    content = flatten_message_content(messages)

    assert "杭州" in content
    assert "2026-10-01" in content
    assert "2026-10-04" in content
    assert "2" in content
    assert "美食" in content
    assert "历史文化" in content


def test_prompt_includes_optional_constraints_when_provided():
    messages = PromptBuilder().build_messages(make_trip_request())

    content = flatten_message_content(messages)

    assert "10000" in content
    assert "relaxed" in content
    assert "少辣" in content
    assert "four_star" in content
    assert "不要早起" in content


def test_prompt_requires_contract_json_only_response():
    messages = PromptBuilder().build_messages(make_trip_request())

    content = flatten_message_content(messages)

    assert "只返回 JSON" in content
    assert "不要返回 Markdown" in content
    assert "destination" in content
    assert "start_date" in content
    assert "end_date" in content
    assert "summary" in content
    assert "days" in content
    assert "activities" in content
    assert "total_estimated_cost" in content


def test_prompt_handles_missing_optional_constraints_without_placeholder_text():
    request = make_trip_request(
        budget=None,
        preferences=[],
        pace=None,
        dietary_preferences=[],
        hotel_level=None,
        special_notes=None,
    )

    messages = PromptBuilder().build_messages(request)
    content = flatten_message_content(messages)

    assert "杭州" in content
    assert "2026-10-01" in content
    assert "2026-10-04" in content
    assert "未提供" in content
    assert "None" not in content
    assert "budget: null" not in content
    assert "preferences: null" not in content
    assert "pace: null" not in content
    assert "dietary_preferences: null" not in content
    assert "hotel_level: null" not in content
    assert "special_notes: null" not in content


def test_prompt_does_not_include_secret_or_internal_path_text():
    messages = PromptBuilder().build_messages(make_trip_request())

    content = flatten_message_content(messages).lower()

    assert "api_key" not in content
    assert "authorization" not in content
    assert "bearer" not in content
    assert "traceback" not in content
    assert "e:\\" not in content
    assert "c:\\" not in content
