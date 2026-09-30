"""City-scoped POI candidate pools for ID-constrained itinerary planning."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from backend.app.integrations.contracts import Coordinates, MapService, Place
from backend.app.integrations.errors import MapServiceError
from backend.app.services.city_resolution import (
    CityCoverageStatus,
    CityResolution,
    resolve_city,
)


class PoiCategory(StrEnum):
    SPOT = "spot"
    MEAL = "meal"
    HOTEL = "hotel"


@dataclass(frozen=True)
class PoiCandidate:
    poi_id: str
    name: str
    category: PoiCategory
    address: str
    latitude: float
    longitude: float

    @classmethod
    def from_place(cls, place: Place, category: PoiCategory) -> PoiCandidate:
        return cls(
            poi_id=place.provider_id,
            name=place.name,
            category=category,
            address=place.address,
            latitude=place.coordinates.latitude,
            longitude=place.coordinates.longitude,
        )


@dataclass(frozen=True)
class PoiCandidatePool:
    city: str
    candidates: tuple[PoiCandidate, ...]
    resolution: CityResolution = field(
        default_factory=lambda: CityResolution(
            requested="",
            city="",
            status=CityCoverageStatus.DYNAMIC,
            reason="legacy_pool",
        )
    )
    minimum_counts: dict[PoiCategory, int] = field(
        default_factory=lambda: {category: 1 for category in PoiCategory}
    )
    rejected_count: int = 0
    unavailable_reason: str | None = None

    @property
    def coverage_status(self) -> CityCoverageStatus:
        return self.resolution.status

    @property
    def counts(self) -> dict[str, int]:
        return {category.value: len(self.for_category(category)) for category in PoiCategory}

    @property
    def shortages(self) -> dict[str, int]:
        return {
            category.value: max(0, minimum - len(self.for_category(category)))
            for category, minimum in self.minimum_counts.items()
            if len(self.for_category(category)) < minimum
        }

    @property
    def meets_minimum(self) -> bool:
        return (
            self.resolution.status is not CityCoverageStatus.INSUFFICIENT_DATA
            and self.unavailable_reason is None
            and not self.shortages
        )

    @property
    def by_id(self) -> dict[str, PoiCandidate]:
        return {candidate.poi_id: candidate for candidate in self.candidates}

    def for_category(self, category: PoiCategory) -> tuple[PoiCandidate, ...]:
        return tuple(item for item in self.candidates if item.category == category)

    def prompt_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "poi_id": item.poi_id,
                "name": item.name,
                "category": item.category.value,
                "address": item.address,
            }
            for item in self.candidates
        ]

    def validate_ids(self, ids: list[str]) -> None:
        if len(ids) != len(set(ids)):
            raise ValueError("Planner returned duplicate POI IDs")
        unknown = sorted(set(ids) - self.by_id.keys())
        if unknown:
            raise ValueError("Planner returned POI IDs outside the candidate pool")


_SEARCHES = (
    (PoiCategory.SPOT, "景点"),
    (PoiCategory.MEAL, "美食"),
    (PoiCategory.HOTEL, "酒店"),
)


def collect_candidate_pool(
    map_service: MapService,
    city: str,
    *,
    limit: int = 25,
    minimum_counts: dict[PoiCategory, int] | None = None,
) -> PoiCandidatePool:
    """Collect trusted city-scoped candidates before model planning.

    Provider failures are retained as diagnostics so callers can degrade to a
    basic itinerary without confusing an unavailable map with an empty city.
    """
    resolution = resolve_city(city)
    minimums = minimum_counts or {category: 1 for category in PoiCategory}
    candidates: list[PoiCandidate] = []
    seen: set[str] = set()
    rejected_count = 0
    unavailable_reason: str | None = None
    for category, keyword in _SEARCHES:
        try:
            places = map_service.search_pois(keyword, city=resolution.city, limit=limit)
        except MapServiceError as exc:
            unavailable_reason = exc.reason.value
            break
        for place in places:
            if not _is_trusted_place(place, resolution.city):
                rejected_count += 1
                continue
            candidate = PoiCandidate.from_place(place, category)
            if candidate.poi_id not in seen:
                seen.add(candidate.poi_id)
                candidates.append(candidate)
    return PoiCandidatePool(
        city=resolution.city,
        candidates=tuple(candidates),
        resolution=resolution,
        minimum_counts=minimums,
        rejected_count=rejected_count,
        unavailable_reason=unavailable_reason,
    )


def _is_trusted_place(place: Place, city: str) -> bool:
    """Reject malformed, cross-city, or coordinate-less provider results."""
    if not isinstance(place.provider_id, str) or not place.provider_id.strip():
        return False
    if not isinstance(place.name, str) or not place.name.strip():
        return False
    coordinates: Coordinates = place.coordinates
    if not (
        math.isfinite(coordinates.longitude)
        and -180 <= coordinates.longitude <= 180
        and math.isfinite(coordinates.latitude)
        and -90 <= coordinates.latitude <= 90
    ):
        return False

    requested = _city_key(city)
    explicit_city = _city_key(place.city or "")
    if explicit_city and not _city_matches(requested, explicit_city):
        return False
    return bool(explicit_city) or bool(place.address and requested in _city_key(place.address))


def _city_key(value: str) -> str:
    return value.replace(" ", "").replace("市", "").replace("省", "").casefold()


def _city_matches(requested: str, candidate: str) -> bool:
    return requested == candidate
