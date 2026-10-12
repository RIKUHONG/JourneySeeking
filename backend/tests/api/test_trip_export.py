from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app, get_trip_repository
from backend.app.storage import SQLiteTripRepository


def payload() -> dict[str, object]:
    return {
        "itinerary": {
            "destination": "杭州/西湖",
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            "summary": "中文长描述：适合慢节奏旅行。",
            "days": [
                {
                    "date": "2026-10-01",
                    "title": "西湖漫步",
                    "activities": [
                        {
                            "time": "09:00",
                            "name": "西湖",
                            "description": "环湖游览",
                            "location": "西湖",
                            "estimated_cost": 10,
                        }
                    ],
                    "weather": {"status": "unknown"},
                },
                {"date": "2026-10-02", "title": "空日程", "activities": []},
                {"date": "2026-10-03", "title": "返程", "activities": []},
            ],
            "total_estimated_cost": 10,
        },
        "expected_version": None,
    }


def test_markdown_and_pdf_export_use_requested_version(tmp_path: Path) -> None:
    app.dependency_overrides[get_trip_repository] = lambda: SQLiteTripRepository(
        tmp_path / "trips.sqlite3"
    )
    client = TestClient(app)
    try:
        created = client.post("/api/trip/save", json=payload())
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]

        markdown = client.get(f"/api/trip/{trip_id}/export", params={"format": "markdown"})
        assert markdown.status_code == 200
        assert markdown.headers["content-type"].startswith("text/markdown")
        assert "西湖漫步" in markdown.text
        assert "暂无安排。" in markdown.text
        assert "暂无来源" in markdown.text
        assert "attachment" in markdown.headers["content-disposition"]

        pdf = client.get(f"/api/trip/{trip_id}/export", params={"version": 1, "format": "pdf"})
        assert pdf.status_code == 200
        assert pdf.headers["content-type"].startswith("application/pdf")
        assert pdf.content.startswith(b"%PDF")
        assert len(pdf.content) > 1000
    finally:
        app.dependency_overrides.clear()


def test_pdf_export_escapes_markup_and_handles_long_text(tmp_path: Path) -> None:
    data = payload()
    itinerary = data["itinerary"]
    assert isinstance(itinerary, dict)
    itinerary["destination"] = "<notclosed & destination>"
    itinerary["summary"] = "<notclosed & summary> " * 300
    itinerary["days"][0]["title"] = "<day & title>"
    activity = itinerary["days"][0]["activities"][0]
    activity["name"] = "<activity & name>"
    activity["description"] = ">" * 2000 + " & <"
    activity["location"] = "<location>"
    app.dependency_overrides[get_trip_repository] = lambda: SQLiteTripRepository(
        tmp_path / "trips.sqlite3"
    )
    client = TestClient(app)
    try:
        created = client.post("/api/trip/save", json=data)
        assert created.status_code == 200
        trip_id = created.json()["trip_id"]
        response = client.get(f"/api/trip/{trip_id}/export", params={"format": "pdf"})
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF")
    finally:
        app.dependency_overrides.clear()


def test_export_missing_version_and_invalid_format_follow_contract(tmp_path: Path) -> None:
    app.dependency_overrides[get_trip_repository] = lambda: SQLiteTripRepository(
        tmp_path / "trips.sqlite3"
    )
    client = TestClient(app)
    try:
        missing = client.get("/api/trip/not-found/export", params={"format": "markdown"})
        assert missing.status_code == 404
        assert missing.json()["code"] == "TRIP_NOT_FOUND"

        invalid = client.get("/api/trip/any/export", params={"format": "docx"})
        assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_export_rejects_non_integer_version(tmp_path: Path) -> None:
    app.dependency_overrides[get_trip_repository] = lambda: SQLiteTripRepository(
        tmp_path / "trips.sqlite3"
    )
    client = TestClient(app)
    try:
        response = client.get(
            "/api/trip/not-found/export", params={"version": "1.0", "format": "pdf"}
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
