"""Offline P3-01 LangGraph state graph acceptance tests."""

import json
from datetime import date, timedelta

import pytest

from backend.app.integrations.contracts import DailyForecast
from backend.app.integrations.errors import FailureReason, WeatherServiceError
from backend.app.knowledge import KnowledgeChunk
from backend.app.models.schemas import TripRequest
from backend.app.services.langgraph_orchestration import LangGraphTripOrchestrator
from backend.app.services.orchestration import CriticRejectedError, OrchestrationError
from backend.app.services.poi_candidates import PoiCandidate, PoiCandidatePool, PoiCategory
from backend.app.services.trip_service import TripService
from backend.app.services.weather_enrichment import WeatherEnrichmentService


def request(*, budget: float | None = 500) -> TripRequest:
    return TripRequest(
        destination="杭州",
        start_date=date(2026, 10, 10),
        end_date=date(2026, 10, 12),
        budget=budget,
        preferences=["文化"],
    )


def payload(
    trip_request: TripRequest,
    *,
    total: float = 3,
    valid_dates: bool = True,
    activity_cost: float = 1,
) -> dict:
    days = []
    day_count = (trip_request.end_date - trip_request.start_date).days + 1
    for offset in range(day_count):
        day = trip_request.start_date + timedelta(days=offset)
        if not valid_dates and offset == 0:
            day += timedelta(days=1)
        days.append(
            {
                "date": str(day),
                "title": f"第 {offset + 1} 天",
                "activities": [
                    {
                        "time": "09:00",
                        "name": "城市漫步",
                        "description": "步行参观",
                        "estimated_cost": activity_cost,
                    }
                ],
            }
        )
    return {
        "destination": trip_request.destination,
        "start_date": str(trip_request.start_date),
        "end_date": str(trip_request.end_date),
        "summary": "杭州三日游",
        "days": days,
        "total_estimated_cost": total,
    }


class RecordingGenerator:
    candidate_provider = None

    def __init__(self, responses: list[dict] | None = None) -> None:
        self.responses = responses or []
        self.calls = 0
        self.contexts: list[dict] = []
        self.candidate_pools = []
        self.last_candidate_pool = None
        self.last_candidate_diagnostics = None
        self.last_usage = {}

    def generate(
        self,
        trip_request: TripRequest,
        *,
        knowledge_chunks=(),
        candidate_pool=None,
        planning_context=None,
        candidate_diagnostics=None,
    ) -> str:
        self.calls += 1
        self.contexts.append(planning_context or {})
        self.candidate_pools.append(candidate_pool)
        current = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        return json.dumps(current or payload(trip_request), ensure_ascii=False)


class Knowledge:
    def search(self, destination: str, query: str, top_k: int = 5):
        return [KnowledgeChunk("chunk-1", destination, "历史", "文化路线", "guide.md", "v1")]


class Weather:
    source = "fake-weather"

    def forecast(self, city: str, *, days: int = 3):
        assert city == "杭州"
        return [
            DailyForecast(
                date=date(2026, 10, 10) + timedelta(days=offset),
                condition="小雨" if offset == 1 else "晴",
                low_celsius=16 + offset,
                high_celsius=24 + offset,
            )
            for offset in range(days)
        ]


class BrokenWeather:
    def forecast_window(self, city, *, start_date, end_date):
        raise WeatherServiceError(FailureReason.TIMEOUT)


class PartialWeather:
    source = "Open-Meteo"

    def forecast_window(self, city, *, start_date, end_date):
        return [
            DailyForecast(
                date=start_date,
                condition="晴",
                low_celsius=15,
                high_celsius=24,
                source=self.source,
                fetched_at="2026-10-13T08:00:00+00:00",
            ),
            DailyForecast(
                date=end_date,
                condition="小雨",
                low_celsius=16,
                high_celsius=23,
                source=self.source,
                fetched_at="2026-10-13T08:00:00+00:00",
            ),
        ]


class WindowWeather:
    source = "Open-Meteo"

    def __init__(self):
        self.calls = []

    def forecast_window(self, city, *, start_date, end_date):
        self.calls.append((city, start_date, end_date))
        return [
            DailyForecast(
                date=start_date + timedelta(days=offset),
                condition="小雨" if offset == 2 else "晴",
                low_celsius=15,
                high_celsius=24,
                source="Open-Meteo",
                fetched_at="2026-10-13T08:00:00+00:00",
            )
            for offset in range((end_date - start_date).days + 1)
        ]


def make_orchestrator(generator, *, weather=None, knowledge=None, **kwargs):
    weather_enricher = WeatherEnrichmentService(weather) if weather is not None else None
    return LangGraphTripOrchestrator(
        TripService(generator, weather_enricher=weather_enricher),
        knowledge=knowledge,
        **kwargs,
    )


