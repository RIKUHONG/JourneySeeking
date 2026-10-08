"""SQLite repository tests without external services."""

from pathlib import Path

import pytest

from backend.app.models.schemas import Itinerary
from backend.app.storage import SQLiteTripRepository, TripNotFoundError, TripVersionConflictError


def itinerary(**changes: object) -> Itinerary:
    payload: dict[str, object] = {
        "destination": "杭州",
        "start_date": "2026-10-01",
        "end_date": "2026-10-03",
        "summary": "杭州三日游",
        "days": [
            {"date": "2026-10-01", "title": "西湖", "activities": []},
        ],
        "total_estimated_cost": 0,
    }
    payload.update(changes)
    return Itinerary.model_validate(payload)


def test_create_read_versions_and_survive_new_repository(tmp_path: Path) -> None:
    database = tmp_path / "trips.sqlite3"
    repository = SQLiteTripRepository(database)
    first = repository.create(itinerary())

    assert first.trip_id is not None
    assert first.version == 1
    assert repository.get_current(first.trip_id) == first
    assert repository.get_version(first.trip_id, 1) == first

    reopened = SQLiteTripRepository(database)
    assert reopened.get_current(first.trip_id) == first
    versions = reopened.list_versions(first.trip_id)
    assert versions.current_version == 1
    assert [item.version for item in versions.items] == [1]


def test_save_version_is_atomic_and_rejects_stale_version(tmp_path: Path) -> None:
    repository = SQLiteTripRepository(tmp_path / "trips.sqlite3")
    first = repository.create(itinerary())
    updated = repository.save_version(
        itinerary(trip_id=first.trip_id, version=1, summary="更新后的行程"), expected_version=1
    )

    assert updated.version == 2
    assert repository.get_current(first.trip_id).summary == "更新后的行程"
    assert repository.get_version(first.trip_id, 1).summary == "杭州三日游"

    with pytest.raises(TripVersionConflictError):
        repository.save_version(
            itinerary(trip_id=first.trip_id, version=1, summary="过期写入"), expected_version=1
        )
    assert repository.get_current(first.trip_id).summary == "更新后的行程"


def test_missing_trip_and_version_are_not_found(tmp_path: Path) -> None:
    repository = SQLiteTripRepository(tmp_path / "trips.sqlite3")
    with pytest.raises(TripNotFoundError):
        repository.get_current("trip_missing")
    with pytest.raises(TripNotFoundError):
        repository.get_version("trip_missing", 1)
    with pytest.raises(TripNotFoundError):
        repository.list_versions("trip_missing")
    with pytest.raises(TripNotFoundError):
        repository.delete("trip_missing")


def test_list_is_bounded_and_cursor_paginates(tmp_path: Path) -> None:
    repository = SQLiteTripRepository(tmp_path / "trips.sqlite3")
    first = repository.create(itinerary(summary="第一条"))
    second = repository.create(itinerary(summary="第二条"))
    listing = repository.list(limit=1)

    assert len(listing.items) == 1
    assert listing.next_cursor == "1"
    next_page = repository.list(limit=1, cursor=listing.next_cursor)
    assert len(next_page.items) == 1
    assert {next_page.items[0].trip_id, listing.items[0].trip_id} == {
        first.trip_id,
        second.trip_id,
    }


def test_delete_removes_current_and_all_versions(tmp_path: Path) -> None:
    repository = SQLiteTripRepository(tmp_path / "trips.sqlite3")
    first = repository.create(itinerary())
    repository.save_version(itinerary(trip_id=first.trip_id, version=1), expected_version=1)
    repository.delete(first.trip_id)

    with pytest.raises(TripNotFoundError):
        repository.get_current(first.trip_id)
    with pytest.raises(TripNotFoundError):
        repository.get_version(first.trip_id, 1)
    with pytest.raises(TripNotFoundError):
        repository.get_version(first.trip_id, 2)
