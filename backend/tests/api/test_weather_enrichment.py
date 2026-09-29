from datetime import date

from backend.app.integrations.contracts import DailyForecast
from backend.app.integrations.errors import FailureReason
from backend.app.integrations.mock_weather_service import MockWeatherService
from backend.app.models.schemas import Activity, DayPlan, Itinerary
from backend.app.services.weather_enrichment import WeatherEnrichmentService


def itinerary(days: int = 5) -> Itinerary:
    start = date(2026, 10, 1)
    return Itinerary(
        destination="杭州",
        start_date=start,
        end_date=start.fromordinal(start.toordinal() + days - 1),
        summary="测试行程",
        days=[
            DayPlan(
                date=start.fromordinal(start.toordinal() + offset),
                title=f"第 {offset + 1} 天",
                activities=[
                    Activity(
                        time="09:00",
                        name="西湖",
                        description="散步",
                        estimated_cost=0,
                    )
                ],
            )
            for offset in range(days)
        ],
        total_estimated_cost=0,
    )


def forecast(day: int, condition: str = "晴") -> DailyForecast:
    return DailyForecast(date=date(2026, 10, day), condition=condition, low_celsius=18, high_celsius=25)


def test_weather_maps_by_date_and_marks_days_after_four_unknown() -> None:
    # Deliberately return records out of order to ensure mapping does not use index.
    service = MockWeatherService(
        forecasts={"杭州": [forecast(3, "小雨"), forecast(1), forecast(2), forecast(4)]}
    )
    result = WeatherEnrichmentService(service).enrich(itinerary())

    assert [day.weather.status for day in result.days] == [
        "available",
        "available",
        "available",
        "available",
        "unknown",
    ]
    assert result.days[0].weather.condition == "晴"
    assert result.days[2].weather.condition == "小雨"
    assert result.days[2].weather_advice == ["建议携带雨具，路面湿滑时注意防滑。"]
    assert result.days[4].activities[0].name == "西湖"


def test_weather_failure_returns_unchanged_base_itinerary(caplog) -> None:
    base = itinerary(3)
    result = WeatherEnrichmentService(
        MockWeatherService(failure=FailureReason.TIMEOUT)
    ).enrich(base)

    assert [day.weather for day in result.days] == [None, None, None]
    assert [day.activities[0].name for day in result.days] == ["西湖"] * 3
    assert "weather enrichment unavailable" in caplog.text
