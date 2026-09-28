"""Business-layer POI and route enrichment for validated itineraries."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from backend.app.cache import Cache, poi_cache_key, route_cache_key
from backend.app.integrations.contracts import Coordinates, MapService, Place, Route
from backend.app.integrations.errors import MapServiceError
from backend.app.models.schemas import Activity, Itinerary, RouteInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MapEnrichmentMetrics:
    """Quality counters for one itinerary enrichment attempt."""

    poi_total: int = 0
    poi_verified: int = 0
    poi_not_found: int = 0
    poi_ambiguous: int = 0
    poi_unavailable: int = 0
    route_eligible: int = 0
    route_verified: int = 0
    route_unavailable: int = 0

    @property
    def poi_verified_rate(self) -> float:
        return self.poi_verified / self.poi_total if self.poi_total else 0.0

    @property
    def route_verified_rate(self) -> float:
        return self.route_verified / self.route_eligible if self.route_eligible else 0.0


def _normalized(value: str) -> str:
    """Normalize names for deterministic, conservative POI matching."""
    value = value.casefold().strip()
    value = re.sub(r"[\s\-_（）()【】\[\]·•、,，.。/\\]+", "", value)
    return value


_NAME_SUFFIXES = (
    "风景名胜区",
    "风景区",
    "旅游区",
    "景区",
    "博物馆",
    "纪念馆",
    "美术馆",
    "公园",
    "广场",
    "分店",
    "店",
)


def _name_variants(value: str) -> set[str]:
    normalized = _normalized(value)
    variants = {normalized}
    for suffix in _NAME_SUFFIXES:
        normalized_suffix = _normalized(suffix)
        if normalized.endswith(normalized_suffix) and len(normalized) > len(normalized_suffix):
            variants.add(normalized[: -len(normalized_suffix)])
    return {variant for variant in variants if len(variant) >= 2}


def _match_place(activity: Activity, places: list[Place]) -> Place | None:
    """Match a unique candidate without guessing between ambiguous POIs.

    Exact normalized names win. If no exact match exists, a suffix-normalized
    or unique containment match is accepted. Similarity scores are deliberately
    not used: two same-name branches must remain ``ambiguous``.
    """
    activity_name = _normalized(activity.name)
    exact = [place for place in places if _normalized(place.name) == activity_name]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None

    activity_variants = _name_variants(activity.name)
    reduced = []
    for place in places:
        place_variants = _name_variants(place.name)
        if activity_variants & place_variants:
            reduced.append(place)
    if len(reduced) == 1:
        return reduced[0]
    if len(reduced) > 1:
        return None

    containment = [
        place
        for place in places
        if len(activity_name) >= 2
        and (_normalized(place.name) in activity_name or activity_name in _normalized(place.name))
    ]
    return containment[0] if len(containment) == 1 else None


class MapEnrichmentService:
    """Enrich a validated itinerary while preserving it when maps are unavailable."""

    def __init__(
        self,
        map_service: MapService,
        cache: Cache[Any] | None = None,
        *,
        poi_ttl_seconds: float | None = 300.0,
        route_ttl_seconds: float | None = 300.0,
    ) -> None:
        self.map_service = map_service
        self.cache = cache
        self.poi_ttl_seconds = poi_ttl_seconds
        self.route_ttl_seconds = route_ttl_seconds
        self.last_metrics = MapEnrichmentMetrics()

    def _cached(self, key: str) -> Any | None:
        if self.cache is None:
            return None
        try:
            return self.cache.get(key)
        except Exception:  # cache is an optional optimization, never a dependency
            logger.warning("cache read failed; bypassing cache", exc_info=True)
            return None

    def _store(self, key: str, value: Any, *, ttl_seconds: float | None) -> None:
        if self.cache is None:
            return
        try:
            self.cache.set(key, value, ttl_seconds=ttl_seconds)
        except Exception:  # cache is an optional optimization, never a dependency
            logger.warning("cache write failed; continuing without cache", exc_info=True)

    def enrich(self, itinerary: Itinerary, *, mode: str = "driving") -> Itinerary:
        if mode not in {"driving", "walking"}:
            raise ValueError("Unsupported travel mode")

        copied = itinerary.model_copy(deep=True)
        activities = list(self._activities(copied))
        if not activities:
            copied.map_enrichment_status = "completed"
            return copied

        service_unavailable = False
        for activity in activities:
            try:
                places_by_id: dict[str, Place] = {}
                search_names = [activity.name]
                normalized_activity = _normalized(activity.name)
                for variant in _name_variants(activity.name):
                    if variant != normalized_activity:
                        search_names.append(variant)
                for search_name in search_names:
                    key = poi_cache_key(search_name, city=copied.destination)
                    cached_places = self._cached(key)
                    if cached_places is None:
                        cached_places = self.map_service.search_pois(
                            search_name, city=copied.destination
                        )
                        self._store(key, list(cached_places), ttl_seconds=self.poi_ttl_seconds)
                    for place in cached_places:
                        places_by_id.setdefault(place.provider_id, place)
                places = list(places_by_id.values())
            except MapServiceError:
                activity.poi_status = "unavailable"
                service_unavailable = True
                continue

            if not places:
                activity.poi_status = "not_found"
                continue
            place = _match_place(activity, places)
            if place is None:
                activity.poi_status = "ambiguous"
                continue
            self._apply_place(activity, place)

        routes_available = False
        route_eligible = 0
        route_verified = 0
        route_unavailable = 0
        for previous, current in pairwise(activities):
            if previous.poi_status != "verified" or current.poi_status != "verified":
                continue
            if previous.longitude is None or previous.latitude is None:
                current.route_status = "missing_coordinates"
                continue
            if current.longitude is None or current.latitude is None:
                current.route_status = "missing_coordinates"
                continue
            route_eligible += 1
            try:
                origin = Coordinates(previous.longitude, previous.latitude)
                destination = Coordinates(current.longitude, current.latitude)
                key = route_cache_key(origin, destination, mode=mode)  # type: ignore[arg-type]
                route = self._cached(key)
                if route is None:
                    route = self.map_service.plan_route(
                        origin,
                        destination,
                        mode=mode,  # type: ignore[arg-type]
                    )
                    self._store(key, route, ttl_seconds=self.route_ttl_seconds)
            except MapServiceError:
                current.route_status = "unavailable"
                service_unavailable = True
                route_unavailable += 1
                continue
            self._apply_route(current, route, mode)
            routes_available = True
            route_verified += 1

        verified_count = sum(activity.poi_status == "verified" for activity in activities)
        if service_unavailable and verified_count == 0:
            copied.map_enrichment_status = "unavailable"
        elif (verified_count == len(activities) and routes_available) or verified_count == len(
            activities
        ) == 1:
            copied.map_enrichment_status = "completed"
        else:
            copied.map_enrichment_status = "partial"
        counts = {
            "verified": sum(activity.poi_status == "verified" for activity in activities),
            "not_found": sum(activity.poi_status == "not_found" for activity in activities),
            "ambiguous": sum(activity.poi_status == "ambiguous" for activity in activities),
            "unavailable": sum(activity.poi_status == "unavailable" for activity in activities),
        }
        self.last_metrics = MapEnrichmentMetrics(
            poi_total=len(activities),
            poi_verified=counts["verified"],
            poi_not_found=counts["not_found"],
            poi_ambiguous=counts["ambiguous"],
            poi_unavailable=counts["unavailable"],
            route_eligible=route_eligible,
            route_verified=route_verified,
            route_unavailable=route_unavailable,
        )
        logger.info(
            "map enrichment metrics: poi=%d/%d (%.3f) route=%d/%d (%.3f)",
            self.last_metrics.poi_verified,
            self.last_metrics.poi_total,
            self.last_metrics.poi_verified_rate,
            self.last_metrics.route_verified,
            self.last_metrics.route_eligible,
            self.last_metrics.route_verified_rate,
        )
        return copied

    @staticmethod
    def _activities(itinerary: Itinerary) -> Iterable[Activity]:
        for day in itinerary.days:
            yield from day.activities

    @staticmethod
    def _apply_place(activity: Activity, place: Place) -> None:
        activity.poi_id = place.provider_id
        activity.address = place.address or None
        activity.latitude = place.coordinates.latitude
        activity.longitude = place.coordinates.longitude
        activity.poi_status = "verified"
        activity.map_source = "amap"

    @staticmethod
    def _apply_route(activity: Activity, route: Route, mode: str) -> None:
        activity.route_from_previous = RouteInfo(
            mode=mode,
            distance_meters=route.distance_meters,
            duration_seconds=route.duration_seconds,
        )
        activity.route_status = "verified"
