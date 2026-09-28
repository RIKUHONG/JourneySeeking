"""Cache interfaces and built-in implementations."""

from .base import Cache
from .keys import (
    build_poi_key,
    build_route_key,
    make_poi_cache_key,
    make_route_cache_key,
    poi_cache_key,
    route_cache_key,
)
from .memory import InMemoryCache, MemoryCache

__all__ = [
    "Cache",
    "MemoryCache",
    "InMemoryCache",
    "poi_cache_key",
    "route_cache_key",
    "build_poi_key",
    "build_route_key",
    "make_poi_cache_key",
    "make_route_cache_key",
]
