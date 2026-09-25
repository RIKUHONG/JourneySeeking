"""FastAPI entry point for the MiliTravel trip-generation API."""

from __future__ import annotations

from uuid import uuid4

from typing import Literal

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .models.schemas import ErrorResponse, Itinerary, TripRequest
from .services.trip_service import TripService, TripServiceError

app = FastAPI(title="MiliTravel API", version="0.1.0", description="Travel planning backend API")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def get_trip_service() -> TripService:
    from .integrations.moma_client import MomaClient
    from .services.itinerary_generator import ItineraryGenerator

    return TripService(ItineraryGenerator(client=MomaClient()))


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    body = ErrorResponse(code="INVALID_TRIP_REQUEST", message="Invalid trip request", request_id=_request_id(request))
    return JSONResponse(status_code=422, content=body.model_dump(mode="json"))


@app.exception_handler(TripServiceError)
async def trip_service_error_handler(request: Request, exc: TripServiceError) -> JSONResponse:
    status = {"MOMA_TIMEOUT": 504, "MOMA_INVALID_RESPONSE": 502, "ITINERARY_VALIDATION_ERROR": 502}.get(exc.code, 500)
    body = ErrorResponse(code=exc.code, message=exc.message, request_id=_request_id(request))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/trip/generate", response_model=Itinerary)
def generate_trip(request: TripRequest, service: TripService = Depends(get_trip_service)) -> Itinerary:
    return service.generate(request)


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
