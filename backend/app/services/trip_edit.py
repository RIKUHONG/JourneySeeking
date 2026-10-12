"""Constrained single-day itinerary editing and validation."""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Any, ClassVar, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.app.models.schemas import (
    Activity,
    DayPlan,
    Itinerary,
    Money,
    NonEmptyText,
    TripEditRequest,
    TripEditResponse,
    TripRequest,
)
from backend.app.services.image_enrichment import ImageEnrichmentService
from backend.app.services.orchestration import ItineraryCritic
from backend.app.storage import TripVersionConflictError
from backend.app.storage.repository import TripRepository

logger = logging.getLogger(__name__)


class TripEditError(RuntimeError):
    """Stable, public-safe failure raised by the edit boundary."""

    code: ClassVar[str] = "ITINERARY_VALIDATION_ERROR"
    message: ClassVar[str] = "单日编辑未通过校验"

    def __init__(
        self, *, reason: str = "validation_failed", details: list[dict[str, Any]] | None = None
    ) -> None:
        super().__init__(self.message)
        self.reason = reason
        self.details = details or []


class TripEditTimeoutError(TripEditError):
    code = "MOMA_TIMEOUT"
    message = "MoMA 单日编辑请求超时"


class InvalidEditDateError(TripEditError):
    code = "INVALID_TRIP_REQUEST"
    message = "编辑日期不在当前行程中"


class ActivityEditDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    name: NonEmptyText
    description: str
    location: str | None = None
    duration_minutes: int | None = Field(default=None, strict=True, gt=0)
    estimated_cost: Money
    poi_id: str | None = None
    poi_category: Literal["spot", "meal", "hotel"] | None = None


class DayEditDraft(BaseModel):
    """The only shape the model may change."""

    model_config = ConfigDict(extra="forbid")

    date: date
    title: NonEmptyText
    activities: list[ActivityEditDraft]

    def as_day(self, current: DayPlan) -> DayPlan:
        return DayPlan(
            date=self.date,
            title=self.title,
            activities=[Activity.model_validate(item.model_dump()) for item in self.activities],
            weather=current.weather,
            weather_advice=current.weather_advice,
        )


_SERVER_DERIVED_ACTIVITY_FIELDS = frozenset(
    {
        "image_url",
        "address",
        "latitude",
        "longitude",
        "poi_status",
        "map_source",
        "route_from_previous",
        "route_status",
    }
)


class DayEditor(Protocol):
    def edit(
        self,
        itinerary: Itinerary,
        day: DayPlan,
        instruction: str,
        *,
        candidates: Sequence[Any] = (),
        session_context: Sequence[Mapping[str, Any]] = (),
    ) -> Mapping[str, Any] | str: ...