def test_graph_runs_pre_generation_evidence_and_replays_redacted_trace() -> None:
    generator = RecordingGenerator([payload(request())])
    orchestrator = make_orchestrator(generator, weather=Weather(), knowledge=Knowledge())

    result = orchestrator.run(request(), request_id="req_p3_01")

    names = [step.name for step in result.trace]
    assert names.index("query_weather_7d") < names.index("generate_base_itinerary")
    assert names.index("retrieve_knowledge") < names.index("generate_base_itinerary")
    assert names.index("search_poi_candidates") < names.index("generate_base_itinerary")
    assert generator.contexts[0]["weather_context"]["2026-10-11"]["condition"] == "小雨"
    assert result.itinerary.days[1].weather is not None
    assert result.itinerary.days[1].weather.condition == "小雨"
    assert [step.name for step in orchestrator.replay_trace()] == names
    assert all("api_key" not in repr(step).lower() for step in result.trace)


def test_weather_context_covers_a_seven_day_request_by_date() -> None:
    trip_request = TripRequest(
        destination="杭州",
        start_date=date(2026, 10, 10),
        end_date=date(2026, 10, 16),
    )
    generator = RecordingGenerator([payload(trip_request, total=7)])
    orchestrator = make_orchestrator(generator, weather=Weather())

    result = orchestrator.run(trip_request)

    assert len(generator.contexts[0]["weather_context"]) == 7
    assert len(result.itinerary.days) == 7
    assert all(day.weather is not None for day in result.itinerary.days)


def test_open_meteo_window_reaches_planner_and_authoritative_weather() -> None:
    trip_request = TripRequest(
        destination="杭州",
        start_date=date(2026, 10, 14),
        end_date=date(2026, 10, 20),
    )
    generator = RecordingGenerator([payload(trip_request, total=7)])
    weather = WindowWeather()
    orchestrator = make_orchestrator(generator, weather=weather)

    result = orchestrator.run(trip_request)

    assert weather.calls == [("杭州", trip_request.start_date, trip_request.end_date)]
    context = generator.contexts[0]["weather_context"]
    assert len(context) == 7
    assert context["2026-10-16"]["condition"] == "小雨"
    assert context["2026-10-16"]["source"] == "Open-Meteo"
    assert all(day.weather.source == "Open-Meteo" for day in result.itinerary.days)
    assert result.itinerary.days[2].weather_advice
    assert result.itinerary.days[2].weather.fetched_at == "2026-10-13T08:00:00+00:00"


def test_partial_weather_reaches_planner_as_unknown_and_degrades() -> None:
    trip_request = TripRequest(
        destination="杭州",
        start_date=date(2026, 10, 10),
        end_date=date(2026, 10, 16),
    )
    generator = RecordingGenerator([payload(trip_request, total=7)])
    orchestrator = make_orchestrator(generator, weather=PartialWeather())

    result = orchestrator.run(trip_request)

    context = generator.contexts[0]["weather_context"]
    assert [item["status"] for item in context.values()] == [
        "available",
        "unknown",
        "unknown",
        "unknown",
        "unknown",
        "unknown",
        "available",
    ]
    weather_status = next(step for step in result.trace if step.name == "query_weather_7d")
    assert weather_status.status.value == "degraded"
    assert weather_status.failure_category == "partial_coverage"
    assert result.itinerary.days[1].weather.status == "unknown"
    assert result.itinerary.days[1].weather.condition is None
    assert result.itinerary.days[1].weather_advice == []


def test_all_unknown_weather_uses_degraded_planning_context() -> None:
    trip_request = request()
    generator = RecordingGenerator([payload(trip_request)])

    class EmptyWeather:
        def forecast_window(self, city, *, start_date, end_date):
            return []

    result = make_orchestrator(generator, weather=EmptyWeather()).run(trip_request)

    assert generator.contexts[0]["planning_context_status"]["weather"] == "degraded"
    assert all(
        item == {"status": "unknown"} for item in generator.contexts[0]["weather_context"].values()
    )
    assert all(
        day.weather.status == "unknown" and not day.weather_advice for day in result.itinerary.days
    )


def test_weather_timeout_is_redacted_to_stable_failure_reason() -> None:
    generator = RecordingGenerator([payload(request())])
    orchestrator = make_orchestrator(generator, weather=BrokenWeather())

    result = orchestrator.run(request())

    weather_status = next(step for step in result.trace if step.name == "query_weather_7d")
    assert weather_status.status.value == "degraded"
    assert weather_status.failure_category == "timeout"
    assert all(day.weather.status == "unknown" for day in result.itinerary.days)


def test_model_weather_claim_is_replaced_by_authoritative_evidence() -> None:
    trip_request = request()
    data = payload(trip_request)
    for day in data["days"]:
        day["weather"] = {
            "status": "available",
            "condition": "模型声称的晴天",
            "low_celsius": 99,
            "high_celsius": 100,
            "source": "model",
        }
    generator = RecordingGenerator([data])
    result = make_orchestrator(generator, weather=WindowWeather()).run(trip_request)

    assert all(day.weather.source == "Open-Meteo" for day in result.itinerary.days)
    assert all(day.weather.condition != "模型声称的晴天" for day in result.itinerary.days)
    assert result.critic.accepted


