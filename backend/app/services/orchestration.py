"""Finite-step trip orchestration and deterministic itinerary criticism."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Any, Protocol

from backend.app.knowledge import KnowledgeChunk
from backend.app.models.schemas import Itinerary, TripRequest
from backend.app.services.city_resolution import resolve_city


class StepStatus(StrEnum):
    SUCCEEDED = "succeeded"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class StepRecord:
    name: str
    status: StepStatus
    duration_ms: float
    source: str
    detail: str | None = None
    failure_category: str | None = None


@dataclass(frozen=True, slots=True)
class CriticFinding:
    code: str
    message: str
    path: str


@dataclass(frozen=True, slots=True)
class CriticReport:
    accepted: bool
    findings: tuple[CriticFinding, ...] = ()


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    itinerary: Itinerary
    trace: tuple[StepRecord, ...]
    critic: CriticReport
    knowledge_chunks: tuple[KnowledgeChunk, ...] = ()


class KnowledgeRetriever(Protocol):
    def search(self, destination: str, query: str, top_k: int = 5) -> list[KnowledgeChunk]: ...


class OrchestrationError(RuntimeError):
    def __init__(self, code: str, message: str, trace: tuple[StepRecord, ...]) -> None:
        super().__init__(message)
        self.code = code
        self.trace = trace


class CriticRejectedError(OrchestrationError):
    def __init__(self, report: CriticReport, trace: tuple[StepRecord, ...]) -> None:
        super().__init__("CRITIC_REJECTED", "行程未通过规则校验", trace)
        self.report = report


class ItineraryCritic:
    """Reject structural, budget, provenance, route, and weather violations."""

    def review(
        self,
        request: TripRequest,
        itinerary: Itinerary,
        *,
        trusted_poi_ids: set[str] | None = None,
    ) -> CriticReport:
        findings: list[CriticFinding] = []
        expected_dates = [
            request.start_date + timedelta(days=offset)
            for offset in range((request.end_date - request.start_date).days + 1)
        ]
        actual_dates = [day.date for day in itinerary.days]
        if itinerary.destination != request.destination:
            findings.append(
                CriticFinding("DESTINATION_MISMATCH", "目的地与请求不一致", "destination")
            )
        if (itinerary.start_date, itinerary.end_date) != (request.start_date, request.end_date):
            findings.append(
                CriticFinding("DATE_RANGE_MISMATCH", "日期范围与请求不一致", "start_date")
            )
        if actual_dates != expected_dates:
            findings.append(CriticFinding("DAY_SEQUENCE_INVALID", "每日日期不连续或不完整", "days"))

        activity_cost = math.fsum(
            activity.estimated_cost for day in itinerary.days for activity in day.activities
        )
        if itinerary.total_estimated_cost + 1e-9 < activity_cost:
            findings.append(
                CriticFinding(
                    "TOTAL_COST_INVALID", "总费用小于活动费用之和", "total_estimated_cost"
                )
            )
        if request.budget is not None and itinerary.total_estimated_cost > request.budget:
            findings.append(
                CriticFinding("BUDGET_EXCEEDED", "行程总费用超过用户预算", "total_estimated_cost")
            )

        for day_index, day in enumerate(itinerary.days):
            previous = None
            if (
                day.weather is not None
                and day.weather.status == "unknown"
                and any(
                    value is not None
                    for value in (
                        day.weather.condition,
                        day.weather.source,
                        day.weather.low_celsius,
                        day.weather.high_celsius,
                    )
                )
            ):
                findings.append(
                    CriticFinding(
                        "UNKNOWN_WEATHER_HAS_FACTS",
                        "未知天气不能包含具体事实",
                        f"days.{day_index}.weather",
                    )
                )
            for activity_index, activity in enumerate(day.activities):
                path = f"days.{day_index}.activities.{activity_index}"
                if activity.poi_status == "verified":
                    reliable = (
                        activity.poi_id is not None
                        and activity.latitude is not None
                        and activity.longitude is not None
                        and activity.map_source == "amap"
                    )
                    if trusted_poi_ids is not None and activity.poi_id not in trusted_poi_ids:
                        reliable = False
                    if not reliable:
                        findings.append(
                            CriticFinding("POI_SOURCE_INVALID", "已核实 POI 缺少可信来源", path)
                        )
                if activity.route_status == "verified":
                    route_valid = (
                        previous is not None
                        and previous.latitude is not None
                        and previous.longitude is not None
                        and activity.latitude is not None
                        and activity.longitude is not None
                        and activity.route_from_previous is not None
                        and activity.route_from_previous.source == "amap"
                    )
                    if not route_valid:
                        findings.append(
                            CriticFinding(
                                "ROUTE_SOURCE_INVALID", "已核实路线缺少可靠坐标或来源", path
                            )
                        )
                previous = activity
        return CriticReport(accepted=not findings, findings=tuple(findings))


class TripOrchestrator:
    """Run a bounded, observable planning pipeline with graceful optional-tool fallback."""

    def __init__(
        self,
        trip_service: Any,
        *,
        knowledge: KnowledgeRetriever | None = None,
        critic: ItineraryCritic | None = None,
        max_steps: int = 8,
        step_timeout_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_steps < 1 or step_timeout_seconds <= 0:
            raise ValueError("max_steps 和 step_timeout_seconds 必须为正数")
        self.trip_service = trip_service
        self.knowledge = knowledge
        self.critic = critic or ItineraryCritic()
        self.max_steps = max_steps
        self.step_timeout_seconds = step_timeout_seconds
        self.clock = clock

    def run(self, request: TripRequest, *, top_k: int = 5) -> OrchestrationResult:
        trace: list[StepRecord] = []
        resolution = self._step(
            trace, "city_resolution", "local_rules", lambda: resolve_city(request.destination)
        )
        query = (
            " ".join(
                [
                    *request.preferences,
                    *(request.dietary_preferences),
                    request.special_notes or "",
                    request.pace or "",
                ]
            ).strip()
            or request.destination
        )
        chunks: tuple[KnowledgeChunk, ...] = ()
        if self.knowledge is None:
            self._record_degraded(trace, "knowledge_retrieval", "knowledge_base", "not_configured")
        elif resolution.status == "insufficient_data":
            self._record_degraded(trace, "knowledge_retrieval", "knowledge_base", "city_ineligible")
        else:
            try:
                chunks = tuple(
                    self._step(
                        trace,
                        "knowledge_retrieval",
                        "curated_knowledge",
                        lambda: self.knowledge.search(resolution.city, query, top_k),
                    )
                )
                if not chunks:
                    trace[-1] = StepRecord(
                        "knowledge_retrieval",
                        StepStatus.DEGRADED,
                        trace[-1].duration_ms,
                        "curated_knowledge",
                        "empty_result",
                        "no_match",
                    )
            except OrchestrationError:
                raise
            except Exception as exc:  # noqa: BLE001 - optional retrieval must degrade safely
                trace.pop()
                self._record_degraded(
                    trace, "knowledge_retrieval", "knowledge_base", type(exc).__name__
                )
                chunks = ()

        itinerary = self._step(
            trace,
            "itinerary_generation",
            "moma_and_candidate_provider",
            lambda: self.trip_service.generate_base(request, knowledge_chunks=chunks),
        )
        diagnostics = getattr(self.trip_service.generator, "last_candidate_diagnostics", None)
        if diagnostics is None or not getattr(diagnostics, "meets_minimum", False):
            reason = getattr(diagnostics, "unavailable_reason", None) or "insufficient_candidates"
            self._record_degraded(trace, "candidate_quality", "map_provider", reason)
        else:
            self._record_success(trace, "candidate_quality", "map_provider", "threshold_met")

        if self.trip_service.map_enricher is None:
            self._record_degraded(trace, "map_enrichment", "map_service", "not_configured")
        else:
            itinerary = self._step(
                trace,
                "map_enrichment",
                "map_service",
                lambda: self.trip_service.enrich_map(itinerary),
            )
            if itinerary.map_enrichment_status in {"partial", "unavailable"}:
                previous = trace[-1]
                trace[-1] = StepRecord(
                    previous.name,
                    StepStatus.DEGRADED,
                    previous.duration_ms,
                    previous.source,
                    itinerary.map_enrichment_status,
                    "partial_result",
                )
        if self.trip_service.weather_enricher is None:
            self._record_degraded(trace, "weather_enrichment", "weather_service", "not_configured")
        else:
            itinerary = self._step(
                trace,
                "weather_enrichment",
                "weather_service",
                lambda: self.trip_service.enrich_weather(itinerary),
            )

        trusted_ids = (
            set(diagnostics.by_id)
            if diagnostics is not None and diagnostics.meets_minimum
            else None
        )
        report = self._step(
            trace,
            "critic",
            "deterministic_rules",
            lambda: self.critic.review(request, itinerary, trusted_poi_ids=trusted_ids),
        )
        if not report.accepted:
            previous = trace[-1]
            trace[-1] = StepRecord(
                previous.name,
                StepStatus.FAILED,
                previous.duration_ms,
                previous.source,
                f"{len(report.findings)} finding(s)",
                "critic_rejected",
            )
            raise CriticRejectedError(report, tuple(trace))
        return OrchestrationResult(itinerary, tuple(trace), report, chunks)

    def _step(
        self, trace: list[StepRecord], name: str, source: str, operation: Callable[[], Any]
    ) -> Any:
        self._ensure_capacity(trace)
        started = self.clock()
        try:
            result = operation()
        except Exception as exc:
            duration = (self.clock() - started) * 1000
            trace.append(
                StepRecord(name, StepStatus.FAILED, duration, source, None, type(exc).__name__)
            )
            raise
        duration = self.clock() - started
        if duration > self.step_timeout_seconds:
            trace.append(
                StepRecord(name, StepStatus.FAILED, duration * 1000, source, None, "timeout")
            )
            raise OrchestrationError("STEP_TIMEOUT", f"步骤 {name} 超时", tuple(trace))
        trace.append(StepRecord(name, StepStatus.SUCCEEDED, duration * 1000, source))
        return result

    def _ensure_capacity(self, trace: list[StepRecord]) -> None:
        if len(trace) >= self.max_steps:
            raise OrchestrationError("MAX_STEPS_EXCEEDED", "编排超过最大步骤数", tuple(trace))

    def _record_degraded(
        self, trace: list[StepRecord], name: str, source: str, reason: str
    ) -> None:
        self._ensure_capacity(trace)
        trace.append(StepRecord(name, StepStatus.DEGRADED, 0.0, source, reason, reason))

    def _record_success(self, trace: list[StepRecord], name: str, source: str, detail: str) -> None:
        self._ensure_capacity(trace)
        trace.append(StepRecord(name, StepStatus.SUCCEEDED, 0.0, source, detail))
