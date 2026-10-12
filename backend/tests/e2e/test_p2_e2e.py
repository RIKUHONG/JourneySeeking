"""P2-10 offline HTTP acceptance flow with provider failure injection."""

import json
import logging
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app, get_trip_edit_service, get_trip_orchestrator, get_trip_repository
from backend.app.services.orchestration import TripOrchestrator
from backend.app.services.trip_edit import TripEditService
from backend.app.services.trip_service import TripService
from backend.app.storage import SQLiteTripRepository

REQUEST = {
    "destination": "杭州",
    "start_date": "2026-10-01",
    "end_date": "2026-10-03",
    "preferences": ["文化"],
}


def itinerary_payload() -> dict[str, object]:
    return {
        **REQUEST,
        "summary": "杭州三日游",
        "days": [
            {
                "date": f"2026-10-0{day}",
                "title": f"第{day}天",
                "activities": [
                    {
                        "time": "09:00",
                        "name": "原活动",
                        "description": "初始活动",
                        "estimated_cost": 0,
                    }
                ],
            }
            for day in range(1, 4)
        ],
        "total_estimated_cost": 0,
    }


class StubGenerator:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.last_candidate_pool = None
        self.last_candidate_diagnostics = None

    def generate(self, request, *, knowledge_chunks=()):
        if self.failure:
            raise self.failure
        return json.dumps(itinerary_payload(), ensure_ascii=False)


class StubDayEditor:
    def edit(self, itinerary, day, instruction, **kwargs):
        return {
            "date": day.date.isoformat(),
            "title": f"{day.title}（已调整）",
            "activities": [
                {
                    "time": "10:00",
                    "name": "原活动",
                    "description": "离线验收编辑结果",
                    "estimated_cost": 10,
                }
            ],
        }


def configure(tmp_path: Path, *, failure: Exception | None = None) -> TestClient:
    repository = SQLiteTripRepository(tmp_path / "trips.sqlite3")
    service = TripService(StubGenerator(failure=failure))
    app.dependency_overrides[get_trip_repository] = lambda: repository
    app.dependency_overrides[get_trip_orchestrator] = lambda: TripOrchestrator(
        service, knowledge=None
    )
    app.dependency_overrides[get_trip_edit_service] = lambda: TripEditService(
        repository, StubDayEditor()
    )
    return TestClient(app, raise_server_exceptions=False)


def reset() -> None:
    app.dependency_overrides.clear()


def test_generate_save_two_edits_history_and_exports(tmp_path: Path, caplog) -> None:
    client = configure(tmp_path)
    caplog.set_level(logging.INFO)
    try:
        generated = client.post(
            "/api/trip/generate", json=REQUEST, headers={"X-Request-ID": "req_e2e"}
        )
        assert generated.status_code == 200
        assert generated.headers["x-request-id"] == "req_e2e"

        saved = client.post(
            "/api/trip/save",
            json={"itinerary": generated.json(), "expected_version": None},
        )
        assert saved.status_code == 200
        trip_id = saved.json()["trip_id"]
        assert saved.json()["version"] == 1

        session = client.post(
            f"/api/trip/{trip_id}/sessions",
            json={"version": 1, "constraints": {"budget": 500}},
        )
        assert session.status_code == 200
        session_id = session.json()["session_id"]

        first = client.post(
            f"/api/trip/{trip_id}/sessions/{session_id}/edit",
            json={"date": "2026-10-01", "instruction": "安排文化活动"},
        )
        assert first.status_code == 200, first.text
        assert first.json()["version"] == 2

        second = client.post(
            f"/api/trip/{trip_id}/sessions/{session_id}/edit",
            json={"date": "2026-10-02", "instruction": "安排轻松活动"},
        )
        assert second.status_code == 200
        assert second.json()["version"] == 3

        current = client.get(f"/api/trip/{trip_id}")
        old = client.get(f"/api/trip/{trip_id}/versions/1")
        assert current.status_code == old.status_code == 200
        assert current.json()["version"] == 3
        assert old.json()["version"] == 1
        assert old.json()["days"] != current.json()["days"]

        markdown = client.get(
            f"/api/trip/{trip_id}/export", params={"version": 3, "format": "markdown"}
        )
        pdf = client.get(f"/api/trip/{trip_id}/export", params={"format": "pdf"})
        assert markdown.status_code == pdf.status_code == 200
        assert "已调整" in markdown.text
        assert pdf.content.startswith(b"%PDF")

        assert any("orchestration_completed" in record.message for record in caplog.records)
        assert any("request_completed" in record.message for record in caplog.records)
        assert any("req_e2e" in record.message for record in caplog.records)

        assert client.delete(f"/api/trip/{trip_id}/sessions/{session_id}").status_code == 204
        assert client.delete(f"/api/trip/{trip_id}").status_code == 204
        assert client.get(f"/api/trip/{trip_id}").status_code == 404
        assert client.get(f"/api/trip/{trip_id}/versions/1").status_code == 404
    finally:
        reset()


def test_generation_failure_does_not_create_trip(tmp_path: Path) -> None:
    client = configure(tmp_path, failure=TimeoutError("provider timeout"))
    try:
        response = client.post("/api/trip/generate", json=REQUEST)
        assert response.status_code == 504
        assert response.json()["code"] == "MOMA_TIMEOUT"
        assert client.get("/api/trip").json()["items"] == []
    finally:
        reset()


def test_orchestration_failure_has_public_error_and_request_id(tmp_path: Path) -> None:
    repository = SQLiteTripRepository(tmp_path / "trips.sqlite3")
    service = TripService(StubGenerator())
    app.dependency_overrides[get_trip_repository] = lambda: repository
    app.dependency_overrides[get_trip_orchestrator] = lambda: TripOrchestrator(
        service, knowledge=None, max_steps=1
    )
    client = TestClient(app, raise_server_exceptions=False)
    try:
        response = client.post(
            "/api/trip/generate", json=REQUEST, headers={"X-Request-ID": "req_limit"}
        )
        assert response.status_code == 502
        assert response.headers["x-request-id"] == "req_limit"
        assert response.json()["code"] == "INTERNAL_SERVER_ERROR"
    finally:
        reset()
