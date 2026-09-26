from datetime import date

import pytest

from backend.app.integrations.contracts import (
    Coordinates,
    DailyForecast,
    MapService,
    Place,
    Route,
    WeatherService,
)
from backend.app.integrations.errors import FailureReason, MapServiceError, WeatherServiceError
from backend.app.integrations.mock_map_service import MockMapService
from backend.app.integrations.mock_weather_service import MockWeatherService


def test_mock_map_implements_contract_without_network():
    origin = Coordinates(120.1, 30.2)
    destination = Coordinates(120.2, 30.3)
    place = Place("poi1", "西湖", "杭州西湖区", origin)
    service = MockMapService(
        places=[place], routes={(origin, destination, "driving"): Route(2500, 600)}
    )

    assert isinstance(service, MapService)
    assert service.search_pois("西湖", city="杭州") == [place]
    assert service.plan_route(origin, destination) == Route(2500, 600)
    assert service.search_pois("不存在") == []


def test_mock_weather_implements_contract_and_failure_injection():
    forecast = DailyForecast(date(2026, 10, 1), "晴", 15, 24)
    service = MockWeatherService(forecasts={"杭州": [forecast]})

    assert isinstance(service, WeatherService)
    assert service.forecast("杭州", days=1) == [forecast]
    with pytest.raises(WeatherServiceError) as empty_info:
        service.forecast("不存在", days=1)
    assert empty_info.value.reason is FailureReason.INVALID_RESPONSE
    with pytest.raises(WeatherServiceError) as exc_info:
        MockWeatherService(failure=FailureReason.TIMEOUT).forecast("杭州", days=1)
    assert exc_info.value.reason is FailureReason.TIMEOUT
    with pytest.raises(MapServiceError):
        MockMapService(search_failure=FailureReason.NETWORK).search_pois("西湖")
