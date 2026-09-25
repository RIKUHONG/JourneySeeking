"""FastAPI entry point for the MiliTravel trip-generation API."""

from __future__ import annotations

from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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
