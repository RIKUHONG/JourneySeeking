"""Verify both generation runtimes keep the same HTTP and storage weather contract."""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.integrations.contracts import DailyForecast
from backend.app.integrations.mock_weather_service import MockWeatherService
from backend.app.main import app, get_trip_orchestrator, get_trip_repository
from backend.app.services.langgraph_orchestration import LangGraphTripOrchestrator
from backend.app.services.orchestration import TripOrchestrator
from backend.app.services.trip_service import TripService
from backend.app.services.weather_enrichment import WeatherEnrichmentService
from backend.app.storage import SQLiteTripRepository

START = date(2026, 10, 13)
REQUEST = {
    "destination": "杭州",
    "start_date": START.isoformat(),
    "end_date": (START + timedelta(days=2)).isoformat(),
    "budget": 500,
}


class Generator:
    candidate_provider = None
    last_candidate_pool = None
    last_candidate_diagnostics = None

    def __init__(self):
        self.last_usage = {}

    def generate(self, request, **kwargs):
        return json.dumps(
            {
                "destination": request.destination,
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "summary": "杭州三日游",
                "days": [
                    {
                        "date": (START + timedelta(days=index)).isoformat(),
                        "title": f"第 {index + 1} 天",
                        "activities": [
                            {
                                "time": "09:00",
                                "name": "城市漫步",
                                "description": "步行参观",
                                "estimated_cost": 10,
                            }
                        ],
                    }
                    for index in range(3)
                ],
                "total_estimated_cost": 30,
            },
            ensure_ascii=False,
        )


@pytest.mark.parametrize("runtime", ["legacy", "langgraph"])
def test_weather_http_and_saved_version_contract_match_across_runtimes(tmp_path, runtime):
    forecasts = [
        DailyForecast(
            date=START + timedelta(days=index),
            condition="小雨" if index == 1 else "晴",
            low_celsius=15 + index,
            high_celsius=24 + index,
            source="Open-Meteo",
            fetched_at="2026-10-13T08:00:00+00:00",
        )
        for index in range(3)
    ]
    service = TripService(
        Generator(),
        weather_enricher=WeatherEnrichmentService(
            MockWeatherService(forecasts={"杭州": forecasts})
        ),
    )
    orchestrator_type = TripOrchestrator if runtime == "legacy" else LangGraphTripOrchestrator
    repository = SQLiteTripRepository(tmp_path / "trips.sqlite3")
    app.dependency_overrides[get_trip_orchestrator] = lambda: orchestrator_type(service)
    app.dependency_overrides[get_trip_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            generated = client.post("/api/trip/generate", json=REQUEST)
            assert generated.status_code == 200
            body = generated.json()
            assert [day["date"] for day in body["days"]] == [
                forecast.date.isoformat() for forecast in forecasts
            ]
            assert [day["weather"]["condition"] for day in body["days"]] == ["晴", "小雨", "晴"]
            assert all(day["weather"]["source"] == "Open-Meteo" for day in body["days"])
            assert all(day["weather"]["fetched_at"] for day in body["days"])

            saved = client.post("/api/trip/save", json={"itinerary": body})
            assert saved.status_code == 200
            assert saved.json()["version"] == 1
            loaded = client.get(f"/api/trip/{saved.json()['trip_id']}")
            assert loaded.status_code == 200
            assert [day["weather"] for day in loaded.json()["days"]] == [
                day["weather"] for day in saved.json()["days"]
            ]
    finally:
        app.dependency_overrides.clear()
