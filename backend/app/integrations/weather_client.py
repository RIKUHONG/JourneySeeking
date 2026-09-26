"""Amap weather forecast adapter with city-name resolution."""

import math
from datetime import date
from typing import Any

import httpx

from ..config.settings import Settings, settings
from ._amap_http import request_amap
from .contracts import DailyForecast
from .errors import FailureReason, WeatherServiceError


class WeatherClient:
    def __init__(self, config: Settings = settings, session: httpx.Client | None = None) -> None:
        self.config = config
        self.session = session

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            self.config.validate_weather()
        except ValueError as exc:
            raise WeatherServiceError(FailureReason.CONFIGURATION) from exc
        return request_amap(
            path,
            params,
            base_url=self.config.weather_base_url,
            api_key=self.config.weather_api_key,
            timeout_seconds=self.config.weather_timeout_seconds,
            max_retries=self.config.weather_max_retries,
            error_type=WeatherServiceError,
            session=self.session,
        )

    def forecast(self, city: str, *, days: int = 3) -> list[DailyForecast]:
        if not city.strip() or not 1 <= days <= 4:
            raise ValueError("Weather forecast requires a city and 1 to 4 days")
        city_code = city.strip()
        if not city_code.isdigit():
            geocodes = self._request("/geocode/geo", {"address": city_code, "city": city_code}).get(
                "geocodes"
            )
            if not isinstance(geocodes, list) or not geocodes:
                raise WeatherServiceError(FailureReason.INVALID_RESPONSE)
            first = geocodes[0]
            if (
                not isinstance(first, dict)
                or not isinstance(first.get("adcode"), str)
                or not first["adcode"]
            ):
                raise WeatherServiceError(FailureReason.INVALID_RESPONSE)
            city_code = first["adcode"]
        payload = self._request("/weather/weatherInfo", {"city": city_code, "extensions": "all"})
        forecasts = payload.get("forecasts")
        if not isinstance(forecasts, list) or not forecasts or not isinstance(forecasts[0], dict):
            raise WeatherServiceError(FailureReason.INVALID_RESPONSE)
        casts = forecasts[0].get("casts")
        if not isinstance(casts, list) or len(casts) < days:
            raise WeatherServiceError(FailureReason.INVALID_RESPONSE)
        result = []
        for cast in casts[:days]:
            try:
                result.append(
                    DailyForecast(
                        date=date.fromisoformat(cast["date"]),
                        condition=cast["dayweather"],
                        low_celsius=float(cast["nighttemp"]),
                        high_celsius=float(cast["daytemp"]),
                    )
                )
                if not isinstance(result[-1].condition, str) or not result[-1].condition:
                    raise ValueError("Invalid weather condition")
                if not all(
                    math.isfinite(value)
                    for value in (result[-1].low_celsius, result[-1].high_celsius)
                ):
                    raise ValueError("Invalid temperature")
            except (KeyError, TypeError, ValueError) as exc:
                raise WeatherServiceError(FailureReason.INVALID_RESPONSE) from exc
        return result
