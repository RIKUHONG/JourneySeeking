"""Contract tests for P2 identity, version and error semantics."""

from datetime import date

import pytest
from pydantic import ValidationError

from backend.app.models.schemas import (
    ErrorCode,
    ErrorResponse,
    Itinerary,
    TripEditRequest,
    TripEditResponse,
    TripExportFormat,
    TripExportQuery,
    TripListQuery,
    TripListResponse,
    TripSaveRequest,
    TripSummary,
    TripVersionsResponse,
    TripVersionSummary,
)


def itinerary_payload(**changes: object) -> dict[str, object]:
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
    return payload


def test_old_itinerary_shape_remains_valid_without_identity() -> None:
    itinerary = Itinerary.model_validate(itinerary_payload())
    assert itinerary.trip_id is None
    assert itinerary.version is None


def test_identity_fields_are_optional_only_as_a_pair() -> None:
    with pytest.raises(ValidationError):
        Itinerary.model_validate(itinerary_payload(trip_id="trip_1"))
    with pytest.raises(ValidationError):
        Itinerary.model_validate(itinerary_payload(version=1))


def test_saved_itinerary_requires_positive_identity_and_version() -> None:
    new_trip = TripSaveRequest(itinerary=Itinerary.model_validate(itinerary_payload()))
    assert new_trip.expected_version is None

    existing = Itinerary.model_validate(itinerary_payload(trip_id="trip_1", version=1))
    saved = TripSaveRequest(itinerary=existing, expected_version=1)
    assert saved.itinerary.trip_id == "trip_1"

    with pytest.raises(ValidationError):
        TripSaveRequest(itinerary=existing)
    with pytest.raises(ValidationError):
        TripSaveRequest(itinerary=existing, expected_version=2)
    with pytest.raises(ValidationError):
        TripSaveRequest(itinerary=Itinerary.model_validate(itinerary_payload()), expected_version=1)


def test_versioned_operation_models_are_serializable() -> None:
    summary = TripSummary(
        trip_id="trip_1",
        version=2,
        destination="杭州",
        summary="杭州三日游",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 3),
    )
    listing = TripListResponse(items=[summary])
    versions = TripVersionsResponse(
        trip_id="trip_1",
        current_version=2,
        items=[
            TripVersionSummary(
                trip_id="trip_1",
                version=2,
                created_at="2026-09-29T10:00:00Z",
                summary="杭州三日游",
            )
        ],
    )
    edit = TripEditRequest(
        expected_version=2,
        date="2026-10-02",
        instruction="减少当天活动",
    )
    response = TripEditResponse(
        trip_id="trip_1",
        version=3,
        itinerary=Itinerary.model_validate(itinerary_payload(trip_id="trip_1", version=3)),
        change_summary=["减少当天活动"],
    )
    assert listing.items[0].version == 2
    assert versions.current_version == 2
    assert edit.date == date(2026, 10, 2)
    assert response.version == response.itinerary.version == 3
    assert TripExportFormat.MARKDOWN.value == "markdown"
    assert TripListQuery(limit=25).limit == 25
    assert TripExportQuery(version=2, format="pdf").format is TripExportFormat.PDF

    with pytest.raises(ValidationError):
        TripEditResponse(
            trip_id="trip_1",
            version=4,
            itinerary=Itinerary.model_validate(itinerary_payload(trip_id="trip_1", version=3)),
        )


def test_error_codes_have_stable_wire_values() -> None:
    error = ErrorResponse(
        code=ErrorCode.TRIP_VERSION_CONFLICT,
        message="版本冲突",
        request_id="req_test",
    )
    assert error.model_dump(mode="json") == {
        "code": "TRIP_VERSION_CONFLICT",
        "message": "版本冲突",
        "request_id": "req_test",
    }
