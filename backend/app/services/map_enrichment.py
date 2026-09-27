"""Business-layer POI and route enrichment for validated itineraries."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import pairwise

from backend.app.integrations.contracts import Coordinates, MapService, Place, Route
from backend.app.integrations.errors import MapServiceError
from backend.app.models.schemas import Activity, Itinerary, RouteInfo


def _normalized(value: str) -> str:
    return "".join(value.casefold().split())


def _match_place(activity: Activity, places: list[Place]) -> Place | None:
    """Accept only one exact normalized name; never guess from similarity."""
    exact = [place for place in places if _normalized(place.name) == _normalized(activity.name)]
    return exact[0] if len(exact) == 1 else None


class MapEnrichmentService:
    """Enrich a validated itinerary while preserving it when maps are unavailable."""

    def __init__(self, map_service: MapService) -> None:
        self.map_service = map_service

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
                places = self.map_service.search_pois(activity.name, city=copied.destination)
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
        for previous, current in pairwise(activities):
            if previous.poi_status != "verified" or current.poi_status != "verified":
                continue
            if previous.longitude is None or previous.latitude is None:
                current.route_status = "missing_coordinates"
                continue
            if current.longitude is None or current.latitude is None:
                current.route_status = "missing_coordinates"
                continue
            try:
                route = self.map_service.plan_route(
                    Coordinates(previous.longitude, previous.latitude),
                    Coordinates(current.longitude, current.latitude),
                    mode=mode,  # type: ignore[arg-type]
                )
            except MapServiceError:
                current.route_status = "unavailable"
                service_unavailable = True
                continue
            self._apply_route(current, route, mode)
            routes_available = True

        verified_count = sum(activity.poi_status == "verified" for activity in activities)
        if service_unavailable and verified_count == 0:
            copied.map_enrichment_status = "unavailable"
        elif (verified_count == len(activities) and routes_available) or verified_count == len(
            activities
        ) == 1:
            copied.map_enrichment_status = "completed"
        else:
            copied.map_enrichment_status = "partial"
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
