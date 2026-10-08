"""HTTP tests for save, history, version and delete endpoints."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app, get_trip_repository
from backend.app.storage import SQLiteTripRepository


def payload(summary: str = "杭州三日游") -> dict[str, object]:
    return {
        "itinerary": {
            "destination": "杭州",
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            "summary": summary,
            "days": [
                {"date": "2026-10-01", "title": "西湖", "activities": []},
            ],
            "total_estimated_cost": 0,
        },
        "expected_version": None,
    }


def client_for(tmp_path: Path) -> TestClient:
    app.dependency_overrides[get_trip_repository] = lambda: SQLiteTripRepository(
        tmp_path / "trips.sqlite3"
    )
    return TestClient(app)


def test_save_list_get_versions_update_and_delete(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    try:
        created = client.post("/api/trip/save", json=payload())
        assert created.status_code == 200
        saved = created.json()
        trip_id = saved["trip_id"]
        assert saved["version"] == 1

        listing = client.get("/api/trip")
        assert listing.status_code == 200
        assert listing.json()["items"][0]["trip_id"] == trip_id

        current = client.get(f"/api/trip/{trip_id}")
        assert current.status_code == 200
        assert current.json()["version"] == 1

        versions = client.get(f"/api/trip/{trip_id}/versions")
        assert versions.status_code == 200
        assert versions.json()["current_version"] == 1

        updated_payload = {
            "itinerary": {**saved, "summary": "更新后的行程"},
            "expected_version": 1,
        }
        updated = client.post("/api/trip/save", json=updated_payload)
        assert updated.status_code == 200
        assert updated.json()["version"] == 2

        conflict = client.post("/api/trip/save", json=updated_payload)
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "TRIP_VERSION_CONFLICT"

        deleted = client.delete(f"/api/trip/{trip_id}")
        assert deleted.status_code == 204
        missing = client.get(f"/api/trip/{trip_id}")
        assert missing.status_code == 404
        assert missing.json()["code"] == "TRIP_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()


def test_invalid_version_and_missing_trip_use_contract_errors(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    try:
        invalid = client.post("/api/trip/save", json={**payload(), "expected_version": 0})
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "INVALID_TRIP_VERSION"

        missing = client.get("/api/trip/trip_missing/versions")
        assert missing.status_code == 404
        assert missing.json()["code"] == "TRIP_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()
