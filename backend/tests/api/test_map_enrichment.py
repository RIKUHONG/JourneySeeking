"""Offline tests for POI and route enrichment business rules."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.app.integrations.contracts import Coordinates, Place, Route
from backend.app.integrations.errors import FailureReason
from backend.app.integrations.mock_map_service import MockMapService
from backend.app.main import app, get_trip_service
from backend.app.models.schemas import Activity, DayPlan, Itinerary
from backend.app.services.map_enrichment import MapEnrichmentService, _match_place
from backend.app.services.trip_service import TripService


def itinerary(*names: str) -> Itinerary:
    return Itinerary(
        destination="杭州",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 3),
        summary="测试行程",
        days=[
            DayPlan(
                date=date(2026, 10, 1),
                title="第一天",
                activities=[
                    Activity(time="09:00", name=name, description="游览", estimated_cost=0)
                    for name in names
                ],
            ),
            DayPlan(date=date(2026, 10, 2), title="第二天", activities=[]),
            DayPlan(date=date(2026, 10, 3), title="第三天", activities=[]),
        ],
        total_estimated_cost=0,
    )


def test_enriches_exact_pois_and_route_without_mutating_input():
    west_lake = Place("poi-west", "西湖", "杭州西湖区", Coordinates(120.1, 30.2))
    lingyin = Place("poi-lingyin", "灵隐寺", "杭州西湖区", Coordinates(120.2, 30.3))
    service = MockMapService(
        places=[west_lake, lingyin],
        routes={(west_lake.coordinates, lingyin.coordinates, "driving"): Route(2500, 600)},
    )
    original = itinerary("西湖", "灵隐寺")

    enriched = MapEnrichmentService(service).enrich(original)
    first, second = enriched.days[0].activities

    assert original.days[0].activities[0].poi_id is None
    assert enriched.map_enrichment_status == "completed"
    assert (first.poi_id, first.latitude, first.longitude) == ("poi-west", 30.2, 120.1)
    assert first.poi_status == "verified"
    assert second.route_status == "verified"
    assert second.route_from_previous is not None
    assert second.route_from_previous.distance_meters == 2500
    assert second.route_from_previous.duration_seconds == 600


def test_matches_unique_suffix_normalized_poi_and_records_metrics():
    service = MapEnrichmentService(
        MockMapService(
            places=[
                Place("poi-west", "西湖", "杭州西湖区", Coordinates(120.1, 30.2)),
            ]
        )
    )

    result = service.enrich(itinerary("西湖景区"))

    assert result.days[0].activities[0].poi_status == "verified"
    assert result.days[0].activities[0].poi_id == "poi-west"
    assert service.last_metrics.poi_verified == 1
    assert service.last_metrics.poi_verified_rate == 1.0


def test_records_not_found_and_ambiguous_rates():
    service = MapEnrichmentService(
        MockMapService(
            places=[
                Place("poi-west-1", "West Lake", "\u676d\u5dde", Coordinates(120.1, 30.2)),
                Place("poi-west-2", "West Lake", "\u676d\u5dde", Coordinates(120.2, 30.3)),
                Place("poi-lingyin", "Lingyin Temple", "\u676d\u5dde", Coordinates(120.3, 30.4)),
            ]
        )
    )

    result = service.enrich(itinerary("West Lake", "Missing Place", "Lingyin Temple"))

    assert result.map_enrichment_status == "partial"
    assert service.last_metrics.poi_total == 3
    assert service.last_metrics.poi_not_found == 1
    assert service.last_metrics.poi_ambiguous == 1
    assert service.last_metrics.poi_not_found_rate == pytest.approx(1 / 3)
    assert service.last_metrics.poi_ambiguous_rate == pytest.approx(1 / 3)


def test_keeps_same_name_candidates_ambiguous_after_normalization():
    service = MapEnrichmentService(
        MockMapService(
            places=[
                Place("poi-1", "西湖景区", "杭州西湖区", Coordinates(120.1, 30.2)),
                Place("poi-2", "西湖风景区", "杭州西湖区", Coordinates(120.2, 30.3)),
            ]
        )
    )

    result = service.enrich(itinerary("西湖"))

    assert result.days[0].activities[0].poi_status == "ambiguous"
    assert service.last_metrics.poi_ambiguous == 1
    assert service.last_metrics.poi_verified_rate == 0.0


def test_location_context_disambiguates_duplicate_pois():
    activity = Activity(
        time="09:00",
        name="西湖",
        location="西湖区孤山路",
        description="游览",
        estimated_cost=0,
    )
    selected = _match_place(
        activity,
        [
            Place("poi-hz", "西湖", "杭州市西湖区孤山路", Coordinates(120.1, 30.2)),
            Place("poi-other", "西湖", "杭州市余杭区未来科技城", Coordinates(120.2, 30.3)),
        ],
    )
    assert selected is not None
    assert selected.provider_id == "poi-hz"


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (("不存在",), "not_found"),
        (("西湖",), "ambiguous"),
    ],
)
def test_does_not_guess_unverified_pois(names, expected):
    places = [
        Place("poi-1", "西湖", "杭州", Coordinates(120.1, 30.2)),
        Place("poi-2", "西湖", "杭州", Coordinates(120.2, 30.3)),
    ]
    if expected == "not_found":
        places = []
    result = MapEnrichmentService(MockMapService(places=places)).enrich(itinerary(*names))
    activity = result.days[0].activities[0]
    assert activity.poi_status == expected
    assert activity.poi_id is None
    assert activity.latitude is None
    assert result.map_enrichment_status == "partial"


def test_map_failure_preserves_base_itinerary_and_marks_unavailable():
    result = MapEnrichmentService(MockMapService(search_failure=FailureReason.TIMEOUT)).enrich(
        itinerary("西湖")
    )
    activity = result.days[0].activities[0]
    assert result.map_enrichment_status == "unavailable"
    assert activity.poi_status == "unavailable"
    assert activity.poi_id is None


def test_unverified_model_poi_fields_are_cleared_before_map_lookup():
    base = itinerary("Unknown")
    base.days[0].activities[0].poi_id = "hotel_001"
    base.days[0].activities[0].poi_category = "hotel"
    base.days[0].activities[0].address = "model-only address"

    result = MapEnrichmentService(MockMapService()).enrich(base)
    activity = result.days[0].activities[0]

    assert activity.poi_id is None
    assert activity.poi_category is None
    assert activity.address is None
    assert activity.poi_status == "not_found"


def test_route_requires_both_verified_coordinates():
    first = Place("poi-1", "西湖", "杭州", Coordinates(120.1, 30.2))
    service = MockMapService(places=[first])
    result = MapEnrichmentService(service).enrich(itinerary("西湖", "未知"))
    assert result.days[0].activities[1].route_from_previous is None
    assert result.days[0].activities[1].route_status == "not_attempted"


def test_route_failure_records_unavailable_metric_and_keeps_base_itinerary():
    first = Place("poi-1", "West Lake", "\u676d\u5dde", Coordinates(120.1, 30.2))
    second = Place("poi-2", "Lingyin Temple", "\u676d\u5dde", Coordinates(120.2, 30.3))
    service = MapEnrichmentService(
        MockMapService(places=[first, second], route_failure=FailureReason.TIMEOUT)
    )

    result = service.enrich(itinerary("West Lake", "Lingyin Temple"))

    assert result.map_enrichment_status == "partial"
    assert result.summary
    assert all(activity.poi_status == "verified" for activity in result.days[0].activities)
    assert result.days[0].activities[1].route_status == "unavailable"
    assert result.days[0].activities[1].route_from_previous is None
    assert service.last_metrics.route_eligible == 1
    assert service.last_metrics.route_verified == 0
    assert service.last_metrics.route_unavailable == 1
    assert service.last_metrics.route_verified_rate == 0.0


def test_generate_endpoint_returns_optional_map_enrichment_fields():
    west_lake = Place("poi-west", "西湖", "杭州西湖区", Coordinates(120.1, 30.2))
    base = itinerary("西湖")

    class Generator:
        def generate(self, request):
            return json.dumps(base.model_dump(mode="json"))

    service = TripService(Generator(), MapEnrichmentService(MockMapService(places=[west_lake])))
    app.dependency_overrides[get_trip_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/trip/generate",
            json={"destination": "杭州", "start_date": "2026-10-01", "end_date": "2026-10-03"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["map_enrichment_status"] == "completed"
    assert body["days"][0]["activities"][0]["poi_id"] == "poi-west"
