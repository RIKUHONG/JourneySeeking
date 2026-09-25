"""Offline checks for the public trip API schemas."""

from datetime import date

import pytest
from pydantic import ValidationError

from backend.app.models.schemas import Activity, DayPlan, ErrorResponse, Itinerary, TripRequest


def request_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "destination": "杭州",
        "start_date": "2026-10-01",
        "end_date": "2026-10-03",
    }
    payload.update(changes)
    return payload


def activity_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "time": "09:00",
        "name": "西湖游览",
        "description": "环湖散步",
        "estimated_cost": 0,
    }
    payload.update(changes)
    return payload


def itinerary_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "destination": "杭州",
        "start_date": "2026-10-01",
        "end_date": "2026-10-03",
        "summary": "西湖三日游",
        "days": [
            {
                "date": "2026-10-01",
                "title": "西湖",
                "activities": [activity_payload()],
            }
        ],
        "total_estimated_cost": 0,
    }
    payload.update(changes)
    return payload


@pytest.mark.parametrize("end_date", ["2026-10-03", "2026-10-07"])
def test_trip_request_accepts_three_to_seven_days_and_defaults(end_date: str) -> None:
    request = TripRequest.model_validate(request_payload(end_date=end_date))
    assert request.travelers == 1
    assert request.budget is None
    assert request.preferences == []
    assert request.dietary_preferences == []
    assert request.end_date == date.fromisoformat(end_date)


def test_trip_request_trims_text_and_accepts_optional_fields() -> None:
    request = TripRequest.model_validate(
        request_payload(
            destination=" 杭州 ",
            travelers=2,
            budget=10000,
            preferences=[" 美食 "],
            pace="relaxed",
            dietary_preferences=[" 少辣 "],
            hotel_level="four_star",
            special_notes=" 不要早起 ",
        )
    )
    assert request.destination == "杭州"
    assert request.preferences == ["美食"]
    assert request.dietary_preferences == ["少辣"]
    assert request.special_notes == "不要早起"
    assert request.budget == 10000


@pytest.mark.parametrize(
    "changes",
    [
        {"destination": ""},
        {"destination": "   "},
        {"start_date": "not-a-date"},
        {"end_date": "2026-09-30"},
        {"end_date": "2026-10-02"},
        {"end_date": "2026-10-08"},
        {"travelers": 0},
        {"travelers": 1.5},
        {"budget": -1},
        {"budget": "medium"},
        {"budget": float("inf")},
        {"preferences": ["x"] * 11},
        {"preferences": ["  "]},
        {"dietary_preferences": ["x"] * 11},
        {"dietary_preferences": [""]},
        {"pace": "slow"},
        {"hotel_level": "luxury"},
        {"special_notes": "  "},
        {"special_notes": "x" * 2001},
    ],
)
def test_trip_request_rejects_invalid_fields(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TripRequest.model_validate(request_payload(**changes))


@pytest.mark.parametrize("missing", ["destination", "start_date", "end_date"])
def test_trip_request_requires_core_fields(missing: str) -> None:
    payload = request_payload()
    del payload[missing]
    with pytest.raises(ValidationError):
        TripRequest.model_validate(payload)


def test_optional_arrays_have_independent_defaults() -> None:
    first = TripRequest.model_validate(request_payload())
    second = TripRequest.model_validate(request_payload())
    first.preferences.append("美食")
    assert second.preferences == []


def test_itinerary_and_error_response_validate() -> None:
    itinerary = Itinerary.model_validate(itinerary_payload())
    error = ErrorResponse(code="INVALID_TRIP_REQUEST", message="日期错误", request_id="req_1")
    assert isinstance(itinerary.days[0], DayPlan)
    assert isinstance(itinerary.days[0].activities[0], Activity)
    assert itinerary.model_dump(mode="json")["start_date"] == "2026-10-01"
    assert error.model_dump() == {
        "code": "INVALID_TRIP_REQUEST",
        "message": "日期错误",
        "request_id": "req_1",
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"time": "24:00"},
        {"time": "9:00"},
        {"name": "  "},
        {"duration_minutes": 0},
        {"duration_minutes": -1},
        {"estimated_cost": -1},
        {"estimated_cost": float("nan")},
    ],
)
def test_activity_rejects_invalid_fields(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Activity.model_validate(activity_payload(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"summary": "  "},
        {"days": []},
        {"days": [{"date": "2026-10-01", "title": " ", "activities": []}]},
        {"days": [{"date": "2026-10-01", "title": "西湖"}]},
        {"total_estimated_cost": -1},
    ],
)
def test_itinerary_rejects_invalid_fields(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Itinerary.model_validate(itinerary_payload(**changes))
