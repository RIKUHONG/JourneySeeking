"""Stable cache key builders for map lookups."""

from __future__ import annotations

from backend.app.integrations.contracts import Coordinates, TravelMode


def _part(value: str | None) -> str:
    return (value or "").strip().casefold()


def poi_cache_key(keyword: str, *, city: str | None = None) -> str:
    return f"map:poi:v1:{_part(city)}:{_part(keyword)}"


def route_cache_key(origin: Coordinates, destination: Coordinates, *, mode: TravelMode) -> str:
    return (
        f"map:route:v1:{mode}:"
        f"{origin.longitude:.6f},{origin.latitude:.6f}:"
        f"{destination.longitude:.6f},{destination.latitude:.6f}"
    )


# Descriptive aliases for adapters/tests.
build_poi_key = poi_cache_key
build_route_key = route_cache_key
make_poi_cache_key = poi_cache_key
make_route_cache_key = route_cache_key
