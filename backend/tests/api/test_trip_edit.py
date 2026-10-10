"""Offline regression tests for constrained single-day editing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app, get_trip_edit_service, get_trip_repository
from backend.app.models.schemas import Itinerary, TripEditRequest
from backend.app.services.trip_edit import (
    MomaDayEditor,
    TripEditError,
    TripEditService,
    TripEditTimeoutError,
)
from backend.app.storage import SQLiteTripRepository, TripVersionConflictError


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


def valid_draft() -> dict[str, Any]:
    return {
        "date": "2026-10-02",
        "title": "轻松看日落",
        "activities": [
            {
                "time": "17:00",
                "name": "活动 2",
                "description": "减少活动，傍晚看日落",
                "estimated_cost": 5.0,
            }
        ],
    }


class StubEditor:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = 0

    def edit(self, *args: object, **kwargs: object) -> Any:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class StubMomaClient:
    def __init__(self, result: object) -> None:
        self.result = result
        self.messages: list[dict[str, str]] = []

    def chat(self, messages: list[dict[str, str]]) -> object:
        self.messages = messages
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class CountingRepository(SQLiteTripRepository):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.save_calls = 0

    def save_version(self, itinerary: Itinerary, *, expected_version: int) -> Itinerary:
        self.save_calls += 1
        return super().save_version(itinerary, expected_version=expected_version)


def request(*, version: int = 1, day: str = "2026-10-02") -> TripEditRequest:
    return TripEditRequest(
        expected_version=version, date=day, instruction="减少活动并安排日落"
    )


def test_success_only_replaces_target_day_and_creates_version(tmp_path: Path) -> None:
    repository = CountingRepository(tmp_path / "trips.sqlite3")
    original = repository.create(itinerary())
    response = TripEditService(repository, StubEditor(valid_draft())).edit(
        original.trip_id, request()  # type: ignore[arg-type]
    )

    assert response.version == 2
    assert response.itinerary.days[0] == original.days[0]
    assert response.itinerary.days[2] == original.days[2]
    assert response.itinerary.days[1].title == "轻松看日落"
    assert response.itinerary.total_estimated_cost == 25
    assert response.change_summary
    assert repository.save_calls == 1
    assert repository.get_version(original.trip_id, 1) == original  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "draft",
    [
        "not json",
        {**valid_draft(), "destination": "苏州"},
        {**valid_draft(), "date": "2026-10-03"},
        {
            **valid_draft(),
            "activities": [{**valid_draft()["activities"][0], "estimated_cost": -1}],
        },
        {
            **valid_draft(),
            "activities": [{**valid_draft()["activities"][0], "estimated_cost": "5"}],
        },
        {
            **valid_draft(),
            "activities": [{**valid_draft()["activities"][0], "poi_id": "fake"}],
        },
        {
            **valid_draft(),
            "activities": [
                {**valid_draft()["activities"][0], "route_status": "verified"}
            ],
        },
    ],
)
def test_invalid_draft_never_writes(tmp_path: Path, draft: object) -> None:
    repository = CountingRepository(tmp_path / "trips.sqlite3")
    original = repository.create(itinerary())

    with pytest.raises(TripEditError):
        TripEditService(repository, StubEditor(draft)).edit(
            original.trip_id, request()  # type: ignore[arg-type]
        )

    assert repository.save_calls == 0
    assert repository.get_current(original.trip_id) == original  # type: ignore[arg-type]


def test_invalid_date_does_not_call_editor_or_save(tmp_path: Path) -> None:
    repository = CountingRepository(tmp_path / "trips.sqlite3")
    original = repository.create(itinerary())
    editor = StubEditor(valid_draft())

    with pytest.raises(TripEditError) as error:
        TripEditService(repository, editor).edit(
            original.trip_id, request(day="2026-10-04")  # type: ignore[arg-type]
        )

    assert error.value.code == "INVALID_TRIP_REQUEST"
    assert editor.calls == repository.save_calls == 0


def test_stale_version_fails_before_model_call(tmp_path: Path) -> None:
    repository = CountingRepository(tmp_path / "trips.sqlite3")
    original = repository.create(itinerary())
    editor = StubEditor(valid_draft())

    with pytest.raises(TripVersionConflictError):
        TripEditService(repository, editor).edit(
            original.trip_id, request(version=2)  # type: ignore[arg-type]
        )

    assert editor.calls == repository.save_calls == 0


def test_editor_timeout_never_writes(tmp_path: Path) -> None:
    repository = CountingRepository(tmp_path / "trips.sqlite3")
    original = repository.create(itinerary())

    with pytest.raises(TripEditTimeoutError):
        TripEditService(repository, StubEditor(TripEditTimeoutError())).edit(
            original.trip_id, request()  # type: ignore[arg-type]
        )
    assert repository.save_calls == 0


def test_moma_editor_builds_target_only_prompt_and_maps_timeout() -> None:
    current = itinerary()
    client = StubMomaClient(json.dumps(valid_draft()))
    result = MomaDayEditor(client).edit(
        current, current.days[1], "减少活动", candidates=()
    )
    prompt = client.messages[1]["content"]
    assert result == json.dumps(valid_draft())
    assert '"target_day"' in prompt
    assert '"instruction":"减少活动"' in prompt

    with pytest.raises(TripEditTimeoutError):
        MomaDayEditor(StubMomaClient(TimeoutError("secret timeout"))).edit(
            current, current.days[1], "减少活动"
        )


def test_edit_http_contract_and_error_mapping(tmp_path: Path) -> None:
    repository = SQLiteTripRepository(tmp_path / "trips.sqlite3")
    original = repository.create(itinerary())
    service = TripEditService(repository, StubEditor(json.dumps(valid_draft())))
    app.dependency_overrides[get_trip_repository] = lambda: repository
    app.dependency_overrides[get_trip_edit_service] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)
    try:
        response = client.post(
            f"/api/trip/{original.trip_id}/edit",
            json={
                "expected_version": 1,
                "date": "2026-10-02",
                "instruction": "减少活动并安排日落",
            },
        )
        assert response.status_code == 200
        assert response.json()["version"] == 2
        assert response.json()["change_summary"]

        stale = client.post(
            f"/api/trip/{original.trip_id}/edit",
            json={
                "expected_version": 1,
                "date": "2026-10-02",
                "instruction": "再次修改",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "TRIP_VERSION_CONFLICT"

        missing = client.post(
            "/api/trip/trip_missing/edit",
            json={
                "expected_version": 1,
                "date": "2026-10-02",
                "instruction": "修改",
            },
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "TRIP_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()
