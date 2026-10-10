"""Offline tests for P2-06 bounded multi-turn trip sessions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.main import (
    app,
    get_session_repository,
    get_session_service,
    get_trip_edit_service,
    get_trip_repository,
)
from backend.app.models.schemas import (
    Itinerary,
    SessionConstraints,
    SessionCreateRequest,
    SessionEditRequest,
)
from backend.app.services.session_context import (
    SessionExpiredError,
    SessionService,
    SessionTripMismatchError,
    SessionVersionError,
)
from backend.app.services.trip_edit import TripEditService
from backend.app.storage import SQLiteSessionRepository, SQLiteTripRepository


def itinerary() -> Itinerary:
    return Itinerary.model_validate(
        {
            "destination": "杭州",
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            "summary": "杭州三日游",
            "days": [
                {
                    "date": f"2026-10-0{index}",
                    "title": f"第 {index} 天",
                    "activities": [
                        {
                            "time": "09:00",
                            "name": f"活动 {index}",
                            "description": "原安排",
                            "estimated_cost": 10.0,
                        }
                    ],
                }
                for index in range(1, 4)
            ],
            "total_estimated_cost": 30.0,
        }
    )


def draft(title: str) -> dict[str, Any]:
    return {
        "date": "2026-10-02",
        "title": title,
        "activities": [
            {
                "time": "17:00",
                "name": "活动 2",
                "description": "调整后的安排",
                "estimated_cost": 5.0,
            }
        ],
    }


class StubEditor:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def edit(self, *args: object, **kwargs: object) -> str:
        self.calls.append((args, kwargs))
        title = f"第 {len(self.calls) + 1} 轮调整"
        return json.dumps(draft(title), ensure_ascii=False)


def services(
    tmp_path: Path,
) -> tuple[SQLiteTripRepository, SQLiteSessionRepository, SessionService, StubEditor]:
    path = tmp_path / "trips.sqlite3"
    trips = SQLiteTripRepository(path)
    sessions = SQLiteSessionRepository(path, ttl_seconds=7 * 24 * 60 * 60)
    editor = StubEditor()
    service = SessionService(sessions, trips, TripEditService(trips, editor))
    return trips, sessions, service, editor


def test_two_edits_advance_session_and_bound_context(tmp_path: Path) -> None:
    trips, _, service, editor = services(tmp_path)
    saved = trips.create(itinerary())
    session = service.create(
        saved.trip_id,
        SessionCreateRequest(version=1, constraints=SessionConstraints(budget=3000, travelers=2)),
    )

    first = service.edit(
        saved.trip_id,
        session.session_id,
        SessionEditRequest(date="2026-10-02", instruction="第一轮调整"),
    )
    second = service.edit(
        saved.trip_id,
        session.session_id,
        SessionEditRequest(date="2026-10-02", instruction="第二轮调整"),
    )

    assert first.version == 2
    assert second.version == 3
    assert second.session.current_version == 3
    assert second.session.constraints.budget == 3000
    assert len(second.session.recent_turns) == 2
    assert editor.calls[1][1]["session_context"]


def test_cross_trip_and_expired_sessions_are_rejected(tmp_path: Path) -> None:
    trips, sessions, service, _ = services(tmp_path)
    first = trips.create(itinerary())
    second = trips.create(itinerary().model_copy(update={"summary": "另一行程"}))
    session = service.create(first.trip_id, SessionCreateRequest(version=1))

    with pytest.raises(SessionTripMismatchError):
        service.get(second.trip_id, session.session_id)

    with sqlite3.connect(sessions.database_path) as connection:
        connection.execute(
            "UPDATE trip_sessions SET expires_at = ? WHERE session_id = ?",
            ("2000-01-01T00:00:00+00:00", session.session_id),
        )
    with pytest.raises(SessionExpiredError):
        service.get(first.trip_id, session.session_id)


def test_external_trip_update_causes_session_version_conflict(tmp_path: Path) -> None:
    trips, _, service, _ = services(tmp_path)
    saved = trips.create(itinerary())
    session = service.create(saved.trip_id, SessionCreateRequest(version=1))
    trips.save_version(saved, expected_version=1)

    with pytest.raises(SessionVersionError):
        service.edit(
            saved.trip_id,
            session.session_id,
            SessionEditRequest(date="2026-10-02", instruction="使用旧会话"),
        )


def test_delete_session_does_not_delete_trip(tmp_path: Path) -> None:
    trips, _, service, _ = services(tmp_path)
    saved = trips.create(itinerary())
    session = service.create(saved.trip_id, SessionCreateRequest(version=1))
    service.delete(saved.trip_id, session.session_id)

    assert trips.get_current(saved.trip_id) == saved
    response = TestClient(app, raise_server_exceptions=False).get("/health")
    assert response.status_code == 200


def test_session_http_contract(tmp_path: Path) -> None:
    path = tmp_path / "trips.sqlite3"
    trips = SQLiteTripRepository(path)
    sessions = SQLiteSessionRepository(path)
    saved = trips.create(itinerary())
    editor = StubEditor()
    service = SessionService(sessions, trips, TripEditService(trips, editor))
    app.dependency_overrides[get_trip_repository] = lambda: trips
    app.dependency_overrides[get_session_repository] = lambda: sessions
    app.dependency_overrides[get_trip_edit_service] = lambda: TripEditService(trips, editor)
    app.dependency_overrides[get_session_service] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)
    try:
        created = client.post(f"/api/trip/{saved.trip_id}/sessions", json={"version": 1})
        assert created.status_code == 200
        session_id = created.json()["session_id"]
        edited = client.post(
            f"/api/trip/{saved.trip_id}/sessions/{session_id}/edit",
            json={"date": "2026-10-02", "instruction": "调整当天安排"},
        )
        assert edited.status_code == 200
        assert edited.json()["version"] == 2
        deleted = client.delete(f"/api/trip/{saved.trip_id}/sessions/{session_id}")
        assert deleted.status_code == 204
        missing = client.get(f"/api/trip/{saved.trip_id}/sessions/{session_id}")
        assert missing.status_code == 404
        assert missing.json()["code"] == "SESSION_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()
