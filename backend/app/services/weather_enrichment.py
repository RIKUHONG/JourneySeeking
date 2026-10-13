"""Optional weather enrichment and conservative, explainable advice."""

from __future__ import annotations

import logging
import math
from datetime import date

from backend.app.integrations.contracts import DailyForecast, WeatherService
from backend.app.integrations.errors import WeatherServiceError
from backend.app.models.schemas import Itinerary, WeatherInfo

logger = logging.getLogger(__name__)


RAIN_KEYWORDS = ("雨", "雷", "台风", "暴雨", "阵雨", "小雨", "中雨", "大雨")


class WeatherEnrichmentService:
    """Attach forecasts by calendar date without changing itinerary activities."""

    def __init__(self, weather_service: WeatherService) -> None:
        self.weather_service = weather_service

    def enrich(self, itinerary: Itinerary) -> Itinerary:
        day_count = (itinerary.end_date - itinerary.start_date).days + 1
        try:
            if hasattr(self.weather_service, "forecast_window"):
                forecasts = self.weather_service.forecast_window(
                    itinerary.destination,
                    start_date=itinerary.start_date,
                    end_date=itinerary.end_date,
                )
            else:
                forecasts = self.weather_service.forecast(
                    itinerary.destination, days=min(day_count, 7)
                )
        except WeatherServiceError as exc:
            logger.warning("weather enrichment unavailable: %s", getattr(exc, "reason", exc))
            for day in itinerary.days:
                day.weather = WeatherInfo(status="unknown")
                day.weather_advice = []
            return itinerary

        by_date: dict[date, DailyForecast] = {}
        conflicts: set[date] = set()
        for forecast in forecasts:
            if (
                not isinstance(forecast.condition, str)
                or not forecast.condition.strip()
                or not all(
                    math.isfinite(value) for value in (forecast.low_celsius, forecast.high_celsius)
                )
                or forecast.low_celsius > forecast.high_celsius
            ):
                continue
            if forecast.date in by_date:
                conflicts.add(forecast.date)
            else:
                by_date[forecast.date] = forecast
        for day in itinerary.days:
            forecast = None if day.date in conflicts else by_date.get(day.date)
            if forecast is None:
                day.weather = WeatherInfo(status="unknown")
                day.weather_advice = []
                continue
            day.weather = self._weather_info(forecast)
            day.weather_advice = self._advice(forecast)
        return itinerary

    def _weather_info(self, forecast: DailyForecast) -> WeatherInfo:
        return WeatherInfo(
            status="available",
            condition=forecast.condition,
            low_celsius=forecast.low_celsius,
            high_celsius=forecast.high_celsius,
            source=forecast.source or getattr(self.weather_service, "source", None),
            fetched_at=forecast.fetched_at,
        )

    @staticmethod
    def _advice(forecast: DailyForecast) -> list[str]:
        if not any(keyword in forecast.condition for keyword in RAIN_KEYWORDS):
            return []
        return ["建议携带雨具，路面湿滑时注意防滑。"]
