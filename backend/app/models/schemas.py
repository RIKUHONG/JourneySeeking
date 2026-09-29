"""First-version trip API request and response schemas."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Money = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class TripRequest(BaseModel):
    destination: NonEmptyText
    start_date: date
    end_date: date
    travelers: int = Field(default=1, strict=True, ge=1)
    budget: Money | None = None
    preferences: list[NonEmptyText] = Field(default_factory=list, max_length=10)
    pace: Literal["relaxed", "normal", "intensive"] | None = None
    dietary_preferences: list[NonEmptyText] = Field(default_factory=list, max_length=10)
    hotel_level: Literal["budget", "three_star", "four_star", "five_star", "不指定"] | None = None
    special_notes: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "TripRequest":
        day_count = (self.end_date - self.start_date).days + 1
        if not 3 <= day_count <= 7:
            raise ValueError("行程必须为 3 至 7 天，且结束日期不能早于开始日期")
        return self


class Activity(BaseModel):
    time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    name: NonEmptyText
    description: str
    location: str | None = None
    duration_minutes: int | None = Field(default=None, strict=True, gt=0)
    estimated_cost: Money
    poi_id: str | None = Field(default=None, description="已核实的高德 POI 标识")
    poi_category: Literal["spot", "meal", "hotel"] | None = None
    address: str | None = Field(default=None, description="已核实 POI 地址")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    poi_status: Literal["not_attempted", "verified", "not_found", "ambiguous", "unavailable"] = (
        "not_attempted"
    )
    map_source: str | None = Field(default=None, description="地图数据来源")
    route_from_previous: "RouteInfo | None" = None
    route_status: Literal["not_attempted", "verified", "missing_coordinates", "unavailable"] = (
        "not_attempted"
    )


class RouteInfo(BaseModel):
    """相邻活动之间由地图服务返回的路线估算。"""

    mode: Literal["driving", "walking"]
    distance_meters: int = Field(ge=0)
    duration_seconds: int = Field(ge=0)
    source: str = "amap"


class WeatherInfo(BaseModel):
    """按行程日期对齐的天气补充信息。

    ``unknown`` 只表示该日期没有可用预报（例如超过供应商的四天范围），
    不应被解释为晴天或其他具体天气。天气服务整体失败时，调用方应保留
    基础行程并将 ``DayPlan.weather`` 留为 ``None``。
    """

    status: Literal["available", "unknown"] = "available"
    condition: NonEmptyText | None = None
    low_celsius: float | None = Field(default=None, allow_inf_nan=False)
    high_celsius: float | None = Field(default=None, allow_inf_nan=False)
    source: NonEmptyText | None = None
    fetched_at: str | None = None


class DayPlan(BaseModel):
    date: date
    title: NonEmptyText
    activities: list[Activity]
    weather: WeatherInfo | None = Field(default=None, description="按 date 对齐的可选天气")
    weather_advice: list[NonEmptyText] = Field(
        default_factory=list, description="天气相关的轻量提示，不改变活动安排"
    )


class Itinerary(BaseModel):
    destination: NonEmptyText
    start_date: date
    end_date: date
    summary: NonEmptyText
    days: list[DayPlan] = Field(min_length=1)
    total_estimated_cost: Money
    map_enrichment_status: Literal["not_attempted", "completed", "partial", "unavailable"] = (
        "not_attempted"
    )


class ErrorResponse(BaseModel):
    code: NonEmptyText
    message: NonEmptyText
    request_id: NonEmptyText
