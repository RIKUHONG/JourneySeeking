"""Offline map service with caller-supplied deterministic data."""

from collections.abc import Mapping, Sequence

from .contracts import Coordinates, Place, Route, TravelMode
from .errors import FailureReason, MapServiceError


class MockMapService:
    def __init__(
        self,
        *,
        places: Sequence[Place] = (),
        routes: Mapping[tuple[Coordinates, Coordinates, TravelMode], Route] | None = None,
        search_failure: FailureReason | None = None,
        route_failure: FailureReason | None = None,
    ) -> None:
        self.places = list(places)
        self.routes = dict(routes or {})
        self.search_failure = search_failure
        self.route_failure = route_failure

    def search_pois(self, keyword: str, *, city: str | None = None, limit: int = 10) -> list[Place]:
        if self.search_failure is not None:
            raise MapServiceError(self.search_failure)
        if not keyword.strip() or not 1 <= limit <= 25:
            raise ValueError("POI search requires a keyword and a limit from 1 to 25")
        matches = [place for place in self.places if keyword.lower() in place.name.lower()]
        if city:
            matches = [place for place in matches if city.lower() in place.address.lower()]
        return matches[:limit]

    def plan_route(
        self, origin: Coordinates, destination: Coordinates, *, mode: TravelMode = "driving"
    ) -> Route:
        if self.route_failure is not None:
            raise MapServiceError(self.route_failure)
        if mode not in ("driving", "walking"):
            raise ValueError("Unsupported travel mode")
        try:
            return self.routes[(origin, destination, mode)]
        except KeyError as exc:
            raise MapServiceError(FailureReason.INVALID_RESPONSE) from exc
