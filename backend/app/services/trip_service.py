"""Validate generated itineraries before returning them from the API."""

import json
import math
from datetime import timedelta
from typing import ClassVar, Protocol

from pydantic import ValidationError

from backend.app.models.schemas import Itinerary, TripRequest


class ItineraryGenerator(Protocol):
    def generate(self, request: TripRequest) -> str: ...


class TripServiceError(Exception):
    code: ClassVar[str]
    message: ClassVar[str]

    def __init__(self) -> None:
        super().__init__(self.message)


class MomaTimeoutError(TripServiceError):
    code = "MOMA_TIMEOUT"
    message = "MoMA 生成行程超时"


class MomaInvalidResponseError(TripServiceError):
    code = "MOMA_INVALID_RESPONSE"
    message = "MoMA 返回的行程不是有效的 JSON 对象"


class ItineraryValidationError(TripServiceError):
    code = "ITINERARY_VALIDATION_ERROR"
    message = "生成的行程未通过结构或业务校验"


class TripService:
    def __init__(self, generator: ItineraryGenerator) -> None:
        self.generator = generator

    def generate(self, request: TripRequest) -> Itinerary:
        try:
            content = self.generator.generate(request)
        except TimeoutError as exc:
            raise MomaTimeoutError() from exc

        if not isinstance(content, str) or not content.strip():
            raise MomaInvalidResponseError()

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise MomaInvalidResponseError() from exc

        required_fields = set(Itinerary.model_fields)
        if not isinstance(payload, dict) or not required_fields.issubset(payload):
            raise MomaInvalidResponseError()

        try:
            itinerary = Itinerary.model_validate(payload)
        except ValidationError as exc:
            raise ItineraryValidationError() from exc

        expected_dates = [
            request.start_date + timedelta(days=offset)
            for offset in range((request.end_date - request.start_date).days + 1)
        ]
        if (
            itinerary.destination != request.destination
            or itinerary.start_date != request.start_date
            or itinerary.end_date != request.end_date
            or [day.date for day in itinerary.days] != expected_dates
        ):
            raise ItineraryValidationError()

        activity_cost = math.fsum(
            activity.estimated_cost for day in itinerary.days for activity in day.activities
        )
        if itinerary.total_estimated_cost < activity_cost and not math.isclose(
            itinerary.total_estimated_cost, activity_cost, rel_tol=0, abs_tol=1e-9
        ):
            raise ItineraryValidationError()

        return itinerary
