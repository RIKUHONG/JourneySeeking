"""Offline weather service with caller-supplied deterministic forecasts."""

from collections.abc import Mapping, Sequence
from datetime import date

from .contracts import DailyForecast
from .errors import FailureReason, WeatherServiceError


class MockWeatherService:
    source = "mock-weather"

    def __init__(
        self,
        *,
        forecasts: Mapping[str, Sequence[DailyForecast]] | None = None,
        failure: FailureReason | None = None,
    ) -> None:
        self.forecasts = {city: list(days) for city, days in (forecasts or {}).items()}
        self.failure = failure

    def forecast(self, city: str, *, days: int = 3) -> list[DailyForecast]:
        if self.failure is not None:
            raise WeatherServiceError(self.failure)
        if not city.strip() or not 1 <= days <= 7:
            raise ValueError("Weather forecast requires a city and 1 to 7 days")
        result = self.forecasts.get(city, [])[:days]
        if len(result) < days:
            raise WeatherServiceError(FailureReason.INVALID_RESPONSE)
        return result

    def forecast_window(
        self, city: str, *, start_date: date, end_date: date
    ) -> list[DailyForecast]:
        if self.failure is not None:
            raise WeatherServiceError(self.failure)
        if not city.strip() or not 1 <= (end_date - start_date).days + 1 <= 7:
            raise ValueError("Weather forecast requires a city and 1 to 7 days")
        return [
            forecast
            for forecast in self.forecasts.get(city, ())
            if start_date <= forecast.date <= end_date
        ]
