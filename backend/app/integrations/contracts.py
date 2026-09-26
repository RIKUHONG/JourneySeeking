"""Provider-independent contracts for map and weather integrations."""

from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class Coordinates:
    longitude: float
    latitude: float


@dataclass(frozen=True)
class Place:
    provider_id: str
    name: str
    address: str
    coordinates: Coordinates


@dataclass(frozen=True)
class Route:
    distance_meters: int
    duration_seconds: int


@dataclass(frozen=True)
class DailyForecast:
    date: date
    condition: str
    low_celsius: float
    high_celsius: float


TravelMode = Literal["driving", "walking"]


@runtime_checkable
class MapService(Protocol):
    def search_pois(
        self, keyword: str, *, city: str | None = None, limit: int = 10
    ) -> list[Place]: ...

    def plan_route(
        self, origin: Coordinates, destination: Coordinates, *, mode: TravelMode = "driving"
    ) -> Route: ...


@runtime_checkable
class WeatherService(Protocol):
    def forecast(self, city: str, *, days: int = 3) -> list[DailyForecast]: ...
