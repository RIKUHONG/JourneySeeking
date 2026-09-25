"""HTTP-level tests for the P0 trip-generation contract."""

from fastapi.testclient import TestClient

from backend.app.main import app, get_trip_service
from backend.app.models.schemas import Itinerary
from backend.app.services.trip_service import MomaTimeoutError, TripService


VALID_REQUEST = {
    "destination": "杭州",
    "start_date": "2026-10-01",
    "end_date": "2026-10-03",
}
VALID_ITINERARY = {
    **VALID_REQUEST,
    "summary": "三日行程",
    "days": [
        {"date": "2026-10-01", "title": "西湖", "activities": []},
        {"date": "2026-10-02", "title": "文化", "activities": []},
        {"date": "2026-10-03", "title": "美食", "activities": []},
    ],
    "total_estimated_cost": 0,
}


class StubService:
    def __init__(self, result: Itinerary | Exception):
        self.result = result

    def generate(self, request):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_generate_trip_returns_itinerary_and_request_id():
    app.dependency_overrides[get_trip_service] = lambda: StubService(Itinerary.model_validate(VALID_ITINERARY))
    try:
        response = TestClient(app).post("/api/trip/generate", json=VALID_REQUEST, headers={"X-Request-ID": "req_test"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == VALID_ITINERARY
    assert response.headers["x-request-id"] == "req_test"


def test_generate_trip_maps_request_validation_error():
    app.dependency_overrides[get_trip_service] = lambda: StubService(Itinerary.model_validate(VALID_ITINERARY))
    try:
        response = TestClient(app).post("/api/trip/generate", json={"destination": ""})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_TRIP_REQUEST"
    assert response.json()["request_id"].startswith("req_")


def test_generate_trip_maps_moma_timeout_without_leaking_details():
    app.dependency_overrides[get_trip_service] = lambda: StubService(MomaTimeoutError())
    try:
        response = TestClient(app).post("/api/trip/generate", json=VALID_REQUEST)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 504
    assert response.json()["code"] == "MOMA_TIMEOUT"
    assert "traceback" not in response.text.lower()
