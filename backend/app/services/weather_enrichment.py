"""Optional weather enrichment and conservative, explainable advice."""

from __future__ import annotations

from backend.app.integrations.contracts import DailyForecast, WeatherService
from backend.app.models.schemas import Itinerary, WeatherInfo


RAIN_KEYWORDS = ("雨", "雷", "台风", "暴雨", "阵雨", "小雨", "中雨", "大雨")


class WeatherEnrichmentService:
    """Attach forecasts by calendar date without changing itinerary activities."""

    def __init__(self, weather_service: WeatherService) -> None:
        self.weather_service = weather_service

    def enrich(self, itinerary: Itinerary) -> Itinerary:
        day_count = (itinerary.end_date - itinerary.start_date).days + 1
        try:
            forecasts = self.weather_service.forecast(
                itinerary.destination, days=min(day_count, 4)
            )
        except Exception:
            # Weather is an optional enhancement: preserve the validated base itinerary.
            return itinerary

        by_date = {forecast.date: forecast for forecast in forecasts}
        for day in itinerary.days:
            forecast = by_date.get(day.date)
            if forecast is None:
                day.weather = WeatherInfo(status="unknown")
                day.weather_advice = []
                continue
            day.weather = self._weather_info(forecast)
            day.weather_advice = self._advice(forecast)
        return itinerary

    @staticmethod
    def _weather_info(forecast: DailyForecast) -> WeatherInfo:
        return WeatherInfo(
            status="available",
            condition=forecast.condition,
            low_celsius=forecast.low_celsius,
            high_celsius=forecast.high_celsius,
            source="amap",
        )

    @staticmethod
    def _advice(forecast: DailyForecast) -> list[str]:
        if not any(keyword in forecast.condition for keyword in RAIN_KEYWORDS):
            return []
        return ["建议携带雨具，路面湿滑时注意防滑。"]
