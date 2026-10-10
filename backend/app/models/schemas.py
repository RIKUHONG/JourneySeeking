"""First-version trip API request and response schemas."""

from datetime import date
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Money = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class ErrorCode(str, Enum):
    """Stable error codes exposed by the HTTP API."""

    INVALID_TRIP_REQUEST = "INVALID_TRIP_REQUEST"
    MOMA_TIMEOUT = "MOMA_TIMEOUT"
    MOMA_INVALID_RESPONSE = "MOMA_INVALID_RESPONSE"
    ITINERARY_VALIDATION_ERROR = "ITINERARY_VALIDATION_ERROR"
    TRIP_NOT_FOUND = "TRIP_NOT_FOUND"
    TRIP_VERSION_CONFLICT = "TRIP_VERSION_CONFLICT"
    INVALID_TRIP_VERSION = "INVALID_TRIP_VERSION"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    SESSION_TRIP_MISMATCH = "SESSION_TRIP_MISMATCH"
    SESSION_VERSION_CONFLICT = "SESSION_VERSION_CONFLICT"


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

    # Required when weather is present so API serialization cannot omit the
    # provider coverage state as a default value.
    status: Literal["available", "unknown"]
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
    # These fields are optional for backward compatibility with the original
    # generate response. Save and versioned-operation models require them.
    trip_id: NonEmptyText | None = None
    version: int | None = Field(default=None, strict=True, ge=1)
    destination: NonEmptyText
    start_date: date
    end_date: date
    summary: NonEmptyText
    days: list[DayPlan] = Field(min_length=1)
    total_estimated_cost: Money
    map_enrichment_status: Literal["not_attempted", "completed", "partial", "unavailable"] = (
        "not_attempted"
    )

    @model_validator(mode="after")
    def validate_identity_pair(self) -> "Itinerary":
        if (self.trip_id is None) != (self.version is None):
            raise ValueError("trip_id 和 version 必须同时提供或同时省略")
        return self


class ErrorResponse(BaseModel):
    code: ErrorCode
    message: NonEmptyText
    request_id: NonEmptyText


class TripSaveRequest(BaseModel):
    """保存完整行程或创建一个新的行程版本。"""

    itinerary: Itinerary
    expected_version: int | None = Field(default=None, strict=True, ge=1)

    @model_validator(mode="after")
    def require_identity_for_save(self) -> "TripSaveRequest":
        has_identity = self.itinerary.trip_id is not None
        if has_identity != (self.expected_version is not None):
            raise ValueError("已有行程必须提供 expected_version，新行程不能提供 expected_version")
        if self.itinerary.version is not None and self.itinerary.version != self.expected_version:
            raise ValueError("行程版本与 expected_version 不一致")
        return self


class TripSummary(BaseModel):
    """历史列表中的有界摘要。"""

    trip_id: NonEmptyText
    version: int = Field(strict=True, ge=1)
    destination: NonEmptyText
    summary: NonEmptyText
    start_date: date
    end_date: date


class TripListResponse(BaseModel):
    items: list[TripSummary]
    next_cursor: NonEmptyText | None = None


class TripListQuery(BaseModel):
    limit: int = Field(default=20, strict=True, ge=1, le=100)
    cursor: NonEmptyText | None = None


class TripVersionSummary(BaseModel):
    trip_id: NonEmptyText
    version: int = Field(strict=True, ge=1)
    created_at: str
    summary: NonEmptyText


class TripVersionsResponse(BaseModel):
    trip_id: NonEmptyText
    current_version: int = Field(strict=True, ge=1)
    items: list[TripVersionSummary]


class TripEditRequest(BaseModel):
    """单日编辑的契约基础；编辑算法由成员 B 实现。"""

    expected_version: int = Field(strict=True, ge=1)
    date: date
    instruction: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]


class TripEditResponse(BaseModel):
    trip_id: NonEmptyText
    version: int = Field(strict=True, ge=1)
    itinerary: Itinerary
    change_summary: list[NonEmptyText] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_response_identity(self) -> "TripEditResponse":
        if self.itinerary.trip_id != self.trip_id or self.itinerary.version != self.version:
            raise ValueError("编辑响应的行程身份与版本不一致")
        return self


class SessionTurn(BaseModel):
    """A bounded, sanitized record of one session edit attempt."""

    turn_id: NonEmptyText
    instruction: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    target_date: date
    base_version: int = Field(strict=True, ge=1)
    result_version: int | None = Field(default=None, strict=True, ge=1)
    status: Literal["succeeded", "failed", "conflict"]
    change_summary: list[NonEmptyText] = Field(default_factory=list, max_length=20)
    created_at: NonEmptyText


class SessionConstraints(BaseModel):
    """Optional immutable snapshot of the original planning constraints."""

    travelers: int | None = Field(default=None, strict=True, ge=1)
    budget: Money | None = None
    preferences: list[NonEmptyText] = Field(default_factory=list, max_length=10)
    pace: Literal["relaxed", "normal", "intensive"] | None = None
    dietary_preferences: list[NonEmptyText] = Field(default_factory=list, max_length=10)
    hotel_level: Literal["budget", "three_star", "four_star", "five_star", "不指定"] | None = None
    special_notes: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
        | None
    ) = None


class TripSession(BaseModel):
    session_id: NonEmptyText
    trip_id: NonEmptyText
    current_version: int = Field(strict=True, ge=1)
    initial_version: int = Field(strict=True, ge=1)
    constraints: SessionConstraints = Field(default_factory=SessionConstraints)
    summary: Annotated[str, StringConstraints(max_length=2000)] = ""
    recent_turns: list[SessionTurn] = Field(default_factory=list, max_length=5)
    created_at: NonEmptyText
    updated_at: NonEmptyText
    expires_at: NonEmptyText


class SessionCreateRequest(BaseModel):
    version: int = Field(strict=True, ge=1)
    constraints: SessionConstraints = Field(default_factory=SessionConstraints)


class SessionEditRequest(BaseModel):
    date: date
    instruction: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]


class SessionEditResponse(BaseModel):
    session_id: NonEmptyText
    trip_id: NonEmptyText
    version: int = Field(strict=True, ge=1)
    itinerary: Itinerary
    change_summary: list[NonEmptyText] = Field(default_factory=list)
    session: TripSession

    @model_validator(mode="after")
    def validate_response_identity(self) -> "SessionEditResponse":
        if (
            self.itinerary.trip_id != self.trip_id
            or self.itinerary.version != self.version
            or self.session.session_id != self.session_id
            or self.session.trip_id != self.trip_id
            or self.session.current_version != self.version
        ):
            raise ValueError("会话编辑响应的行程身份与版本不一致")
        return self


class TripExportFormat(str, Enum):
    MARKDOWN = "markdown"
    PDF = "pdf"


class TripExportQuery(BaseModel):
    version: int | None = Field(default=None, strict=True, ge=1)
    format: TripExportFormat
