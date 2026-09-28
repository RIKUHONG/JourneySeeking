"""Business-layer POI and route enrichment for validated itineraries."""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from backend.app.cache import Cache, poi_cache_key, route_cache_key
from backend.app.integrations.contracts import Coordinates, MapService, Place, Route
from backend.app.integrations.errors import MapServiceError
from backend.app.models.schemas import Activity, Itinerary, RouteInfo
from backend.app.services.poi_candidates import PoiCandidatePool

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
    def poi_not_found_rate(self) -> float:
        return self.poi_not_found / self.poi_total if self.poi_total else 0.0

    @property
    def poi_ambiguous_rate(self) -> float:
        return self.poi_ambiguous / self.poi_total if self.poi_total else 0.0

    @property
    def route_verified_rate(self) -> float:
        return self.route_verified / self.route_eligible if self.route_eligible else 0.0


def _normalized(value: str) -> str:
    """Normalize names for deterministic, conservative POI matching."""
    value = value.casefold().strip()
    value = re.sub(r"[\s\-_（）()【】\[\]·•、,，.。/\\]+", "", value)
    return "".join(
        char for char in value if not unicodedata.category(char).startswith(("P", "S", "Z"))
    )


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


def _tokens(value: str) -> set[str]:
    """Return useful chunks for matching an activity location context."""
    normalized = _normalized(value)
    if not normalized:
        return set()
    chunks = {normalized}
    chunks.update(
        part for part in re.split(r"[路街道区县市省镇乡村号栋座层店馆园]", normalized) if part
    )
    return {chunk for chunk in chunks if len(chunk) >= 2}


def _match_place(activity: Activity, places: list[Place]) -> Place | None:
    """Match one real candidate using name plus location evidence."""
    activity_name = _normalized(activity.name)
    activity_variants = _name_variants(activity.name)
    location_tokens = _tokens(activity.location or "")
    scored: list[tuple[int, Place]] = []
    for place in places:
        place_name = _normalized(place.name)
        place_address = _normalized(place.address)
        place_tokens = _tokens(place.name) | _tokens(place.address)
        score = 0
        if place_name == activity_name:
            score += 100
        elif activity_variants & _name_variants(place.name):
            score += 70
        elif len(activity_name) >= 2 and (
            activity_name in place_name or place_name in activity_name
        ):
            score += 50
        if location_tokens:
            score += 25 * sum(token in place_tokens for token in location_tokens)
            score += 10 * sum(token in place_address for token in location_tokens)
        if score:
            scored.append((score, place))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score = scored[0][0]
    best = [place for score, place in scored if score == best_score]
    return best[0] if len(best) == 1 else None


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
        except Exception:
            logger.warning("cache read failed; bypassing cache", exc_info=True)
            return None

    def _store(self, key: str, value: Any, *, ttl_seconds: float | None) -> None:
        if self.cache is None:
            return
        try:
            self.cache.set(key, value, ttl_seconds=ttl_seconds)
        except Exception:
            logger.warning("cache write failed; continuing without cache", exc_info=True)
            return

    def enrich(
        self,
        itinerary: Itinerary,
        *,
        mode: str = "driving",
        candidate_pool: PoiCandidatePool | None = None,
        require_poi_ids: bool = False,
    ) -> Itinerary:
        if mode not in {"driving", "walking"}:
            raise ValueError("Unsupported travel mode")

        copied = itinerary.model_copy(deep=True)
        activities = list(self._activities(copied))
        if not activities:
            copied.map_enrichment_status = "completed"
            return copied

        service_unavailable = False
        for activity in activities:
            if candidate_pool is not None and require_poi_ids:
                candidate = candidate_pool.by_id.get(activity.poi_id or "")
                if candidate is None:
                    activity.poi_status = "not_found"
                    continue
                self._apply_candidate(activity, candidate)
                continue
            try:
                places_by_id: dict[str, Place] = {}
                search_names = [activity.name]
                if activity.location and activity.location != activity.name:
                    search_names.append(f"{activity.name} {activity.location}")
                    search_names.append(activity.location)
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
    def _apply_candidate(activity: Activity, candidate: object) -> None:
        activity.poi_id = candidate.poi_id  # type: ignore[attr-defined]
        activity.poi_category = candidate.category.value  # type: ignore[attr-defined]
        activity.name = candidate.name  # type: ignore[attr-defined]
        activity.location = candidate.address or activity.location  # type: ignore[attr-defined]
        activity.address = candidate.address or None  # type: ignore[attr-defined]
        activity.latitude = candidate.latitude  # type: ignore[attr-defined]
        activity.longitude = candidate.longitude  # type: ignore[attr-defined]
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
