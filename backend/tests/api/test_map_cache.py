"""Offline tests for map lookup caching and cache degradation."""

from __future__ import annotations

import time
from datetime import date

from backend.app.cache import MemoryCache
from backend.app.integrations.contracts import Coordinates, Place, Route
from backend.app.models.schemas import Activity, DayPlan, Itinerary
from backend.app.services.map_enrichment import MapEnrichmentService


def make_itinerary(*names: str) -> Itinerary:
    return Itinerary(
        destination="\u676d\u5dde",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 1),
        summary="cache test",
        days=[
            DayPlan(
                date=date(2026, 10, 1),
                title="day one",
                activities=[
                    Activity(time="09:00", name=name, description="visit", estimated_cost=0)
                    for name in names
                ],
            )
        ],
        total_estimated_cost=0,
    )


class CountingMapService:
    def __init__(self, places: list[Place], route: Route | None = None) -> None:
        self.places = places
        self.route = route
        self.search_calls = 0
        self.route_calls = 0

    def search_pois(self, keyword: str, *, city: str | None = None, limit: int = 10):
        self.search_calls += 1
        return [place for place in self.places if place.name == keyword][:limit]

    def plan_route(self, origin: Coordinates, destination: Coordinates, *, mode="driving"):
        self.route_calls += 1
        if self.route is None:
            raise AssertionError("a route was requested without a configured route")
        return self.route


class BrokenCache:
    def get(self, key: str):
        raise RuntimeError("cache read unavailable")

    def set(self, key: str, value, *, ttl_seconds: float | None = None) -> None:
        raise RuntimeError("cache write unavailable")

    def delete(self, key: str) -> None:
        return None

    def clear(self) -> None:
        return None


def test_poi_first_call_misses_and_second_call_hits():
    place = Place("poi-west", "West Lake", "\u676d\u5dde", Coordinates(120.1, 30.2))
    map_service = CountingMapService([place])
    service = MapEnrichmentService(map_service, cache=MemoryCache())

    first = service.enrich(make_itinerary("West Lake"))
    second = service.enrich(make_itinerary("West Lake"))

    assert first.days[0].activities[0].poi_status == "verified"
    assert second.days[0].activities[0].poi_status == "verified"
    assert map_service.search_calls == 1


def test_route_first_call_misses_and_second_call_hits():
    first = Place("poi-west", "West Lake", "\u676d\u5dde", Coordinates(120.1, 30.2))
    second = Place("poi-lingyin", "Lingyin Temple", "\u676d\u5dde", Coordinates(120.2, 30.3))
    map_service = CountingMapService([first, second], Route(2500, 600))
    service = MapEnrichmentService(map_service, cache=MemoryCache())

    service.enrich(make_itinerary("West Lake", "Lingyin Temple"))
    result = service.enrich(make_itinerary("West Lake", "Lingyin Temple"))

    assert result.days[0].activities[1].route_status == "verified"
    assert map_service.search_calls == 2
    assert map_service.route_calls == 1


def test_expired_poi_entry_is_requested_again():
    place = Place("poi-west", "West Lake", "\u676d\u5dde", Coordinates(120.1, 30.2))
    map_service = CountingMapService([place])
    service = MapEnrichmentService(
        map_service,
        cache=MemoryCache(default_ttl_seconds=0.01),
        poi_ttl_seconds=0.01,
    )

    service.enrich(make_itinerary("West Lake"))
    time.sleep(0.02)
    service.enrich(make_itinerary("West Lake"))

    assert map_service.search_calls == 2


def test_cache_get_failure_bypasses_cache_and_calls_map_service():
    place = Place("poi-west", "West Lake", "\u676d\u5dde", Coordinates(120.1, 30.2))
    map_service = CountingMapService([place])

    result = MapEnrichmentService(map_service, cache=BrokenCache()).enrich(
        make_itinerary("West Lake")
    )

    assert result.days[0].activities[0].poi_status == "verified"
    assert map_service.search_calls == 1


def test_cache_set_failure_still_returns_map_enrichment():
    place = Place("poi-west", "West Lake", "\u676d\u5dde", Coordinates(120.1, 30.2))
    map_service = CountingMapService([place])

    result = MapEnrichmentService(map_service, cache=BrokenCache()).enrich(
        make_itinerary("West Lake")
    )

    assert result.map_enrichment_status == "completed"
    assert result.days[0].activities[0].poi_id == "poi-west"


def test_unavailable_cache_does_not_block_base_itinerary():
    place = Place("poi-west", "West Lake", "\u676d\u5dde", Coordinates(120.1, 30.2))
    map_service = CountingMapService([place])
    original = make_itinerary("West Lake")

    result = MapEnrichmentService(map_service, cache=BrokenCache()).enrich(original)

    assert result.summary == original.summary
    assert result.days[0].activities[0].poi_status == "verified"
    assert original.days[0].activities[0].poi_id is None
