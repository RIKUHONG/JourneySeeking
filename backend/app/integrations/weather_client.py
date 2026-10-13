"""Open-Meteo daily forecasts using city coordinates from the map adapter."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from ..config.settings import Settings, settings
from .amap_client import AmapClient
from .contracts import DailyForecast
from .errors import FailureReason, MapServiceError, WeatherServiceError

WEATHER_SOURCE = "Open-Meteo"

_WEATHER_CODES = {
    0: "晴",
    1: "晴间多云",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    56: "冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "小冻雨",
    67: "大冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "中阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "大阵雪",
    95: "雷阵雨",
    96: "雷雨伴冰雹",
    99: "强雷雨伴冰雹",
}


class WeatherClient:
    source = WEATHER_SOURCE

    def __init__(
        self,
        config: Settings = settings,
        session: httpx.Client | None = None,
        *,
        geocoder: AmapClient | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.config = config
        self.session = session
        self.geocoder = geocoder or AmapClient(config, session)
        self.now = now

    def forecast(self, city: str, *, days: int = 3) -> list[DailyForecast]:
        if not 1 <= days <= 7:
            raise ValueError("Weather forecast requires 1 to 7 days")
        start = self.now().astimezone(ZoneInfo("Asia/Shanghai")).date()
        return self.forecast_window(
            city, start_date=start, end_date=start + timedelta(days=days - 1)
        )

    def forecast_window(
        self, city: str, *, start_date: date, end_date: date
    ) -> list[DailyForecast]:
        if not city.strip() or not 1 <= (end_date - start_date).days + 1 <= 7:
            raise ValueError("Weather forecast requires a city and 1 to 7 days")
        try:
            coordinates = self.geocoder.geocode_city(city)
        except MapServiceError as exc:
            raise WeatherServiceError(exc.reason) from exc
        payload = self._request(
            {
                "latitude": coordinates.latitude,
                "longitude": coordinates.longitude,
                "daily": "weather_code,temperature_2m_min,temperature_2m_max",
                "timezone": "auto",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        )
        return self._parse_daily(payload, start_date, end_date)

    def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            self.config.validate_weather()
        except ValueError as exc:
            raise WeatherServiceError(FailureReason.CONFIGURATION) from exc
        context = nullcontext(self.session) if self.session is not None else httpx.Client()
        with context as client:
            for attempt in range(self.config.weather_max_retries + 1):
                try:
                    response = client.get(
                        f"{self.config.weather_base_url.rstrip('/')}/forecast",
                        params=params,
                        timeout=self.config.weather_timeout_seconds,
                    )
                except httpx.TimeoutException as exc:
                    if attempt == self.config.weather_max_retries:
                        raise WeatherServiceError(FailureReason.TIMEOUT) from exc
                except httpx.RequestError as exc:
                    if attempt == self.config.weather_max_retries:
                        raise WeatherServiceError(FailureReason.NETWORK) from exc
                else:
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt == self.config.weather_max_retries:
                            raise WeatherServiceError(FailureReason.PROVIDER)
                    elif response.status_code != 200:
                        raise WeatherServiceError(FailureReason.PROVIDER)
                    else:
                        try:
                            payload = response.json()
                        except ValueError as exc:
                            raise WeatherServiceError(FailureReason.INVALID_RESPONSE) from exc
                        if not isinstance(payload, dict) or payload.get("error") is True:
                            raise WeatherServiceError(FailureReason.INVALID_RESPONSE)
                        return payload
                time.sleep(2**attempt)
        raise AssertionError("Unreachable: every request attempt returns or raises")

    def _parse_daily(
        self, payload: dict[str, Any], start_date: date, end_date: date
    ) -> list[DailyForecast]:
        daily = payload.get("daily")
        if not isinstance(daily, dict):
            raise WeatherServiceError(FailureReason.INVALID_RESPONSE)
        columns = [
            daily.get("time"),
            daily.get("weather_code"),
            daily.get("temperature_2m_min"),
            daily.get("temperature_2m_max"),
        ]
        if not all(isinstance(column, list) for column in columns):
            raise WeatherServiceError(FailureReason.INVALID_RESPONSE)
        dates, codes, lows, highs = columns
        if not len(dates) == len(codes) == len(lows) == len(highs):
            raise WeatherServiceError(FailureReason.INVALID_RESPONSE)

        fetched_at = self.now().astimezone(UTC).isoformat(timespec="seconds")
        by_date: dict[date, DailyForecast] = {}
        conflicts: set[date] = set()
        for raw_date, code, low, high in zip(dates, codes, lows, highs, strict=True):
            try:
                forecast_date = date.fromisoformat(raw_date)
                low_value, high_value = float(low), float(high)
                if (
                    not isinstance(code, int)
                    or isinstance(code, bool)
                    or code not in _WEATHER_CODES
                    or not math.isfinite(low_value)
                    or not math.isfinite(high_value)
                    or low_value > high_value
                ):
                    continue
            except (TypeError, ValueError):
                continue
            if not start_date <= forecast_date <= end_date:
                continue
            if forecast_date in by_date:
                conflicts.add(forecast_date)
                continue
            by_date[forecast_date] = DailyForecast(
                date=forecast_date,
                condition=_WEATHER_CODES[code],
                low_celsius=low_value,
                high_celsius=high_value,
                source=self.source,
                fetched_at=fetched_at,
            )
        return [by_date[item] for item in sorted(by_date) if item not in conflicts]
