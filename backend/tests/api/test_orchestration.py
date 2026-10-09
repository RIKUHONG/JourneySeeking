"""Offline P2-07 orchestration and critic tests."""

import json
from datetime import date

import pytest

from backend.app.knowledge import KnowledgeChunk
from backend.app.models.schemas import Itinerary, TripRequest
from backend.app.services.orchestration import (
    CriticRejectedError,
    ItineraryCritic,
    OrchestrationError,
    StepStatus,
    TripOrchestrator,
)
from backend.app.services.trip_service import TripService


def request(*, budget: float | None = 500) -> TripRequest:
    return TripRequest(
        destination="杭州",
        start_date=date(2026, 10, 10),
        end_date=date(2026, 10, 12),
        budget=budget,
        preferences=["文化"],
    )


def payload(*, total: float = 60) -> dict:
    return {
        "destination": "杭州",
        "start_date": "2026-10-10",
        "end_date": "2026-10-12",
        "summary": "杭州三日游",
        "days": [
            {
                "date": f"2026-10-{day}",
                "title": f"第 {day - 9} 天",
                "activities": [
                    {
                        "time": "09:00",
                        "name": "城市漫步",
                        "description": "步行参观",
                        "estimated_cost": 10,
                    }
                ],
            }
            for day in range(10, 13)
        ],
        "total_estimated_cost": total,
    }


class Generator:
    def __init__(self, result: dict | None = None) -> None:
        self.result = result or payload()
        self.last_candidate_pool = None
        self.last_candidate_diagnostics = None
        self.knowledge_chunks = ()
        self.call_count = 0

    def generate(self, trip_request, *, knowledge_chunks=()):
        self.call_count += 1
        self.knowledge_chunks = tuple(knowledge_chunks)
        return json.dumps(self.result, ensure_ascii=False)


class Knowledge:
    def search(self, destination: str, query: str, top_k: int = 5):
        assert destination == "杭州"
        assert "文化" in query
        return [
            KnowledgeChunk(
                "chunk-1", "杭州", "历史文化", "灵隐寺适合文化主题。", "curated.md", "2026-10-01"
            )
        ]


def test_orchestrator_runs_bounded_pipeline_and_passes_cited_knowledge() -> None:
    generator = Generator()
    result = TripOrchestrator(TripService(generator), knowledge=Knowledge()).run(request())

    assert result.critic.accepted
    assert result.knowledge_chunks[0].source == "curated.md"
    assert generator.knowledge_chunks == result.knowledge_chunks
    assert [step.name for step in result.trace] == [
        "city_resolution",
        "knowledge_retrieval",
        "itinerary_generation",
        "candidate_quality",
        "map_enrichment",
        "weather_enrichment",
        "critic",
    ]
    assert result.trace[3].status is StepStatus.DEGRADED


def test_knowledge_failure_degrades_without_blocking_base_itinerary() -> None:
    class BrokenKnowledge:
        def search(self, destination, query, top_k=5):
            raise RuntimeError("private knowledge failure")

    result = TripOrchestrator(TripService(Generator()), knowledge=BrokenKnowledge()).run(request())
    step = next(item for item in result.trace if item.name == "knowledge_retrieval")
    assert step.status is StepStatus.DEGRADED
    assert "private knowledge failure" not in (step.detail or "")


def test_max_steps_is_enforced() -> None:
    with pytest.raises(OrchestrationError) as error:
        TripOrchestrator(TripService(Generator()), knowledge=Knowledge(), max_steps=1).run(
            request()
        )
    assert error.value.code == "MAX_STEPS_EXCEEDED"


def test_step_timeout_is_enforced() -> None:
    times = iter([0.0, 2.0])
    with pytest.raises(OrchestrationError) as error:
        TripOrchestrator(
            TripService(Generator()), step_timeout_seconds=1, clock=lambda: next(times)
        ).run(request())
    assert error.value.code == "STEP_TIMEOUT"
    assert error.value.trace[-1].failure_category == "timeout"


def test_knowledge_timeout_is_not_degraded_or_followed_by_generation() -> None:
    generator = Generator()
    times = iter([0.0, 0.1, 0.1, 2.0])

    with pytest.raises(OrchestrationError) as error:
        TripOrchestrator(
            TripService(generator),
            knowledge=Knowledge(),
            step_timeout_seconds=1,
            clock=lambda: next(times),
        ).run(request())

    assert error.value.code == "STEP_TIMEOUT"
    assert [step.name for step in error.value.trace] == [
        "city_resolution",
        "knowledge_retrieval",
    ]
    assert error.value.trace[-1].status is StepStatus.FAILED
    assert error.value.trace[-1].failure_category == "timeout"
    assert generator.call_count == 0


def test_critic_rejects_budget_violation() -> None:
    with pytest.raises(CriticRejectedError) as error:
        TripOrchestrator(TripService(Generator(payload(total=600)))).run(request(budget=500))
    assert {finding.code for finding in error.value.report.findings} == {"BUDGET_EXCEEDED"}


def test_critic_rejects_untrusted_verified_poi_and_route() -> None:
    data = payload()
    first, second = data["days"][0]["activities"] * 2
    first.update(
        poi_id="outside", poi_status="verified", latitude=30.2, longitude=120.1, map_source="amap"
    )
    second.update(
        poi_id="outside-2",
        poi_status="verified",
        latitude=30.3,
        longitude=120.2,
        map_source="amap",
        route_status="verified",
        route_from_previous={
            "mode": "walking",
            "distance_meters": 100,
            "duration_seconds": 60,
            "source": "unknown",
        },
    )
    data["days"][0]["activities"] = [first, second]
    itinerary = Itinerary.model_validate(data)
    report = ItineraryCritic().review(request(), itinerary, trusted_poi_ids={"allowed"})
    codes = {finding.code for finding in report.findings}
    assert "POI_SOURCE_INVALID" in codes
    assert "ROUTE_SOURCE_INVALID" in codes


def test_critic_rejects_facts_attached_to_unknown_weather() -> None:
    data = payload()
    data["days"][0]["weather"] = {"status": "unknown", "condition": "晴"}
    report = ItineraryCritic().review(request(), Itinerary.model_validate(data))
    assert {finding.code for finding in report.findings} == {"UNKNOWN_WEATHER_HAS_FACTS"}
