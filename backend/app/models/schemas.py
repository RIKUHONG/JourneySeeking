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


class DayPlan(BaseModel):
    date: date
    title: NonEmptyText
    activities: list[Activity]


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
