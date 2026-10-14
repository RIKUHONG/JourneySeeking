"""Versioned prompt and one-call-per-node regression checks."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.integrations.mock_moma_client import MockMomaClient, MockMomaResponse
from backend.app.models.schemas import Itinerary, TripEditRequest, TripRequest
from backend.app.services.itinerary_generator import ItineraryGenerationError, ItineraryGenerator
from backend.app.services.langgraph_orchestration import LangGraphTripOrchestrator
from backend.app.services.orchestration import OrchestrationError
from backend.app.services.prompt_builder import PromptBuilder
from backend.app.services.prompt_registry import (
    COMPAT_VERSION,
    DAY_EDIT,
    GENERATION,
    P2_VERSION,
    TARGET_VERSION,
    get_prompt,
)
from backend.app.services.trip_edit import (
    MomaDayEditor,
    TripEditError,
    TripEditService,
    TripEditTimeoutError,
)
from backend.app.services.trip_service import TripService
from backend.app.storage import SQLiteTripRepository
from backend.eval.prompt_ab import capture_fixture, evaluate

FIXTURES = Path(__file__).resolve().parents[2] / "eval/fixtures/p3_03_smoke.json"
AB_FIXTURES = Path(__file__).resolve().parents[2] / "eval/fixtures/p3_03_ab.json"


def sample():
    return json.loads(FIXTURES.read_text(encoding="utf-8"))["cases"][0]


def graph(responses):
    client = MockMomaClient(responses)
    generator = ItineraryGenerator(client, prompt_builder=PromptBuilder(COMPAT_VERSION))
    return LangGraphTripOrchestrator(TripService(generator)), generator, client


def test_registry_has_frozen_versions_and_model_only_schema():
    with pytest.raises(ValueError, match="unknown prompt version"):
        get_prompt(GENERATION, "missing")

    generation_schema = get_prompt(GENERATION, TARGET_VERSION).output_schema()
    edit_schema = get_prompt(DAY_EDIT, "v1").output_schema()
    assert "weather" not in json.dumps(generation_schema)
    assert "route_from_previous" not in json.dumps(generation_schema)
    assert set(edit_schema["properties"]) == {"date", "title", "activities"}


def test_v1_ignores_preflight_weather_while_compat_and_v2_include_it():
    request = TripRequest.model_validate(sample()["request"])
    context = {"weather_context": {"2026-10-14": {"status": "available", "condition": "小雨"}}}
    rendered = {
        version: "\n".join(
            message["content"]
            for message in PromptBuilder(version).build_messages(request, planning_context=context)
        )
        for version in (P2_VERSION, COMPAT_VERSION, TARGET_VERSION)
    }
    assert "小雨" not in rendered[P2_VERSION]
    assert "小雨" in rendered[COMPAT_VERSION]
    assert "小雨" in rendered[TARGET_VERSION]
    assert "JSON Schema" in rendered[TARGET_VERSION]


def test_repair_prompt_bounds_draft_and_reports_truncation():
    request = TripRequest.model_validate(sample()["request"])
    messages = PromptBuilder().build_repair_messages(
        request,
        kind="structured_repair",
        raw_content="X" * 16010,
        failure_code="MOMA_INVALID_RESPONSE",
    )

    assert '"draft_truncated_chars":10' in messages[1]["content"]
    assert "X" * 16000 in messages[1]["content"]
    assert "X" * 16001 not in messages[1]["content"]


def test_graph_structured_repair_is_exactly_one_extra_model_call():
    case = sample()
    orchestrator, generator, client = graph(
        [
            MockMomaResponse("not json", usage={"prompt_tokens": 10, "completion_tokens": 20}),
            MockMomaResponse(
                json.dumps(case["response"]),
                usage={"prompt_tokens": 30, "completion_tokens": 40},
            ),
        ]
    )
    generator.set_execution_context(
        request_id="req_test", runtime="langgraph", graph_version="trip-generation/v2"
    )

    result = orchestrator.run(TripRequest.model_validate(case["request"]))

    assert result.critic.accepted
    assert len(client.calls) == 2
    assert [record.prompt_key for record in generator.call_records] == [
        f"{GENERATION}/{COMPAT_VERSION}",
        "structured_repair/v1",
    ]
    assert generator.last_usage["total_tokens"] == 100
    assert [record.validation for record in generator.call_records] == ["rejected", "accepted"]
    assert generator.last_raw_content == ""
    assert generator.call_records[-1].request_id == "req_test"
    assert generator.call_records[-1].runtime == "langgraph"
    assert generator.call_records[-1].graph_version == "trip-generation/v2"
    assert '"validation_paths":["root"]' in client.calls[1][0][1]["content"]


def test_graph_repair_receives_business_validation_path():
    case = sample()
    invalid = json.loads(json.dumps(case["response"]))
    invalid["days"][0]["date"] = "2026-10-14"
    orchestrator, _, client = graph([json.dumps(invalid), json.dumps(case["response"])])

    result = orchestrator.run(TripRequest.model_validate(case["request"]))

    assert result.critic.accepted
    assert "days.date" in client.calls[1][0][1]["content"]


def test_graph_critic_repair_uses_findings_and_shared_limit():
    case = sample()
    bad = json.loads(json.dumps(case["response"]))
    bad["total_estimated_cost"] = 101
    orchestrator, generator, client = graph([json.dumps(bad), json.dumps(case["response"])])

    result = orchestrator.run(TripRequest.model_validate(case["request"]))

    assert result.critic.accepted
    assert len(client.calls) == 2
    assert generator.call_records[-1].prompt_key == "critic_repair/v1"
    assert "BUDGET_EXCEEDED" in client.calls[1][0][1]["content"]


def test_graph_does_not_hide_an_internal_repair_call():
    case = sample()
    orchestrator, generator, client = graph(["bad one", "bad two", json.dumps(case["response"])])

    with pytest.raises(OrchestrationError):
        orchestrator.run(TripRequest.model_validate(case["request"]))

    assert len(client.calls) == 2
    assert len(generator.call_records) == 2


def test_v2_rejects_server_owned_fields_and_logs_no_model_preview(caplog):
    case = sample()
    bad = json.loads(json.dumps(case["response"]))
    bad["days"][0]["activities"][0]["address"] = "SENSITIVE_MODEL_TEXT"
    generator = ItineraryGenerator(
        MockMomaClient([json.dumps(bad)]), prompt_builder=PromptBuilder(TARGET_VERSION)
    )

    with pytest.raises(ItineraryGenerationError):
        generator.generate(TripRequest.model_validate(case["request"]), allow_repair=False)

    assert generator.call_records[0].validation == "rejected"
    assert "SENSITIVE_MODEL_TEXT" not in caplog.text


def test_day_edit_parse_failure_does_not_log_raw_response(caplog):
    sentinel = "SENSITIVE_EDIT_RESPONSE"
    with caplog.at_level("DEBUG"), pytest.raises(TripEditError):
        TripEditService._parse_draft(sentinel)
    assert sentinel not in caplog.text


def test_day_edit_prompt_version_is_recorded():
    client = MockMomaClient(['{"date":"2026-10-14","title":"新标题","activities":[]}'])
    editor = MomaDayEditor(client)
    day = SimpleNamespace(model_dump=lambda **_: {"date": "2026-10-14"})
    itinerary = SimpleNamespace(
        destination="杭州",
        start_date=SimpleNamespace(isoformat=lambda: "2026-10-13"),
        end_date=SimpleNamespace(isoformat=lambda: "2026-10-15"),
    )

    editor.edit(itinerary, day, "调整安排")

    assert editor.call_records[0].prompt_key == "day_edit/v1"
    assert editor.call_records[0].schema_version == "day-edit-draft/v1"
    assert editor.call_records[0].runtime == "edit"
    assert "JSON Schema" in client.calls[0][0][1]["content"]


def test_day_edit_scope_rejection_updates_metadata_and_never_saves(tmp_path):
    case = sample()
    repository = SQLiteTripRepository(tmp_path / "trip.sqlite3")
    saved = repository.create(Itinerary.model_validate(case["response"]))
    draft = {"date": "2026-10-15", "title": "错日", "activities": []}
    editor = MomaDayEditor(MockMomaClient([json.dumps(draft)]))
    service = TripEditService(repository, editor)
    request = TripEditRequest(expected_version=1, date="2026-10-14", instruction="调整第二天安排")

    with pytest.raises(TripEditError):
        service.edit(saved.trip_id, request)

    assert editor.call_records[-1].validation == "rejected"
    assert editor.call_records[-1].failure_code == "EDIT_RULE_REJECTED"
    assert repository.get_current(saved.trip_id).version == 1


def test_day_edit_timeout_keeps_provider_failure_metadata(tmp_path):
    case = sample()
    repository = SQLiteTripRepository(tmp_path / "trip.sqlite3")
    saved = repository.create(Itinerary.model_validate(case["response"]))
    editor = MomaDayEditor(MockMomaClient([TimeoutError("private provider detail")]))
    request = TripEditRequest(expected_version=1, date="2026-10-14", instruction="调整第二天安排")

    with pytest.raises(TripEditTimeoutError):
        TripEditService(repository, editor).edit(saved.trip_id, request)

    assert editor.call_records[-1].validation == "failed"
    assert editor.call_records[-1].failure_code == "MOMA_TIMEOUT"


def test_offline_ab_report_blocks_default_switch_without_paired_model_samples():
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))

    report = evaluate(fixtures)

    assert report["hard_contract_pass"]
    assert report["case_count"] == 3
    assert not report["release_gate_pass"]
    assert (
        "paired_model_samples_missing_or_fewer_than_12_distinct_cases"
        in report["release_gate_reasons"]
    )
    assert set(report["by_version"]) == {P2_VERSION, COMPAT_VERSION, TARGET_VERSION}

    fixtures["cases"][0]["response"]["days"] = []
    assert not evaluate(fixtures)["hard_contract_pass"]


def test_real_sampling_fixture_has_distinct_anonymized_cases():
    fixtures = json.loads(AB_FIXTURES.read_text(encoding="utf-8"))

    assert fixtures["kind"] == "synthetic"
    assert len(fixtures["cases"]) >= 12
    assert len({case["id"] for case in fixtures["cases"]}) == len(fixtures["cases"])
    for case in fixtures["cases"]:
        request = TripRequest.model_validate(case["request"])
        assert 3 <= (request.end_date - request.start_date).days + 1 <= 7
        assert "response" not in case


def test_offline_ab_release_gate_detects_token_and_latency_regression():
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixtures["kind"] = "controlled_model_capture"
    for case in fixtures["cases"]:
        case["versions"] = {
            version: {
                "response": case["response"],
                "usage": {
                    "prompt_tokens": 300 if version == TARGET_VERSION else 100,
                    "completion_tokens": 300 if version == TARGET_VERSION else 100,
                },
                "duration_ms": 150 if version == TARGET_VERSION else 100,
            }
            for version in (P2_VERSION, COMPAT_VERSION, TARGET_VERSION)
        }

    report = evaluate(fixtures)

    assert "token_budget_exceeded" in report["release_gate_reasons"]
    assert "p95_latency_exceeded" in report["release_gate_reasons"]


def test_capture_uses_same_fixture_with_three_versioned_prompts():
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixtures["cases"] = fixtures["cases"][:1]
    client = MockMomaClient(
        [MockMomaResponse(json.dumps(fixtures["cases"][0]["response"])) for _ in range(6)]
    )

    captured = capture_fixture(fixtures, client, repeats=2)

    assert captured["kind"] == "controlled_model_capture"
    assert fixtures["kind"] == "synthetic"
    assert len(client.calls) == 6
    assert [case["id"] for case in captured["cases"]] == [
        "three_day_rain_poi_r1",
        "three_day_rain_poi_r2",
    ]
    assert {case["base_case_id"] for case in captured["cases"]} == {"three_day_rain_poi"}
    assert set(captured["cases"][0]["versions"]) == {P2_VERSION, COMPAT_VERSION, TARGET_VERSION}
    assert all("Authorization" not in str(call) for call in client.calls)
