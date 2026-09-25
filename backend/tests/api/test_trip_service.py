"""Trip service tests use a deterministic generator and no API keys."""

import json
from datetime import date, timedelta

import pytest

from backend.app.models.schemas import Itinerary, TripRequest
from backend.app.services.trip_service import (
    ItineraryValidationError,
    MomaInvalidResponseError,
    MomaTimeoutError,
    TripService,
)


class StubGenerator:
    def __init__(self, result: str | Exception) -> None:
        self.result = result
        self.request: TripRequest | None = None

    def generate(self, request: TripRequest) -> str:
        self.request = request
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def trip_request() -> TripRequest:
    return TripRequest.model_validate(
        {
            "destination": "杭州",
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            "travelers": 2,
        }
    )


def itinerary_payload(request: TripRequest) -> dict[str, object]:
    days = [
        {
            "date": (request.start_date + timedelta(days=offset)).isoformat(),
            "title": f"第 {offset + 1} 天",
            "activities": [
                {
                    "time": "09:00",
                    "name": "景点游览",
                    "description": "步行参观",
                    "estimated_cost": 10,
                }
            ],
        }
        for offset in range(3)
    ]
    return {
        "destination": request.destination,
        "start_date": request.start_date.isoformat(),
        "end_date": request.end_date.isoformat(),
        "summary": "杭州三日游",
        "days": days,
        "total_estimated_cost": 100,
    }


def generate_payload(request: TripRequest, payload: object) -> Itinerary:
    return TripService(StubGenerator(json.dumps(payload))).generate(request)


def test_generates_valid_itinerary(trip_request: TripRequest) -> None:
    generator = StubGenerator(json.dumps(itinerary_payload(trip_request)))
    itinerary = TripService(generator).generate(trip_request)
    assert isinstance(itinerary, Itinerary)
    assert generator.request is trip_request
    assert [day.date for day in itinerary.days] == [
        date(2026, 10, 1),
        date(2026, 10, 2),
        date(2026, 10, 3),
    ]
    assert itinerary.total_estimated_cost == 100


@pytest.mark.parametrize("result", ["", "not json", "```json\n{}\n```", "[]", "null"])
def test_rejects_non_json_or_non_object(trip_request: TripRequest, result: str) -> None:
    with pytest.raises(MomaInvalidResponseError) as error:
        TripService(StubGenerator(result)).generate(trip_request)
    assert error.value.code == "MOMA_INVALID_RESPONSE"
    assert "not json" not in str(error.value)


def test_rejects_missing_top_level_field(trip_request: TripRequest) -> None:
    payload = itinerary_payload(trip_request)
    del payload["days"]
    with pytest.raises(MomaInvalidResponseError):
        generate_payload(trip_request, payload)


@pytest.mark.parametrize(
    "change",
    [
        {"days": "三天行程"},
        {"total_estimated_cost": "很多钱"},
        {"total_estimated_cost": -1},
    ],
)
def test_rejects_wrong_field_types_or_costs(
    trip_request: TripRequest, change: dict[str, object]
) -> None:
    payload = itinerary_payload(trip_request)
    payload.update(change)
    with pytest.raises(ItineraryValidationError) as error:
        generate_payload(trip_request, payload)
    assert error.value.code == "ITINERARY_VALIDATION_ERROR"


@pytest.mark.parametrize("dates", [["2026-10-01", "2026-10-03"], ["2026-10-02"]])
def test_rejects_missing_or_skipped_days(trip_request: TripRequest, dates: list[str]) -> None:
    payload = itinerary_payload(trip_request)
    payload["days"] = [{"date": day, "title": "行程", "activities": []} for day in dates]
    with pytest.raises(ItineraryValidationError):
        generate_payload(trip_request, payload)


def test_rejects_out_of_order_days(trip_request: TripRequest) -> None:
    payload = itinerary_payload(trip_request)
    payload["days"] = list(reversed(payload["days"]))
    with pytest.raises(ItineraryValidationError):
        generate_payload(trip_request, payload)


@pytest.mark.parametrize("change", [{"destination": "苏州"}, {"end_date": "2026-10-04"}])
def test_rejects_mismatched_request_fields(
    trip_request: TripRequest, change: dict[str, object]
) -> None:
    payload = itinerary_payload(trip_request)
    payload.update(change)
    with pytest.raises(ItineraryValidationError):
        generate_payload(trip_request, payload)


def test_rejects_total_below_activity_cost(trip_request: TripRequest) -> None:
    payload = itinerary_payload(trip_request)
    payload["total_estimated_cost"] = 29
    with pytest.raises(ItineraryValidationError):
        generate_payload(trip_request, payload)


def test_accepts_total_above_activity_cost(trip_request: TripRequest) -> None:
    payload = itinerary_payload(trip_request)
    payload["total_estimated_cost"] = 120
    assert generate_payload(trip_request, payload).total_estimated_cost == 120


def test_converts_generator_timeout(trip_request: TripRequest) -> None:
    with pytest.raises(MomaTimeoutError) as error:
        TripService(StubGenerator(TimeoutError("upstream secret"))).generate(trip_request)
    assert error.value.code == "MOMA_TIMEOUT"
    assert "upstream secret" not in str(error.value)