class AuthorityBypassGraph(LangGraphTripOrchestrator):
    def _apply_authoritative_weather(self, state):
        return {"itinerary_draft": state["itinerary_draft"]}


def test_critic_rejects_weather_fact_conflict_when_authority_step_is_bypassed() -> None:
    trip_request = request()
    data = payload(trip_request)
    for day in data["days"]:
        day["weather"] = {
            "status": "available",
            "condition": "模型声称的晴天",
            "low_celsius": 99,
            "high_celsius": 100,
            "source": "model",
        }
    generator = RecordingGenerator([data])
    weather_enricher = WeatherEnrichmentService(WindowWeather())
    orchestrator = AuthorityBypassGraph(
        TripService(generator, weather_enricher=weather_enricher), max_repair_attempts=0
    )

    with pytest.raises(CriticRejectedError) as error:
        orchestrator.run(trip_request)

    assert any(
        finding.code == "WEATHER_EVIDENCE_MISMATCH" for finding in error.value.report.findings
    )


def test_optional_failures_degrade_without_blocking_generation() -> None:
    generator = RecordingGenerator([payload(request())])
    orchestrator = make_orchestrator(generator, weather=BrokenWeather())

    result = orchestrator.run(request())

    status_by_name = {step.name: step.status.value for step in result.trace}
    assert status_by_name["retrieve_knowledge"] == "degraded"
    assert status_by_name["search_poi_candidates"] == "degraded"
    assert status_by_name["query_weather_7d"] == "degraded"
    assert all(
        day.weather is not None and day.weather.status == "unknown" for day in result.itinerary.days
    )


def test_candidate_search_happens_once_and_pool_reaches_planner() -> None:
    pool = PoiCandidatePool(
        city="杭州",
        candidates=(
            PoiCandidate("spot-1", "景点一", PoiCategory.SPOT, "杭州", 30.1, 120.1),
            PoiCandidate("spot-2", "景点二", PoiCategory.SPOT, "杭州", 30.2, 120.2),
            PoiCandidate("spot-3", "景点三", PoiCategory.SPOT, "杭州", 30.3, 120.3),
            PoiCandidate("meal-1", "餐厅", PoiCategory.MEAL, "杭州", 30.4, 120.4),
            PoiCandidate("hotel-1", "酒店", PoiCategory.HOTEL, "杭州", 30.5, 120.5),
        ),
    )
    generator = RecordingGenerator([payload(request())])
    calls = 0

    def provider(_request):
        nonlocal calls
        calls += 1
        return pool

    generator.candidate_provider = provider
    # Use a payload with unique trusted IDs so the base service can enforce the whitelist.
    data = payload(request())
    for index, day in enumerate(data["days"]):
        day["activities"][0]["poi_id"] = f"spot-{index + 1}"
        day["activities"][0]["poi_category"] = "spot"
    generator.responses = [data]
    orchestrator = make_orchestrator(generator)

    result = orchestrator.run(request())

    assert calls == 1
    assert generator.candidate_pools[0] is pool
    assert result.critic.accepted


def test_structural_failure_has_one_bounded_repair() -> None:
    trip_request = request()
    generator = RecordingGenerator(
        [payload(trip_request, valid_dates=False), payload(trip_request, valid_dates=True)]
    )
    orchestrator = make_orchestrator(generator, max_repair_attempts=1)

    result = orchestrator.run(trip_request)

    assert generator.calls == 2
    assert [step.name for step in result.trace].count("repair_structured_output") == 1
    assert result.critic.accepted


def test_critic_rejection_repairs_once_then_succeeds() -> None:
    trip_request = request(budget=2)
    generator = RecordingGenerator(
        [
            payload(trip_request, total=3, activity_cost=0.5),
            payload(trip_request, total=2, activity_cost=0.5),
        ]
    )
    orchestrator = make_orchestrator(generator, max_repair_attempts=1)

    result = orchestrator.run(trip_request)

    assert generator.calls == 2
    assert [step.name for step in result.trace].count("repair_with_critic_findings") == 1
    assert generator.contexts[-1]["critic_findings"][0]["code"] == "BUDGET_EXCEEDED"
    assert result.critic.accepted


def test_critic_rejection_after_repair_limit_is_stable_error() -> None:
    trip_request = request(budget=2)
    generator = RecordingGenerator([payload(trip_request, total=3), payload(trip_request, total=3)])
    orchestrator = make_orchestrator(generator, max_repair_attempts=1)

    with pytest.raises(CriticRejectedError) as error:
        orchestrator.run(trip_request)

    assert error.value.code == "CRITIC_REJECTED"
    assert [step.name for step in error.value.trace].count("repair_with_critic_findings") == 1


def test_step_limit_is_enforced_before_external_preparation() -> None:
    generator = RecordingGenerator([payload(request())])
    orchestrator = make_orchestrator(generator, max_steps=1)

    with pytest.raises(OrchestrationError) as error:
        orchestrator.run(request())

    assert error.value.code == "MAX_STEPS_EXCEEDED"
    assert generator.calls == 0