class MomaDayEditor:
    """MoMA adapter that requests one JSON day and exposes no storage concerns."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def edit(
        self,
        itinerary: Itinerary,
        day: DayPlan,
        instruction: str,
        *,
        candidates: Sequence[Any] = (),
        session_context: Sequence[Mapping[str, Any]] = (),
    ) -> str:
        candidate_payload = [
            {
                "poi_id": item.poi_id,
                "name": item.name,
                "category": item.category.value,
                "address": item.address,
            }
            for item in candidates
        ]
        context = {
            "immutable_trip": {
                "destination": itinerary.destination,
                "start_date": itinerary.start_date.isoformat(),
                "end_date": itinerary.end_date.isoformat(),
            },
            "target_day": day.model_dump(mode="json"),
            "instruction": instruction,
            "allowed_pois": candidate_payload,
            "recent_session_context": list(session_context),
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是单日行程编辑器。只返回一个 JSON 对象，且只能包含 date、title、"
                    "activities。不得返回或修改目的地、日期范围、其他日期、天气或总费用。"
                    "有 POI 候选时只能使用 allowed_pois 中的 poi_id。不得输出 Markdown 或解释。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            },
        ]
        try:
            response = self.client.chat(messages)
        except Exception as exc:
            if _is_timeout(exc):
                raise TripEditTimeoutError() from exc
            raise
        content = getattr(response, "content", response)
        if not isinstance(content, str):
            raise TripEditError(reason="editor_response_not_text")
        return content


class TripEditService:
    def __init__(
        self,
        repository: TripRepository,
        editor: DayEditor,
        *,
        candidate_provider: Callable[[str], Any] | None = None,
        critic: ItineraryCritic | None = None,
        image_enricher: ImageEnrichmentService | None = None,
    ) -> None:
        self.repository = repository
        self.editor = editor
        self.candidate_provider = candidate_provider
        self.critic = critic or ItineraryCritic()
        self.image_enricher = image_enricher

    def edit(
        self,
        trip_id: str,
        request: TripEditRequest,
        *,
        session_context: Sequence[Mapping[str, Any]] = (),
    ) -> TripEditResponse:
        current = self.repository.get_current(trip_id)
        if current.version != request.expected_version:
            raise TripVersionConflictError(trip_id)
        target_index = next(
            (index for index, day in enumerate(current.days) if day.date == request.date), None
        )
        if target_index is None:
            raise InvalidEditDateError()

        candidates = self._candidates(current.destination)
        raw_draft = self.editor.edit(
            current,
            current.days[target_index],
            request.instruction,
            candidates=candidates,
            session_context=session_context,
        )
        draft = self._parse_draft(raw_draft)
        if draft.date != request.date:
            raise TripEditError(reason="draft_date_mismatch")

        try:
            edited_day = draft.as_day(current.days[target_index])
        except ValidationError as exc:
            raise TripEditError(reason="draft_schema_invalid") from exc
        trusted_ids = self._trusted_ids(current, candidates)
        self._validate_pois(current.days[target_index], edited_day, trusted_ids)
        self._hydrate_pois(current, edited_day, candidates)

        updated = current.model_copy(deep=True)
        updated.days[target_index] = edited_day
        self._validate_unique_pois(updated)
        old_cost = math.fsum(item.estimated_cost for item in current.days[target_index].activities)
        new_cost = math.fsum(item.estimated_cost for item in edited_day.activities)
        updated.total_estimated_cost = max(0.0, current.total_estimated_cost - old_cost + new_cost)

        self._validate_scope(current, updated, target_index)
        critic_request = TripRequest(
            destination=current.destination,
            start_date=current.start_date,
            end_date=current.end_date,
        )
        report = self.critic.review(critic_request, updated, trusted_poi_ids=trusted_ids or None)
        if not report.accepted:
            raise TripEditError(reason="critic_rejected")

        if self.image_enricher is not None:
            used_urls = {
                activity.image_url
                for index, day in enumerate(updated.days)
                if index != target_index
                for activity in day.activities
                if activity.image_url
            }
            self.image_enricher.enrich_day(edited_day, used_urls=used_urls)

        saved = self.repository.save_version(updated, expected_version=request.expected_version)
        return TripEditResponse(
            trip_id=trip_id,
            version=saved.version,
            itinerary=saved,
            change_summary=self._change_summary(current.days[target_index], edited_day),
        )

    def _candidates(self, destination: str) -> tuple[Any, ...]:
        if self.candidate_provider is None:
            return ()
        pool = self.candidate_provider(destination)
        if not getattr(pool, "meets_minimum", False):
            return ()
        return tuple(pool.candidates)

    @staticmethod
    def _parse_draft(raw: Mapping[str, Any] | str) -> DayEditDraft:
        try:
            payload = json.loads(_extract_json_object(raw)) if isinstance(raw, str) else dict(raw)
            payload = _normalize_edit_payload(payload)
            return DayEditDraft.model_validate(payload)
        except ValidationError as exc:
            if isinstance(raw, str):
                logger.debug(
                    "MoMA day edit response schema rejected chars=%d preview=%r",
                    len(raw),
                    raw[:500],
                )
            details = [
                {"loc": error.get("loc"), "type": error.get("type")} for error in exc.errors()
            ]
            raise TripEditError(reason="draft_schema_invalid", details=details) from exc
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            if isinstance(raw, str):
                logger.debug(
                    "MoMA day edit response parse rejected chars=%d preview=%r",
                    len(raw),
                    raw[:500],
                )
            raise TripEditError(reason="draft_parse_failed") from exc

    @staticmethod
    def _trusted_ids(current: Itinerary, candidates: Sequence[Any]) -> set[str]:
        return {item.poi_id for item in candidates} | {
            activity.poi_id
            for day in current.days
            for activity in day.activities
            if activity.poi_id is not None and activity.poi_status == "verified"
        }

    @staticmethod
    def _validate_pois(before: DayPlan, after: DayPlan, trusted_ids: set[str]) -> None:
        existing_unverified = {
            (item.name, item.poi_id) for item in before.activities if item.poi_status != "verified"
        }
        for activity in after.activities:
            if activity.poi_id is not None and activity.poi_id not in trusted_ids:
                raise TripEditError(reason="untrusted_poi")
            if activity.poi_id is None and (activity.name, None) not in existing_unverified:
                raise TripEditError(reason="new_activity_without_trusted_poi")

    @staticmethod
    def _hydrate_pois(current: Itinerary, day: DayPlan, candidates: Sequence[Any]) -> None:
        by_id = {item.poi_id: item for item in candidates}
        existing = {
            item.poi_id: item
            for current_day in current.days
            for item in current_day.activities
            if item.poi_id is not None and item.poi_status == "verified"
        }
        for activity in day.activities:
            candidate = by_id.get(activity.poi_id)
            prior = existing.get(activity.poi_id)
            if candidate is None and prior is None:
                continue
            if candidate is not None:
                activity.name = candidate.name
                activity.poi_category = candidate.category.value
                activity.location = candidate.address or activity.location
                activity.address = candidate.address or None
                activity.latitude = candidate.latitude
                activity.longitude = candidate.longitude
            else:
                activity.name = prior.name
                activity.poi_category = prior.poi_category
                activity.location = prior.location
                activity.address = prior.address
                activity.latitude = prior.latitude
                activity.longitude = prior.longitude
            activity.poi_status = "verified"
            activity.map_source = "amap"
            if prior is not None:
                activity.image_url = prior.image_url
            activity.route_from_previous = None
            activity.route_status = "not_attempted"

    @staticmethod
    def _validate_scope(before: Itinerary, after: Itinerary, target_index: int) -> None:
        immutable = ("trip_id", "version", "destination", "start_date", "end_date", "summary")
        if any(getattr(before, field) != getattr(after, field) for field in immutable):
            raise TripEditError(reason="immutable_scope_changed")
        for index, day in enumerate(before.days):
            if index != target_index and day != after.days[index]:
                raise TripEditError(reason="other_day_changed")

    @staticmethod
    def _change_summary(before: DayPlan, after: DayPlan) -> list[str]:
        changes: list[str] = []
        if before.title != after.title:
            changes.append(f"更新 {after.date.isoformat()} 标题")
        delta = len(after.activities) - len(before.activities)
        if delta:
            changes.append(f"活动数量{'增加' if delta > 0 else '减少'} {abs(delta)} 项")
        before_cost = math.fsum(item.estimated_cost for item in before.activities)
        after_cost = math.fsum(item.estimated_cost for item in after.activities)
        if not math.isclose(before_cost, after_cost, abs_tol=1e-9):
            changes.append(f"当日预计费用由 {before_cost:g} 调整为 {after_cost:g}")
        if not changes:
            changes.append(f"更新 {after.date.isoformat()} 的活动安排")
        return changes

    @staticmethod
    def _validate_unique_pois(itinerary: Itinerary) -> None:
        ids = [
            activity.poi_id
            for day in itinerary.days
            for activity in day.activities
            if activity.poi_id is not None
        ]
        if len(ids) != len(set(ids)):
            raise TripEditError(reason="duplicate_poi")


def _is_timeout(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return (
        isinstance(exc, TimeoutError) or "timeout" in text or "timed out" in text or "超时" in text
    )


def _extract_json_object(raw: str) -> str:
    """Extract one JSON object while leaving schema validation to the caller."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].lstrip()

    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            _, end_index = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        return text[index : index + end_index]
    raise json.JSONDecodeError("No JSON object found", text, 0)


def _normalize_edit_payload(payload: Any) -> Any:
    """Remove server-derived activity fields echoed from the target-day context."""
    if not isinstance(payload, dict):
        return payload
    activities = payload.get("activities")
    if not isinstance(activities, list):
        return payload
    normalized = dict(payload)
    normalized["activities"] = [
        {
            key: value
            for key, value in activity.items()
            if key not in _SERVER_DERIVED_ACTIVITY_FIELDS
        }
        if isinstance(activity, dict)
        else activity
        for activity in activities
    ]
    return normalized
