from datetime import date

import httpx
import pytest

from backend.app.config.settings import Settings
from backend.app.integrations.errors import FailureReason, WeatherServiceError
from backend.app.integrations.weather_client import WeatherClient


@pytest.fixture
def config():
    return Settings(
        weather_api_key="test-key",
        weather_base_url="https://weather.test/v3",
        weather_max_retries=0,
    )


def client(config, handler):
    return WeatherClient(config, httpx.Client(transport=httpx.MockTransport(handler)))


def test_city_name_resolves_adcode_then_maps_forecast(config):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/geocode/geo"):
            assert request.url.params["address"] == "杭州"
            return httpx.Response(200, json={"status": "1", "geocodes": [{"adcode": "330100"}]})
        assert request.url.params["city"] == "330100"
        assert request.url.params["extensions"] == "all"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "forecasts": [
                    {
                        "casts": [
                            {
                                "date": "2026-10-01",
                                "dayweather": "晴",
                                "nighttemp": "15",
                                "daytemp": "24",
                            },
                            {
                                "date": "2026-10-02",
                                "dayweather": "雨",
                                "nighttemp": "16",
                                "daytemp": "21",
                            },
                        ]
                    }
                ],
            },
        )

    days = client(config, handler).forecast("杭州", days=2)

    assert paths == ["/v3/geocode/geo", "/v3/weather/weatherInfo"]
    assert days[0].date == date(2026, 10, 1)
    assert (days[0].condition, days[0].low_celsius, days[0].high_celsius) == ("晴", 15, 24)


def test_adcode_skips_geocoding(config):
    def handler(request):
        assert request.url.path == "/v3/weather/weatherInfo"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "forecasts": [
                    {
                        "casts": [
                            {
                                "date": "2026-10-01",
                                "dayweather": "晴",
                                "nighttemp": "15",
                                "daytemp": "24",
                            }
                        ]
                    }
                ],
            },
        )

    assert len(client(config, handler).forecast("330100", days=1)) == 1


def test_provider_error_is_sanitized(config):
    with pytest.raises(WeatherServiceError) as exc_info:
        client(
            config, lambda request: httpx.Response(200, json={"status": "0", "info": "secret"})
        ).forecast("330100", days=1)

    assert exc_info.value.reason is FailureReason.PROVIDER
    assert "secret" not in str(exc_info.value)


def test_timeout_is_classified(config):
    def handler(request):
        raise httpx.ReadTimeout("secret request URL", request=request)

    with pytest.raises(WeatherServiceError) as exc_info:
        client(config, handler).forecast("330100", days=1)

    assert exc_info.value.reason is FailureReason.TIMEOUT
    assert "secret" not in str(exc_info.value)


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "1", "forecasts": []},
        {"status": "1", "forecasts": [{"casts": []}]},
        {"status": "1", "forecasts": [{"casts": [{"date": "bad"}]}]},
        {
            "status": "1",
            "forecasts": [
                {
                    "casts": [
                        {
                            "date": "2026-10-01",
                            "dayweather": "晴",
                            "nighttemp": "nan",
                            "daytemp": "24",
                        }
                    ]
                }
            ],
        },
    ],
)
def test_invalid_forecast_is_consistent_error(config, payload):
    with pytest.raises(WeatherServiceError) as exc_info:
        client(config, lambda request: httpx.Response(200, json=payload)).forecast("330100", days=1)

    assert exc_info.value.reason is FailureReason.INVALID_RESPONSE
