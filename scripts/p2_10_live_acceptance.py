"""Run one real-provider P2-10 sample without touching the application database."""

from __future__ import annotations

import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.app.main import get_trip_edit_service, get_trip_orchestrator, get_trip_service
from backend.app.models.schemas import TripEditRequest, TripRequest
from backend.app.services.trip_export import render_markdown, render_pdf
from backend.app.storage import SQLiteTripRepository


def main() -> None:
    tomorrow = datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)
    request = TripRequest(
        destination="杭州",
        start_date=tomorrow,
        end_date=tomorrow + timedelta(days=2),
        travelers=1,
        budget=8000,
        preferences=["历史文化", "自然风光"],
        pace="relaxed",
    )
    result: dict[str, object] = {
        "started_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "destination": request.destination,
        "days_requested": 3,
    }
    stage = "generation"
    started = time.perf_counter()
    try:
        service = get_trip_service()
        orchestrator = get_trip_orchestrator(service)
        generated = orchestrator.run(request)
        result["generation_seconds"] = round(time.perf_counter() - started, 2)
        result["generation_usage"] = dict(service.generator.last_usage)
        result["generation_steps"] = [
            {
                "name": step.name,
                "status": step.status.value,
                "duration_ms": round(step.duration_ms, 2),
                "failure_category": step.failure_category,
            }
            for step in generated.trace
        ]
        metrics = service.map_enricher.last_metrics
        result["quality"] = {
            "days": len(generated.itinerary.days),
            "activities": sum(len(day.activities) for day in generated.itinerary.days),
            "poi_verified": metrics.poi_verified,
            "poi_total": metrics.poi_total,
            "poi_verified_rate": round(metrics.poi_verified_rate, 3),
            "route_verified": metrics.route_verified,
            "route_eligible": metrics.route_eligible,
            "route_verified_rate": round(metrics.route_verified_rate, 3),
            "weather_available_days": sum(
                day.weather is not None and day.weather.status == "available"
                for day in generated.itinerary.days
            ),
            "spot_images": sum(
                activity.poi_category == "spot" and bool(activity.image_url)
                for day in generated.itinerary.days
                for activity in day.activities
            ),
        }

        stage = "edit"
        with tempfile.TemporaryDirectory(prefix="p2-10-live-") as directory:
            repository = SQLiteTripRepository(Path(directory) / "trips.sqlite3")
            saved = repository.create(generated.itinerary)
            editor = get_trip_edit_service(repository)
            client = editor.editor.client
            original_chat = client.chat
            edit_usage: dict[str, object] = {}

            def measured_chat(*args, **kwargs):
                response = original_chat(*args, **kwargs)
                edit_usage.update(dict(response.usage))
                return response

            client.chat = measured_chat
            edit_started = time.perf_counter()
            edited = editor.edit(
                saved.trip_id,
                TripEditRequest(
                    expected_version=1,
                    date=tomorrow + timedelta(days=1),
                    instruction="保留原有地点和 POI ID，让当天节奏更轻松，适当调整活动时间。",
                ),
            )
            result["edit_seconds"] = round(time.perf_counter() - edit_started, 2)
            result["edit_usage"] = edit_usage
            result["edit_version"] = edited.version
            result["other_days_unchanged"] = (
                edited.itinerary.days[0] == saved.days[0]
                and edited.itinerary.days[2] == saved.days[2]
            )
            result["edited_day_images"] = sum(
                activity.poi_category == "spot" and bool(activity.image_url)
                for activity in edited.itinerary.days[1].activities
            )
            result["historical_version_unchanged"] = (
                repository.get_version(saved.trip_id, 1) == saved
            )
            stage = "export"
            result["markdown_bytes"] = len(render_markdown(edited.itinerary).encode("utf-8"))
            result["pdf_bytes"] = len(render_pdf(edited.itinerary))
            result["status"] = "passed"
    except Exception as exc:  # noqa: BLE001 - report provider failures without exposing payloads
        result["status"] = "failed"
        result["failed_stage"] = stage
        result["failure_type"] = type(exc).__name__
        result["elapsed_seconds"] = round(time.perf_counter() - started, 2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
