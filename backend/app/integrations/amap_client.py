"""Amap POI search and route planning adapter."""

import math
from typing import Any

import httpx

from ..config.settings import Settings, settings
from ._amap_http import request_amap
from .contracts import Coordinates, Place, Route, TravelMode
from .errors import FailureReason, MapServiceError


def _coordinates(value: Any) -> Coordinates:
    if not isinstance(value, str):
        raise TypeError("Missing coordinates")
    parts = value.split(",")
    if len(parts) != 2:
        raise ValueError("Invalid coordinates")
    longitude, latitude = map(float, parts)
    if not (math.isfinite(longitude) and -180 <= longitude <= 180):
        raise ValueError("Invalid longitude")
    if not (math.isfinite(latitude) and -90 <= latitude <= 90):
        raise ValueError("Invalid latitude")
    return Coordinates(longitude, latitude)


def _distance_or_duration(value: Any) -> int:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError("Invalid route value")
    return round(number)


class AmapClient:
    def __init__(self, config: Settings = settings, session: httpx.Client | None = None) -> None:
        self.config = config
        self.session = session

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            self.config.validate_map()
        except ValueError as exc:
            raise MapServiceError(FailureReason.CONFIGURATION) from exc
        return request_amap(
            path,
            params,
            base_url=self.config.amap_base_url,
            api_key=self.config.amap_api_key,
            timeout_seconds=self.config.amap_timeout_seconds,
            max_retries=self.config.amap_max_retries,
            error_type=MapServiceError,
            session=self.session,
        )

    def search_pois(self, keyword: str, *, city: str | None = None, limit: int = 10) -> list[Place]:
        if not keyword.strip() or not 1 <= limit <= 25:
            raise ValueError("POI search requires a keyword and a limit from 1 to 25")
        params: dict[str, Any] = {
            "keywords": keyword.strip(),
            "offset": limit,
            "page": 1,
            "extensions": "all",
        }
        if city:
            params.update(city=city.strip(), citylimit="true")
        payload = self._request("/place/text", params)
        pois = payload.get("pois")
        if not isinstance(pois, list):
            raise MapServiceError(FailureReason.INVALID_RESPONSE)
        places = []
        for poi in pois:
            if not isinstance(poi, dict):
                raise MapServiceError(FailureReason.INVALID_RESPONSE)
            try:
                provider_id = poi["id"]
                name = poi["name"]
                coordinates = _coordinates(poi["location"])
                if not isinstance(provider_id, str) or not provider_id:
                    raise ValueError("Invalid POI ID")
                if not isinstance(name, str) or not name:
                    raise ValueError("Invalid POI name")
            except (KeyError, TypeError, ValueError) as exc:
                raise MapServiceError(FailureReason.INVALID_RESPONSE) from exc
            address = poi.get("address")
            places.append(
                Place(provider_id, name, address if isinstance(address, str) else "", coordinates)
            )
        return places

    def plan_route(
        self, origin: Coordinates, destination: Coordinates, *, mode: TravelMode = "driving"
    ) -> Route:
        if mode not in ("driving", "walking"):
            raise ValueError("Unsupported travel mode")
        try:
            for point in (origin, destination):
                _coordinates(f"{point.longitude},{point.latitude}")
        except (AttributeError, ValueError) as exc:
            raise ValueError("Invalid route coordinates") from exc
        params: dict[str, Any] = {
            "origin": f"{origin.longitude},{origin.latitude}",
            "destination": f"{destination.longitude},{destination.latitude}",
        }
        if mode == "driving":
            params["strategy"] = 0
        payload = self._request(f"/direction/{mode}", params)
        try:
            path = payload["route"]["paths"][0]
            return Route(
                distance_meters=_distance_or_duration(path["distance"]),
                duration_seconds=_distance_or_duration(path["duration"]),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise MapServiceError(FailureReason.INVALID_RESPONSE) from exc
