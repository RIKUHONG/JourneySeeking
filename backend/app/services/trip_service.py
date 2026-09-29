"""Validate generated itineraries before returning them from the API."""

import json
import logging
import math
from datetime import timedelta
from typing import ClassVar, Protocol

from pydantic import ValidationError

from backend.app.models.schemas import Itinerary, TripRequest
from backend.app.services.map_enrichment import MapEnrichmentService
from backend.app.services.weather_enrichment import WeatherEnrichmentService


logger = logging.getLogger(__name__)


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
    def __init__(
        self,
        generator: ItineraryGenerator,
        map_enricher: MapEnrichmentService | None = None,
        weather_enricher: WeatherEnrichmentService | None = None,
    ) -> None:
        self.generator = generator
        self.map_enricher = map_enricher
        self.weather_enricher = weather_enricher

    def generate(self, request: TripRequest) -> Itinerary:
        try:
            content = self.generator.generate(request)
        except TimeoutError as exc:
            raise MomaTimeoutError() from exc
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code == "MOMA_TIMEOUT":
                raise MomaTimeoutError() from exc
            if code == "MOMA_INVALID_RESPONSE":
                raise MomaInvalidResponseError() from exc
            raise

        if not isinstance(content, str) or not content.strip():
            raise MomaInvalidResponseError()

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise MomaInvalidResponseError() from exc

        required_fields = {
            name for name, field in Itinerary.model_fields.items() if field.is_required()
        }
        if not isinstance(payload, dict) or not required_fields.issubset(payload):
            raise MomaInvalidResponseError()

        candidate_pool = getattr(self.generator, "last_candidate_pool", None)
        self._normalize_model_payload(payload, request, candidate_pool)

        try:
            itinerary = Itinerary.model_validate(payload)
        except ValidationError as exc:
            raise ItineraryValidationError() from exc

        if candidate_pool is not None:
            ids = [
                activity.poi_id
                for day in itinerary.days
                for activity in day.activities
                if activity.poi_id is not None
            ]
            if len(ids) != sum(len(day.activities) for day in itinerary.days):
                raise ItineraryValidationError()
            try:
                candidate_pool.validate_ids(ids)
                for day in itinerary.days:
                    for activity in day.activities:
                        candidate = candidate_pool.by_id[activity.poi_id]
                        if activity.poi_category != candidate.category.value:
                            raise ValueError("Planner returned a POI category mismatch")
            except ValueError as exc:
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

        if self.map_enricher is not None:
            itinerary = self.map_enricher.enrich(
                itinerary,
                candidate_pool=candidate_pool,
                require_poi_ids=candidate_pool is not None,
            )
        if self.weather_enricher is not None:
            itinerary = self.weather_enricher.enrich(itinerary)
        return itinerary

    @staticmethod
    def _normalize_model_payload(
        payload: dict[str, object], request: TripRequest, candidate_pool: object | None
    ) -> None:
        """Repair deterministic model drift before validating the base itinerary.

        The request owns its destination; accepting a model-selected destination
        would also query map and weather providers for the wrong city.  In
        candidate mode each POI may be scheduled at most once.  Keeping the first
        occurrence preserves model order while preventing duplicate provider IDs
        from reaching map enrichment.

        This deliberately does not repair dates, costs, unknown IDs, or category
        mismatches because those require model intent rather than request facts.
        """
        if payload.get("destination") != request.destination:
            logger.warning("normalizing generated itinerary destination to request destination")
            payload["destination"] = request.destination

        if candidate_pool is None:
            return

        seen_poi_ids: set[str] = set()
        removed_count = 0
        days = payload.get("days")
        if not isinstance(days, list):
            return

        for day in days:
            if not isinstance(day, dict):
                continue
            activities = day.get("activities")
            if not isinstance(activities, list):
                continue

            unique_activities: list[object] = []
            for activity in activities:
                poi_id = activity.get("poi_id") if isinstance(activity, dict) else None
                if isinstance(poi_id, str) and poi_id in seen_poi_ids:
                    removed_count += 1
                    continue
                if isinstance(poi_id, str):
                    seen_poi_ids.add(poi_id)
                unique_activities.append(activity)
            day["activities"] = unique_activities

        if removed_count:
            logger.warning(
                "removed %d generated activities with duplicate POI IDs", removed_count
            )
