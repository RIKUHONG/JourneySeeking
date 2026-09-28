"""City-scoped POI candidate pools for ID-constrained itinerary planning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from backend.app.integrations.contracts import MapService, Place


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
    map_service: MapService, city: str, *, limit: int = 25
) -> PoiCandidatePool:
    """Collect and deduplicate city-scoped candidates before model planning."""
    candidates: list[PoiCandidate] = []
    seen: set[str] = set()
    for category, keyword in _SEARCHES:
        for place in map_service.search_pois(keyword, city=city, limit=limit):
            candidate = PoiCandidate.from_place(place, category)
            if candidate.poi_id not in seen:
                seen.add(candidate.poi_id)
                candidates.append(candidate)
    return PoiCandidatePool(city=city, candidates=tuple(candidates))
