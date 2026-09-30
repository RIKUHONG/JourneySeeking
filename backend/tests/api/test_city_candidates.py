"""P2-02 city resolution and candidate quality tests."""

import json
import math

import pytest

from backend.app.integrations.contracts import Coordinates, Place
from backend.app.integrations.errors import FailureReason
from backend.app.integrations.mock_map_service import MockMapService
from backend.app.models.schemas import TripRequest
from backend.app.services.city_resolution import CityCoverageStatus, resolve_city
from backend.app.services.itinerary_generator import ItineraryGenerator
from backend.app.services.poi_candidates import PoiCategory, collect_candidate_pool


def place(
    provider_id: str,
    name: str,
    *,
    city: str | None = "杭州",
    address: str = "杭州市西湖区",
    coordinates: Coordinates | None = None,
) -> Place:
    coordinates = coordinates or Coordinates(120.1, 30.2)
    return Place(provider_id, name, address, coordinates, city=city)


def test_city_aliases_are_normalized_and_province_input_is_ineligible():
    assert resolve_city("杭州市").city == "杭州"
    assert resolve_city("西湖区").city == "杭州"
    assert resolve_city("杭州").status is CityCoverageStatus.CURATED

    province = resolve_city("浙江省")
    assert province.status is CityCoverageStatus.INSUFFICIENT_DATA
    assert province.reason == "province_requires_city"

    for destination in ("广西壮族自治区", "新疆维吾尔自治区", "香港特别行政区"):
        assert resolve_city(destination).status is CityCoverageStatus.INSUFFICIENT_DATA


def test_unknown_non_province_destination_remains_dynamic():
    result = resolve_city("张家界")
    assert result.city == "张家界"
    assert result.status is CityCoverageStatus.DYNAMIC


def test_candidate_pool_rejects_cross_city_missing_coordinates_and_invalid_ids():
    places = [
        place("ok", "景点"),
        place("other", "美食", city="苏州", address="苏州市姑苏区"),
        place("missing", "酒店", coordinates=Coordinates(math.nan, 30.2)),
        place(" ", "酒店"),
        place("no-region", "酒店", city=None, address=""),
    ]

    class UnfilteredMap:
        def search_pois(self, keyword, *, city=None, limit=10):
            return [item for item in places if keyword in item.name]

    pool = collect_candidate_pool(UnfilteredMap(), "杭州")

    assert [candidate.poi_id for candidate in pool.candidates] == ["ok"]
    assert pool.rejected_count == 4
    assert pool.counts == {"spot": 1, "meal": 0, "hotel": 0}
    assert pool.shortages == {"meal": 1, "hotel": 1}
    assert not pool.meets_minimum


def test_explicit_provider_city_requires_exact_normalized_match():
    places = [
        place("child", "景点", city="杭州市西湖区"),
        place("same", "景点", city="杭州市"),
    ]

    class UnfilteredMap:
        def search_pois(self, keyword, *, city=None, limit=10):
            return places if keyword == "景点" else []

    pool = collect_candidate_pool(
        UnfilteredMap(),
        "杭州",
        minimum_counts={PoiCategory.SPOT: 1, PoiCategory.MEAL: 0, PoiCategory.HOTEL: 0},
    )

    assert [candidate.poi_id for candidate in pool.candidates] == ["same"]
    assert pool.rejected_count == 1


def test_generator_preserves_incomplete_pool_diagnostics_when_falling_back():
    pool = collect_candidate_pool(MockMapService(), "浙江省")

    class Client:
        def chat(self, messages):
            return json.dumps(
                {
                    "destination": "浙江省",
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-03",
                    "summary": "基础行程",
                    "days": [
                        {"date": "2026-10-01", "title": "第一天", "activities": []},
                        {"date": "2026-10-02", "title": "第二天", "activities": []},
                        {"date": "2026-10-03", "title": "第三天", "activities": []},
                    ],
                    "total_estimated_cost": 0,
                },
                ensure_ascii=False,
            )

    generator = ItineraryGenerator(Client(), candidate_provider=lambda request: pool)
    generator.generate(
        TripRequest(destination="浙江省", start_date="2026-10-01", end_date="2026-10-03")
    )

    assert generator.last_candidate_pool is None
    assert generator.last_candidate_diagnostics is pool
    assert (
        generator.last_candidate_diagnostics.coverage_status is CityCoverageStatus.INSUFFICIENT_DATA
    )


def test_candidate_pool_reports_provider_failure_without_mislabeling_empty_results():
    pool = collect_candidate_pool(
        MockMapService(search_failure=FailureReason.TIMEOUT),
        "杭州",
    )

    assert pool.candidates == ()
    assert pool.unavailable_reason == "timeout"
    assert not pool.meets_minimum
    assert pool.shortages == {"spot": 1, "meal": 1, "hotel": 1}


def test_candidate_pool_rejects_province_scope_even_with_provider_results():
    pool = collect_candidate_pool(
        MockMapService(
            places=[
                place("spot", "景点", city="浙江", address="浙江省"),
                place("meal", "美食", city="浙江", address="浙江省"),
                place("hotel", "酒店", city="浙江", address="浙江省"),
            ]
        ),
        "浙江省",
    )

    assert pool.coverage_status is CityCoverageStatus.INSUFFICIENT_DATA
    assert not pool.meets_minimum


@pytest.mark.parametrize(
    "category, expected",
    [(PoiCategory.SPOT, 1), (PoiCategory.MEAL, 1), (PoiCategory.HOTEL, 1)],
)
def test_default_threshold_has_one_candidate_per_category(category, expected):
    pool = collect_candidate_pool(MockMapService(), "杭州")
    assert pool.minimum_counts[category] == expected
