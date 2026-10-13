from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from backend.app.config.settings import Settings
from backend.app.integrations.contracts import Coordinates
from backend.app.integrations.errors import FailureReason, MapServiceError, WeatherServiceError
from backend.app.integrations.weather_client import WeatherClient

NOW = datetime(2026, 10, 13, 8, tzinfo=UTC)


class Geocoder:
    def __init__(self, failure=None):
        self.calls = []
        self.failure = failure

    def geocode_city(self, city):
        self.calls.append(city)
        if self.failure:
            raise MapServiceError(self.failure)
        return Coordinates(120.16, 30.29)


@pytest.fixture
def config():
    return Settings(
        amap_api_key="test-map-key",
        weather_base_url="https://weather.test/v1",
        weather_max_retries=0,
    )


def client(config, handler, *, geocoder=None):
    geocoder = geocoder or Geocoder()
    weather = WeatherClient(
        config,
        httpx.Client(transport=httpx.MockTransport(handler)),
        geocoder=geocoder,
        now=lambda: NOW,
    )
    return weather, geocoder


def daily_payload(dates, *, codes=None, lows=None, highs=None):
    count = len(dates)
    return {
        "daily": {
            "time": [item.isoformat() if isinstance(item, date) else item for item in dates],
            "weather_code": codes if codes is not None else [0] * count,
            "temperature_2m_min": lows if lows is not None else [15] * count,
            "temperature_2m_max": highs if highs is not None else [24] * count,
        }
    }


def test_seven_day_window_maps_dates_source_and_fetch_time(config):
    start = date(2026, 10, 14)
    dates = [start + timedelta(days=offset) for offset in range(7)]

    def handler(request):
        assert request.url.path == "/v1/forecast"
        assert request.url.params["latitude"] == "30.29"
        assert request.url.params["longitude"] == "120.16"
        assert request.url.params["start_date"] == "2026-10-14"
        assert request.url.params["end_date"] == "2026-10-20"
        assert request.url.params["timezone"] == "auto"
        assert "key" not in request.url.params
        return httpx.Response(200, json=daily_payload(dates, codes=[0, 1, 2, 3, 61, 80, 95]))

    weather, geocoder = client(config, handler)
    result = weather.forecast_window("杭州", start_date=start, end_date=dates[-1])

    assert geocoder.calls == ["杭州"]
    assert [item.date for item in result] == dates
    assert [item.condition for item in result] == [
        "晴",
        "晴间多云",
        "多云",
        "阴",
        "小雨",
        "小阵雨",
        "雷阵雨",
    ]
    assert all(item.source == "Open-Meteo" for item in result)
    assert all(item.fetched_at == "2026-10-13T08:00:00+00:00" for item in result)


def test_legacy_forecast_uses_china_today(config):
    def handler(request):
        assert request.url.params["start_date"] == "2026-10-13"
        assert request.url.params["end_date"] == "2026-10-15"
        return httpx.Response(
            200,
            json=daily_payload([date(2026, 10, 13) + timedelta(days=index) for index in range(3)]),
        )

    weather, _ = client(config, handler)
    assert len(weather.forecast("杭州", days=3)) == 3


def test_legacy_forecast_supports_seven_days(config):
    def handler(request):
        start = date(2026, 10, 13)
        dates = [start + timedelta(days=index) for index in range(7)]
        assert request.url.params["start_date"] == "2026-10-13"
        assert request.url.params["end_date"] == "2026-10-19"
        return httpx.Response(200, json=daily_payload(dates))

    weather, _ = client(config, handler)
    assert len(weather.forecast("杭州", days=7)) == 7


@pytest.mark.parametrize("day_count", [3, 4])
def test_short_windows_support_three_and_four_days(config, day_count):
    start = date(2026, 10, 13)
    dates = [start + timedelta(days=offset) for offset in range(day_count)]
    weather, _ = client(
        config,
        lambda request: httpx.Response(200, json=daily_payload(dates)),
    )

    result = weather.forecast_window("杭州", start_date=start, end_date=dates[-1])

    assert [item.date for item in result] == dates


def test_partial_coverage_rejects_duplicates_invalid_codes_and_out_of_range(config):
    payload = daily_payload(
        ["2026-10-16", "2026-10-14", "2026-10-14", "2026-10-15", "2026-10-13", "2026-11-01"],
        codes=[61, 0, 0, 999, 3, 0],
        lows=[16, 15, 15, 14, 13, 12],
        highs=[21, 24, 24, 20, 22, 20],
    )
    weather, _ = client(config, lambda request: httpx.Response(200, json=payload))

    result = weather.forecast_window(
        "杭州", start_date=date(2026, 10, 13), end_date=date(2026, 10, 16)
    )

    assert [item.date.isoformat() for item in result] == ["2026-10-13", "2026-10-16"]


@pytest.mark.parametrize(
    "payload",
    [
        {"daily": None},
        {"daily": {"time": [], "weather_code": []}},
        daily_payload(["2026-10-13"], lows=[]),
    ],
)
def test_invalid_response_is_sanitized(config, payload):
    weather, _ = client(config, lambda request: httpx.Response(200, json=payload))

    with pytest.raises(WeatherServiceError) as exc_info:
        weather.forecast_window("杭州", start_date=date(2026, 10, 13), end_date=date(2026, 10, 15))

    assert exc_info.value.reason is FailureReason.INVALID_RESPONSE


def test_timeout_and_provider_error_are_classified(config):
    def timeout(request):
        raise httpx.ReadTimeout("secret URL", request=request)

    weather, _ = client(config, timeout)
    with pytest.raises(WeatherServiceError) as timeout_info:
        weather.forecast_window("杭州", start_date=date(2026, 10, 13), end_date=date(2026, 10, 15))
    assert timeout_info.value.reason is FailureReason.TIMEOUT
    assert "secret" not in str(timeout_info.value)

    weather, _ = client(config, lambda request: httpx.Response(400, json={"reason": "secret"}))
    with pytest.raises(WeatherServiceError) as provider_info:
        weather.forecast_window("杭州", start_date=date(2026, 10, 13), end_date=date(2026, 10, 15))
    assert provider_info.value.reason is FailureReason.PROVIDER
    assert "secret" not in str(provider_info.value)


def test_geocoding_failure_degrades_as_weather_error(config):
    geocoder = Geocoder(FailureReason.CONFIGURATION)
    weather, _ = client(
        config, lambda request: pytest.fail("forecast must not run"), geocoder=geocoder
    )

    with pytest.raises(WeatherServiceError) as exc_info:
        weather.forecast_window("杭州", start_date=date(2026, 10, 13), end_date=date(2026, 10, 19))
    assert exc_info.value.reason is FailureReason.CONFIGURATION


@pytest.mark.parametrize(
    "start,end", [(date(2026, 10, 14), date(2026, 10, 13)), (date(2026, 10, 1), date(2026, 10, 8))]
)
def test_invalid_window_never_calls_provider(config, start, end):
    weather, geocoder = client(config, lambda request: pytest.fail("forecast must not run"))

    with pytest.raises(ValueError):
        weather.forecast_window("杭州", start_date=start, end_date=end)
    assert geocoder.calls == []
