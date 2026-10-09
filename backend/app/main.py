"""FastAPI entry point for the MiliTravel trip-generation API."""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .cache import MemoryCache
from .integrations.moma_client import MomaError
from .models.schemas import (
    ErrorCode,
    ErrorResponse,
    Itinerary,
    TripListResponse,
    TripRequest,
    TripSaveRequest,
    TripVersionsResponse,
)
from .services.trip_service import TripService, TripServiceError
from .storage import (
    InvalidTripCursorError,
    SQLiteTripRepository,
    TripNotFoundError,
    TripVersionConflictError,
)

app = FastAPI(title="MiliTravel API", version="0.1.0", description="Travel planning backend API")
_map_cache = MemoryCache(default_ttl_seconds=300)
_trip_repository: SQLiteTripRepository | None = None


def _request_id(request: Request) -> str:
    return (
        getattr(request.state, "request_id", None)
        or request.headers.get("X-Request-ID")
        or f"req_{uuid4().hex}"
    )


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json") and "charset=" not in content_type.lower():
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


def get_trip_service() -> TripService:
    from .config.settings import settings
    from .integrations.amap_client import AmapClient
    from .integrations.moma_client import MomaClient
    from .integrations.weather_client import WeatherClient
    from .services.itinerary_generator import ItineraryGenerator
    from .services.map_enrichment import MapEnrichmentService
    from .services.poi_candidates import collect_candidate_pool
    from .services.weather_enrichment import WeatherEnrichmentService

    map_client = AmapClient(config=settings)
    return TripService(
        ItineraryGenerator(
            client=MomaClient(),
            candidate_provider=lambda request: collect_candidate_pool(
                map_client, request.destination
            ),
        ),
        map_enricher=MapEnrichmentService(map_client, cache=_map_cache),
        weather_enricher=WeatherEnrichmentService(WeatherClient(config=settings)),
    )


def get_trip_repository() -> SQLiteTripRepository:
    global _trip_repository
    if _trip_repository is None:
        from .config.settings import settings

        _trip_repository = SQLiteTripRepository(settings.trip_database_path)
    return _trip_repository


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    error_code = ErrorCode.INVALID_TRIP_REQUEST
    if request.url.path == "/api/trip/save":
        version_error = any(
            any(str(part) in {"version", "expected_version"} for part in error["loc"])
            for error in exc.errors()
        )
        if version_error:
            error_code = ErrorCode.INVALID_TRIP_VERSION
    body = ErrorResponse(
        code=error_code,
        message=(
            "行程版本必须是正整数且与当前行程一致"
            if error_code is ErrorCode.INVALID_TRIP_VERSION
            else "Invalid trip request"
        ),
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=422, content=body.model_dump(mode="json"))


@app.exception_handler(TripServiceError)
async def trip_service_error_handler(request: Request, exc: TripServiceError) -> JSONResponse:
    status = {
        "MOMA_TIMEOUT": 504,
        "MOMA_INVALID_RESPONSE": 502,
        "ITINERARY_VALIDATION_ERROR": 502,
    }.get(exc.code, 500)
    body = ErrorResponse(code=exc.code, message=exc.message, request_id=_request_id(request))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


@app.exception_handler(TripNotFoundError)
async def trip_not_found_handler(request: Request, exc: TripNotFoundError) -> JSONResponse:
    body = ErrorResponse(
        code=ErrorCode.TRIP_NOT_FOUND,
        message="行程或指定版本不存在",
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=404, content=body.model_dump(mode="json"))


@app.exception_handler(TripVersionConflictError)
async def trip_version_conflict_handler(
    request: Request, exc: TripVersionConflictError
) -> JSONResponse:
    body = ErrorResponse(
        code=ErrorCode.TRIP_VERSION_CONFLICT,
        message="行程已被其他请求更新，请重新读取最新版本",
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


@app.exception_handler(InvalidTripCursorError)
async def invalid_trip_cursor_handler(
    request: Request, exc: InvalidTripCursorError
) -> JSONResponse:
    body = ErrorResponse(
        code=ErrorCode.INVALID_TRIP_REQUEST,
        message="分页 cursor 无效",
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=422, content=body.model_dump(mode="json"))


@app.exception_handler(MomaError)
async def chat_provider_error_handler(request: Request, exc: MomaError) -> JSONResponse:
    """Keep raw chat-provider details out of the public response."""

    body = ErrorResponse(
        code=ErrorCode.INTERNAL_SERVER_ERROR,
        message="上游服务暂时不可用",
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=502, content=body.model_dump(mode="json"))


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return the documented shape for unexpected application failures."""

    body = ErrorResponse(
        code=ErrorCode.INTERNAL_SERVER_ERROR,
        message="服务暂时不可用",
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=500, content=body.model_dump(mode="json"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/trip/generate", response_model=Itinerary, response_model_exclude_defaults=True)
def generate_trip(
    request: TripRequest,
    service: TripService = Depends(get_trip_service),  # noqa: B008
) -> Itinerary:
    return service.generate(request)


@app.post("/api/trip/save", response_model=Itinerary)
def save_trip(
    request: TripSaveRequest,
    repository: SQLiteTripRepository = Depends(get_trip_repository),  # noqa: B008
) -> Itinerary:
    if request.itinerary.trip_id is None:
        return repository.create(request.itinerary)
    return repository.save_version(request.itinerary, expected_version=request.expected_version)  # type: ignore[arg-type]


@app.get("/api/trip", response_model=TripListResponse)
def list_trips(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    repository: SQLiteTripRepository = Depends(get_trip_repository),  # noqa: B008
) -> TripListResponse:
    return repository.list(limit=limit, cursor=cursor)


@app.get("/api/trip/{trip_id}", response_model=Itinerary)
def get_trip(
    trip_id: str,
    repository: SQLiteTripRepository = Depends(get_trip_repository),  # noqa: B008
) -> Itinerary:
    return repository.get_current(trip_id)


@app.get("/api/trip/{trip_id}/versions", response_model=TripVersionsResponse)
def list_trip_versions(
    trip_id: str,
    repository: SQLiteTripRepository = Depends(get_trip_repository),  # noqa: B008
) -> TripVersionsResponse:
    return repository.list_versions(trip_id)


@app.get("/api/trip/{trip_id}/versions/{version}", response_model=Itinerary)
def get_trip_version(
    trip_id: str,
    version: int,
    repository: SQLiteTripRepository = Depends(get_trip_repository),  # noqa: B008
) -> Itinerary:
    return repository.get_version(trip_id, version)


@app.delete("/api/trip/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(
    trip_id: str,
    repository: SQLiteTripRepository = Depends(get_trip_repository),  # noqa: B008
) -> Response:
    repository.delete(trip_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=32_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.2, ge=0, le=2)
    top_p: float = Field(default=0.9, gt=0, le=1)


class ChatResponse(BaseModel):
    content: str
    model: str | None = None
    request_id: str | None = None
    usage: dict = Field(default_factory=dict)


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    from .integrations.moma_client import MomaClient

    result = MomaClient().chat(
        [message.model_dump() for message in request.messages],
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
    )
    return ChatResponse(
        content=result.content,
        model=result.model,
        request_id=result.request_id,
        usage=dict(result.usage),
    )
