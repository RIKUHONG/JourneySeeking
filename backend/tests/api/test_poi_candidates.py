import json

import pytest

from backend.app.integrations.contracts import Coordinates, Place, Route
from backend.app.integrations.mock_map_service import MockMapService
from backend.app.models.schemas import TripRequest
from backend.app.services.map_enrichment import MapEnrichmentService
from backend.app.services.poi_candidates import (
    PoiCandidate,
    PoiCandidatePool,
    PoiCategory,
    collect_candidate_pool,
)
from backend.app.services.trip_service import ItineraryValidationError, TripService
from backend.app.services.weather_enrichment import WeatherEnrichmentService


def test_candidate_pool_is_city_scoped_and_categorized():
    pool = collect_candidate_pool(
        MockMapService(
            places=[
                Place("spot-1", "景点", "杭州市西湖区", Coordinates(120.1, 30.2)),
                Place("meal-1", "美食", "杭州市西湖区", Coordinates(120.2, 30.3)),
                Place("hotel-1", "酒店", "杭州市西湖区", Coordinates(120.3, 30.4)),
            ]
        ),
        "杭州市",
    )
    assert {item.category for item in pool.candidates} == set(PoiCategory)
    assert all(item.poi_id for item in pool.candidates)
    assert pool.by_id["spot-1"].category == PoiCategory.SPOT


def test_candidate_pool_rejects_unknown_and_duplicate_ids():
    pool = collect_candidate_pool(
        MockMapService(places=[Place("spot-1", "景点", "杭州市", Coordinates(120.1, 30.2))]),
        "杭州市",
    )
    with pytest.raises(ValueError, match="outside"):
        pool.validate_ids(["unknown"])
    with pytest.raises(ValueError, match="duplicate"):
        pool.validate_ids(["spot-1", "spot-1"])


def test_candidate_ids_are_hydrated_and_adjacent_routes_are_planned():
    first = PoiCandidate("spot-1", "西湖", PoiCategory.SPOT, "杭州市西湖区", 30.2, 120.1)
    second = PoiCandidate("spot-2", "灵隐寺", PoiCategory.SPOT, "杭州市西湖区", 30.3, 120.2)
    pool = PoiCandidatePool("杭州市", (first, second))
    service = MockMapService(
        routes={(Coordinates(120.1, 30.2), Coordinates(120.2, 30.3), "driving"): Route(2500, 600)}
    )

    class Generator:
        last_candidate_pool = pool

        def generate(self, request):
            return json.dumps(
                {
                    "destination": request.destination,
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-03",
                    "summary": "test",
                    "days": [
                        {
                            "date": "2026-10-01",
                            "title": "day",
                            "activities": [
                                {
                                    "time": "09:00",
                                    "name": "ignored",
                                    "poi_id": "spot-1",
                                    "poi_category": "spot",
                                    "description": "x",
                                    "estimated_cost": 0,
                                },
                                {
                                    "time": "11:00",
                                    "name": "ignored",
                                    "poi_id": "spot-2",
                                    "poi_category": "spot",
                                    "description": "x",
                                    "estimated_cost": 0,
                                },
                            ],
                        },
                        {"date": "2026-10-02", "title": "day", "activities": []},
                        {"date": "2026-10-03", "title": "day", "activities": []},
                    ],
                    "total_estimated_cost": 0,
                }
            )

    result = TripService(Generator(), MapEnrichmentService(service)).generate(
        TripRequest(destination="杭州市", start_date="2026-10-01", end_date="2026-10-03")
    )
    activities = result.days[0].activities
    assert [activity.name for activity in activities] == ["西湖", "灵隐寺"]
    assert activities[1].route_status == "verified"


def test_candidate_mode_rejects_missing_or_out_of_pool_ids():
    pool = PoiCandidatePool(
        "杭州市",
        (PoiCandidate("spot-1", "西湖", PoiCategory.SPOT, "杭州市", 30.2, 120.1),),
    )

    class Generator:
        last_candidate_pool = pool

        def generate(self, request):
            return json.dumps(
                {
                    "destination": request.destination,
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-03",
                    "summary": "test",
                    "days": [
                        {
                            "date": "2026-10-01",
                            "title": "day",
                            "activities": [
                                {
                                    "time": "09:00",
                                    "name": "x",
                                    "poi_id": "outside",
                                    "poi_category": "spot",
                                    "description": "x",
                                    "estimated_cost": 0,
                                }
                            ],
                        },
                        {"date": "2026-10-02", "title": "day", "activities": []},
                        {"date": "2026-10-03", "title": "day", "activities": []},
                    ],
                    "total_estimated_cost": 0,
                }
            )

    with pytest.raises(ItineraryValidationError):
        TripService(Generator()).generate(
            TripRequest(destination="杭州市", start_date="2026-10-01", end_date="2026-10-03")
        )


def test_real_chain_repairs_destination_and_duplicate_poi_before_weather_enrichment():
    pool = PoiCandidatePool(
        "杭州市",
        (PoiCandidate("spot-1", "西湖", PoiCategory.SPOT, "杭州市", 30.2, 120.1),),
    )

    class Generator:
        last_candidate_pool = pool

        def generate(self, request):
            activity = {
                "time": "09:00",
                "name": "西湖",
                "poi_id": "spot-1",
                "poi_category": "spot",
                "description": "游览西湖",
                "estimated_cost": 0,
            }
            return json.dumps(
                {
                    "destination": "苏州市",
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-03",
                    "summary": "test",
                    "days": [
                        {
                            "date": "2026-10-01",
                            "title": "day one",
                            "activities": [activity, {**activity, "time": "10:00"}],
                        },
                        {"date": "2026-10-02", "title": "day two", "activities": []},
                        {"date": "2026-10-03", "title": "day three", "activities": []},
                    ],
                    "total_estimated_cost": 0,
                },
                ensure_ascii=False,
            )

    class RecordingWeatherService:
        def __init__(self):
            self.calls = []

        def forecast(self, city, *, days):
            self.calls.append((city, days))
            return []

    weather_service = RecordingWeatherService()
    result = TripService(
        Generator(),
        MapEnrichmentService(MockMapService()),
        WeatherEnrichmentService(weather_service),
    ).generate(
        TripRequest(destination="杭州市", start_date="2026-10-01", end_date="2026-10-03")
    )

    assert result.destination == "杭州市"
    assert [activity.poi_id for activity in result.days[0].activities] == ["spot-1"]
    assert weather_service.calls == [("杭州市", 3)]
    assert all(day.weather is not None and day.weather.status == "unknown" for day in result.days)
