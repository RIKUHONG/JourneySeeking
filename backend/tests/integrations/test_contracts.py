"""Offline checks for the external service boundary."""

from dataclasses import replace

import pytest

from backend.app.config.settings import Settings
from backend.app.integrations.errors import (
    FailureReason,
    MapServiceError,
    WeatherServiceError,
)


def test_external_services_do_not_require_keys_at_startup():
    config = Settings(amap_api_key="", weather_api_key="")

    assert config.amap_api_key == ""
    assert config.weather_api_key == ""

    with pytest.raises(ValueError, match="AMAP_API_KEY"):
        config.validate_map()
    with pytest.raises(ValueError, match="WEATHER_API_KEY"):
        config.validate_weather()


@pytest.mark.parametrize("service", ["map", "weather"])
def test_external_config_rejects_invalid_url_timeout_and_retries(service):
    config = Settings(amap_api_key="test-key", weather_api_key="test-key")
    prefix = "amap" if service == "map" else "weather"
    validate = lambda candidate: getattr(candidate, f"validate_{service}")()

    for field, value in (
        (f"{prefix}_base_url", "not-a-url"),
        (f"{prefix}_timeout_seconds", 0),
        (f"{prefix}_timeout_seconds", float("nan")),
        (f"{prefix}_max_retries", -1),
    ):
        with pytest.raises(ValueError):
            validate(replace(config, **{field: value}))


def test_external_errors_use_contract_codes_without_leaking_provider_details():
    map_error = MapServiceError(FailureReason.TIMEOUT)
    weather_error = WeatherServiceError(FailureReason.INVALID_RESPONSE)

    assert map_error.code == "MAP_SERVICE_ERROR"
    assert map_error.reason is FailureReason.TIMEOUT
    assert str(map_error) == "地图服务请求超时"
    assert weather_error.code == "WEATHER_SERVICE_ERROR"
    assert weather_error.reason is FailureReason.INVALID_RESPONSE
    assert str(weather_error) == "天气服务返回的数据无效"
