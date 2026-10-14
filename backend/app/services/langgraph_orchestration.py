"""Bounded LangGraph orchestration for the P3 generation pipeline.

The graph owns execution order, bounded repair, and redacted trace records.
Domain services remain responsible for model validation, provider truth, and
SQLite persistence semantics.
"""

from __future__ import annotations

import math
import operator
import time
from collections.abc import Callable, Mapping
from datetime import date, timedelta
from typing import Annotated, Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from backend.app.integrations.contracts import DailyForecast
from backend.app.integrations.errors import WeatherServiceError
from backend.app.models.schemas import Itinerary, TripRequest, WeatherInfo
from backend.app.services.city_resolution import CityCoverageStatus, CityResolution, resolve_city
from backend.app.services.orchestration import (
    CriticFinding,
    CriticRejectedError,
    CriticReport,
    ItineraryCritic,
    OrchestrationError,
    OrchestrationResult,
    StepRecord,
    StepStatus,
)
from backend.app.services.prompt_registry import CRITIC_REPAIR, STRUCTURED_REPAIR
from backend.app.services.trip_service import TripService

GRAPH_VERSION = "trip-generation/v2"
DEFAULT_MAX_REPAIR_ATTEMPTS = 1
DEFAULT_MAX_STEPS = 32


def _merge_status(left: dict[str, str], right: dict[str, str]) -> dict[str, str]:
    merged = dict(left)
    merged.update(right)
    return merged


class GraphState(TypedDict, total=False):
    graph_version: str
    request_id: str
    top_k: int
    request: TripRequest
    city_resolution: CityResolution
    knowledge_chunks: tuple[Any, ...]
    candidate_pool: Any
    weather_context: dict[str, dict[str, Any]]
    planning_context_status: Annotated[dict[str, str], _merge_status]
    planning_context: dict[str, Any]
    itinerary_draft: Itinerary
    repair_attempts: int
    critic_report: CriticReport
    trace: Annotated[list[StepRecord], operator.add]
    error_code: str | None
    error_message: str | None


class _GraphDegraded(Exception):
    def __init__(self, reason: str, updates: dict[str, Any] | None = None) -> None:
        self.reason = reason
        self.updates = updates or {}
        super().__init__(reason)


class _GraphFailure(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        updates: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.updates = updates or {}
        super().__init__(message)


class LangGraphTripOrchestrator:
    """Run the P3 graph while preserving the P2 ``OrchestrationResult`` API."""

    def __init__(
        self,
        trip_service: TripService,
        *,
        knowledge: Any | None = None,
        critic: ItineraryCritic | None = None,
        graph_version: str = GRAPH_VERSION,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_repair_attempts: int = DEFAULT_MAX_REPAIR_ATTEMPTS,
        step_timeout_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_steps < 1 or max_repair_attempts < 0 or step_timeout_seconds <= 0:
            raise ValueError("图的步骤数、修复次数和超时必须满足正数边界")
        self.trip_service = trip_service
        self.knowledge = knowledge
        self.critic = critic or ItineraryCritic()
        self.graph_version = graph_version
        self.max_steps = max_steps
        self.max_repair_attempts = max_repair_attempts
        self.step_timeout_seconds = step_timeout_seconds
        self.clock = clock
        self.last_state: GraphState | None = None
        self.graph = self._build_graph()

    def run(
        self,
        request: TripRequest,
        *,
        top_k: int = 5,
        request_id: str | None = None,
    ) -> OrchestrationResult:
        try:
            validated_request = TripRequest.model_validate(request)
        except Exception as exc:  # pragma: no cover - HTTP validation normally catches this
            raise OrchestrationError("INVALID_TRIP_REQUEST", "旅行请求未通过校验", ()) from exc

        initial: GraphState = {
            "graph_version": self.graph_version,
            "request_id": request_id or f"req_{uuid4().hex}",
            "top_k": top_k,
            "request": validated_request,
            "knowledge_chunks": (),
            "weather_context": {},
            "planning_context_status": {},
            "planning_context": {},
            "repair_attempts": 0,
            "trace": [],
            "error_code": None,
            "error_message": None,
        }
        try:
            result_state = self.graph.invoke(initial, config={"configurable": {"top_k": top_k}})
        finally:
            generator = self.trip_service.generator
            if getattr(generator, "supports_prompt_repair", False):
                generator.last_raw_content = ""
        self.last_state = result_state

        trace = tuple(result_state.get("trace", ()))
        error_code = result_state.get("error_code")
        if error_code:
            if error_code == "CRITIC_REJECTED":
                report = result_state.get("critic_report") or CriticReport(False)
                raise CriticRejectedError(report, trace)
            raise OrchestrationError(
                error_code,
                result_state.get("error_message") or "行程生成失败",
                trace,
            )

        itinerary = result_state.get("itinerary_draft")
        report = result_state.get("critic_report")
        if itinerary is None or report is None:
            raise OrchestrationError("ITINERARY_VALIDATION_ERROR", "图未返回完整行程", trace)
        return OrchestrationResult(
            itinerary=itinerary,
            trace=trace,
            critic=report,
            knowledge_chunks=tuple(result_state.get("knowledge_chunks", ())),
        )

    def replay_trace(self, state: Mapping[str, Any] | None = None) -> tuple[StepRecord, ...]:
        """Return the redacted node path from the supplied or last graph state."""

        source = state or self.last_state or {}
        return tuple(source.get("trace", ()))

    def _build_graph(self):
        builder = StateGraph(GraphState)
        builder.add_node(
            "validate_request", self._wrap("validate_request", "pydantic", self._validate_request)
        )
        builder.add_node(
            "resolve_destination",
            self._wrap("resolve_destination", "local_rules", self._resolve_destination),
        )
        builder.add_node(
            "retrieve_knowledge",
            self._wrap("retrieve_knowledge", "curated_knowledge", self._retrieve_knowledge),
        )
        builder.add_node(
            "search_poi_candidates",
            self._wrap("search_poi_candidates", "map_provider", self._search_poi_candidates),
        )
        builder.add_node(
            "query_weather_7d",
            self._wrap("query_weather_7d", "weather_service", self._query_weather),
        )
        builder.add_node(
            "join_planning_context",
            self._wrap("join_planning_context", "state", self._join_planning_context),
        )
        builder.add_node(
            "generate_base_itinerary",
            self._wrap("generate_base_itinerary", "moma_and_planning_context", self._generate_base),
        )
        builder.add_node(
            "validate_structure",
            self._wrap("validate_structure", "pydantic", self._validate_structure),
        )
        builder.add_node(
            "repair_structured_output",
            self._wrap(
                "repair_structured_output",
                "moma_and_planning_context",
                self._repair_structured_output,
            ),
        )
        builder.add_node(
            "apply_authoritative_weather",
            self._wrap(
                "apply_authoritative_weather", "weather_service", self._apply_authoritative_weather
            ),
        )
        builder.add_node(
            "enrich_map_routes",
            self._wrap("enrich_map_routes", "map_service", self._enrich_map_routes),
        )
        builder.add_node(
            "enrich_images", self._wrap("enrich_images", "image_service", self._enrich_images)
        )
        builder.add_node(
            "critic_review", self._wrap("critic_review", "deterministic_rules", self._critic_review)
        )
        builder.add_node(
            "repair_with_critic_findings",
            self._wrap(
                "repair_with_critic_findings",
                "moma_and_planning_context",
                self._repair_with_critic_findings,
            ),
        )

        builder.add_edge(START, "validate_request")
        builder.add_edge("validate_request", "resolve_destination")
        builder.add_conditional_edges(
            "resolve_destination",
            self._route_after_resolution,
        )
        builder.add_edge("retrieve_knowledge", "join_planning_context")
        builder.add_edge("search_poi_candidates", "join_planning_context")
        builder.add_edge("query_weather_7d", "join_planning_context")
        builder.add_edge("join_planning_context", "generate_base_itinerary")
        builder.add_edge("generate_base_itinerary", "validate_structure")
        builder.add_conditional_edges(
            "validate_structure",
            self._route_after_validation,
            {
                "repair": "repair_structured_output",
                "apply_authoritative_weather": "apply_authoritative_weather",
                "failure": END,
            },
        )
        builder.add_edge("repair_structured_output", "validate_structure")
        builder.add_edge("apply_authoritative_weather", "enrich_map_routes")
        builder.add_edge("enrich_map_routes", "enrich_images")
        builder.add_edge("enrich_images", "critic_review")
        builder.add_conditional_edges(
            "critic_review",
            self._route_after_critic,
            {"repair": "repair_with_critic_findings", "success": END, "failure": END},
        )
        builder.add_edge("repair_with_critic_findings", "validate_structure")
        return builder.compile()

    def _wrap(self, name: str, source: str, operation: Callable[[GraphState], dict[str, Any]]):
        def node(state: GraphState) -> dict[str, Any]:
            if len(state.get("trace", ())) >= self.max_steps:
                return {
                    "error_code": "MAX_STEPS_EXCEEDED",
                    "error_message": "编排超过最大步骤数",
                }
            started = self.clock()
            try:
                updates = operation(state)
            except _GraphDegraded as exc:
                return {
                    **exc.updates,
                    "trace": [
                        self._record(
                            name,
                            StepStatus.DEGRADED,
                            source,
                            started,
                            detail=exc.reason,
                            failure_category=exc.reason,
                        )
                    ],
                }
            except _GraphFailure as exc:
                return {
                    **exc.updates,
                    "error_code": exc.code,
                    "error_message": exc.message,
                    "trace": [
                        self._record(
                            name,
                            StepStatus.FAILED,
                            source,
                            started,
                            failure_category=exc.code,
                        )
                    ],
                }
            except Exception as exc:  # noqa: BLE001 - graph boundary redacts provider failures
                return {
                    "error_code": type(exc).__name__,
                    "error_message": "图节点执行失败",
                    "trace": [
                        self._record(
                            name,
                            StepStatus.FAILED,
                            source,
                            started,
                            failure_category=type(exc).__name__,
                        )
                    ],
                }

            record = self._record(name, StepStatus.SUCCEEDED, source, started)
            if record.status is StepStatus.FAILED and record.failure_category == "timeout":
                return {
                    "error_code": "STEP_TIMEOUT",
                    "error_message": f"步骤 {name} 超时",
                    "trace": [record],
                }
            return {**updates, "trace": [record]}

        return node

    def _record(
        self,
        name: str,
        status: StepStatus,
        source: str,
        started: float,
        *,
        detail: str | None = None,
        failure_category: str | None = None,
    ) -> StepRecord:
        duration_ms = (self.clock() - started) * 1000
        if duration_ms > self.step_timeout_seconds * 1000 and status is StepStatus.SUCCEEDED:
            return StepRecord(name, StepStatus.FAILED, duration_ms, source, None, "timeout")
        return StepRecord(name, status, duration_ms, source, detail, failure_category)

    @staticmethod
    def _validate_request(state: GraphState) -> dict[str, Any]:
        TripRequest.model_validate(state["request"])
        return {}

    @staticmethod
    def _resolve_destination(state: GraphState) -> dict[str, Any]:
        return {"city_resolution": resolve_city(state["request"].destination)}

    def _route_after_resolution(self, state: GraphState) -> str | list[str]:
        if state.get("error_code"):
            return END
        return ["retrieve_knowledge", "search_poi_candidates", "query_weather_7d"]

    def _retrieve_knowledge(self, state: GraphState) -> dict[str, Any]:
        resolution = state["city_resolution"]
        if self.knowledge is None:
            raise _GraphDegraded(
                "not_configured",
                {"planning_context_status": {"knowledge": "degraded"}, "knowledge_chunks": ()},
            )
        if resolution.status is CityCoverageStatus.INSUFFICIENT_DATA:
            raise _GraphDegraded(
                "city_ineligible",
                {"planning_context_status": {"knowledge": "degraded"}, "knowledge_chunks": ()},
            )
        request = state["request"]
        query = (
            " ".join(
                [
                    *request.preferences,
                    *request.dietary_preferences,
                    request.special_notes or "",
                    request.pace or "",
                ]
            ).strip()
            or request.destination
        )
        try:
            chunks = tuple(self.knowledge.search(resolution.city, query, self._top_k(state)))
        except Exception as exc:
            raise _GraphDegraded(
                type(exc).__name__,
                {"planning_context_status": {"knowledge": "degraded"}, "knowledge_chunks": ()},
            ) from exc
        if not chunks:
            raise _GraphDegraded(
                "empty_result",
                {"planning_context_status": {"knowledge": "degraded"}, "knowledge_chunks": ()},
            )
        return {"planning_context_status": {"knowledge": "succeeded"}, "knowledge_chunks": chunks}

    @staticmethod
    def _top_k(state: GraphState) -> int:
        # The value is injected through LangGraph config only for future nodes;
        # keeping the graph state independent makes snapshots deterministic.
        return int(state.get("top_k", 5))

    def _search_poi_candidates(self, state: GraphState) -> dict[str, Any]:
        resolution = state["city_resolution"]
        provider = getattr(self.trip_service.generator, "candidate_provider", None)
        if provider is None:
            raise _GraphDegraded(
                "not_configured",
                {"planning_context_status": {"poi": "degraded"}, "candidate_pool": None},
            )
        if resolution.status is CityCoverageStatus.INSUFFICIENT_DATA:
            raise _GraphDegraded(
                "city_ineligible",
                {"planning_context_status": {"poi": "degraded"}, "candidate_pool": None},
            )
        try:
            pool = provider(state["request"])
        except Exception as exc:
            raise _GraphDegraded(
                type(exc).__name__,
                {"planning_context_status": {"poi": "degraded"}, "candidate_pool": None},
            ) from exc
        if pool is None:
            raise _GraphDegraded(
                "empty_result",
                {"planning_context_status": {"poi": "degraded"}, "candidate_pool": None},
            )
        status = "succeeded" if getattr(pool, "meets_minimum", False) else "degraded"
        if status == "degraded":
            raise _GraphDegraded(
                "insufficient_candidates",
                {"planning_context_status": {"poi": "degraded"}, "candidate_pool": pool},
            )
        return {"planning_context_status": {"poi": "succeeded"}, "candidate_pool": pool}

    def _query_weather(self, state: GraphState) -> dict[str, Any]:
        request = state["request"]
        expected_dates = self._expected_dates(request)
        context = {item.isoformat(): {"status": "unknown"} for item in expected_dates}
        enricher = self.trip_service.weather_enricher
        if enricher is None:
            raise _GraphDegraded(
                "not_configured",
                {"planning_context_status": {"weather": "degraded"}, "weather_context": context},
            )
        provider = getattr(enricher, "weather_service", None)
        if provider is None:
            raise _GraphDegraded(
                "not_configured",
                {"planning_context_status": {"weather": "degraded"}, "weather_context": context},
            )
        day_count = len(expected_dates)
        resolution = state.get("city_resolution")
        city = resolution.city if resolution is not None else request.destination
        try:
            if hasattr(provider, "forecast_window"):
                forecasts = provider.forecast_window(
                    city,
                    start_date=request.start_date,
                    end_date=request.end_date,
                )
            else:
                forecasts = provider.forecast(city, days=day_count)
        except Exception as exc:
            reason = (
                exc.reason.value if isinstance(exc, WeatherServiceError) else type(exc).__name__
            )
            raise _GraphDegraded(
                reason,
                {"planning_context_status": {"weather": "degraded"}, "weather_context": context},
            ) from exc

        conflicts: set[str] = set()
        for forecast in forecasts or ():
            if not isinstance(forecast, DailyForecast):
                continue
            key = forecast.date.isoformat()
            if key not in context:
                continue
            if context[key]["status"] == "available":
                conflicts.add(key)
                context[key] = {"status": "unknown"}
                continue
            if key in conflicts:
                continue
            if (
                not isinstance(forecast.condition, str)
                or not forecast.condition.strip()
                or not all(
                    math.isfinite(value) for value in (forecast.low_celsius, forecast.high_celsius)
                )
                or forecast.low_celsius > forecast.high_celsius
            ):
                continue
            context[key] = {
                "status": "available",
                "condition": forecast.condition,
                "low_celsius": forecast.low_celsius,
                "high_celsius": forecast.high_celsius,
                "source": forecast.source or getattr(provider, "source", "weather_service"),
                "fetched_at": forecast.fetched_at,
            }
        has_unknown = any(item["status"] == "unknown" for item in context.values())
        status = "degraded" if has_unknown else "succeeded"
        if has_unknown:
            raise _GraphDegraded(
                "partial_coverage",
                {"planning_context_status": {"weather": status}, "weather_context": context},
            )
        return {"planning_context_status": {"weather": status}, "weather_context": context}

    @staticmethod
    def _expected_dates(request: TripRequest) -> list[date]:
        return [
            request.start_date + timedelta(days=offset)
            for offset in range((request.end_date - request.start_date).days + 1)
        ]

    def _join_planning_context(self, state: GraphState) -> dict[str, Any]:
        return {
            "planning_context": {
                "weather_context": state.get("weather_context", {}),
                "planning_context_status": state.get("planning_context_status", {}),
            }
        }

    def _generate_base(self, state: GraphState) -> dict[str, Any]:
        return self._generate_draft(state)

    def _generate_draft(
        self,
        state: GraphState,
        *,
        repair_kind: str | None = None,
        repair_findings: tuple[dict[str, str], ...] = (),
    ) -> dict[str, Any]:
        generator = self.trip_service.generator
        diagnostics = state.get("candidate_pool")
        trusted_pool = diagnostics if getattr(diagnostics, "meets_minimum", False) else None
        try:
            draft = self.trip_service.generate_base(
                state["request"],
                knowledge_chunks=state.get("knowledge_chunks", ()),
                candidate_pool=trusted_pool,
                candidate_diagnostics=diagnostics,
                planning_context=state.get("planning_context", {}),
                allow_repair=False,
                repair_kind=repair_kind,
                repair_findings=repair_findings,
                repair_failure_code=state.get("error_code") or "ITINERARY_VALIDATION_ERROR",
            )
        except Exception as exc:
            code = getattr(exc, "code", None) or type(exc).__name__
            message = getattr(exc, "message", None) or "基础行程生成失败"
            raise _GraphFailure(code, message) from exc
        # The graph performed candidate search. Prevent map enrichment from
        # consulting a second, implicit provider call and retain diagnostics.
        if diagnostics is not None:
            generator.last_candidate_diagnostics = diagnostics
        return {
            "itinerary_draft": draft,
            "error_code": None,
            "error_message": None,
        }

    def _validate_structure(self, state: GraphState) -> dict[str, Any]:
        if state.get("error_code"):
            return {}
        itinerary = state.get("itinerary_draft")
        if itinerary is None:
            raise _GraphFailure("ITINERARY_VALIDATION_ERROR", "缺少结构化行程草稿")
        try:
            validated = Itinerary.model_validate(itinerary)
            expected_dates = [item.isoformat() for item in self._expected_dates(state["request"])]
            actual_dates = [item.date.isoformat() for item in validated.days]
            if (
                validated.destination != state["request"].destination
                or validated.start_date != state["request"].start_date
                or validated.end_date != state["request"].end_date
                or actual_dates != expected_dates
            ):
                raise ValueError("日期或目的地与请求不一致")
            activity_cost = math.fsum(
                activity.estimated_cost for day in validated.days for activity in day.activities
            )
            if validated.total_estimated_cost + 1e-9 < activity_cost:
                raise ValueError("总费用小于活动费用之和")
            pool = state.get("candidate_pool")
            if getattr(pool, "meets_minimum", False):
                ids = [
                    activity.poi_id
                    for day in validated.days
                    for activity in day.activities
                    if activity.poi_id is not None
                ]
                if len(ids) != sum(len(day.activities) for day in validated.days):
                    raise ValueError("候选模式下活动缺少 POI ID")
                pool.validate_ids(ids)
        except Exception as exc:
            raise _GraphFailure("ITINERARY_VALIDATION_ERROR", "行程未通过结构校验") from exc
        return {"itinerary_draft": validated, "error_code": None, "error_message": None}

    def _route_after_validation(self, state: GraphState) -> str:
        code = state.get("error_code")
        if code is None:
            return "apply_authoritative_weather"
        if (
            code in {"ITINERARY_VALIDATION_ERROR", "MOMA_INVALID_RESPONSE"}
            and state.get("repair_attempts", 0) < self.max_repair_attempts
        ):
            return "repair"
        return "failure"

    def _repair_structured_output(self, state: GraphState) -> dict[str, Any]:
        return self._repair(state, STRUCTURED_REPAIR)

    def _repair_with_critic_findings(self, state: GraphState) -> dict[str, Any]:
        report = state.get("critic_report")
        findings = ()
        if report is not None:
            findings = tuple(
                {
                    "code": finding.code,
                    "path": finding.path,
                    "message": finding.message,
                }
                for finding in report.findings
            )
        planning_context = dict(state.get("planning_context", {}))
        planning_context["critic_findings"] = findings
        return self._repair(
            {**state, "planning_context": planning_context},
            CRITIC_REPAIR,
            findings=findings,
        )

    def _repair(
        self,
        state: GraphState,
        kind: str,
        *,
        findings: tuple[dict[str, str], ...] = (),
    ) -> dict[str, Any]:
        attempts = state.get("repair_attempts", 0) + 1
        try:
            updates = self._generate_draft(state, repair_kind=kind, repair_findings=findings)
        except _GraphFailure as exc:
            raise _GraphFailure(
                exc.code,
                exc.message,
                {**exc.updates, "repair_attempts": attempts},
            ) from exc
        return {**updates, "repair_attempts": attempts}

    def _apply_authoritative_weather(self, state: GraphState) -> dict[str, Any]:
        itinerary = state.get("itinerary_draft")
        if itinerary is None:
            raise _GraphFailure("ITINERARY_VALIDATION_ERROR", "缺少行程草稿")
        context = state.get("weather_context", {})
        updated = itinerary.model_copy(deep=True)
        for day in updated.days:
            evidence = context.get(day.date.isoformat(), {"status": "unknown"})
            if evidence.get("status") != "available":
                day.weather = WeatherInfo(status="unknown")
                day.weather_advice = []
                continue
            day.weather = WeatherInfo(
                status="available",
                condition=evidence["condition"],
                low_celsius=evidence["low_celsius"],
                high_celsius=evidence["high_celsius"],
                source=evidence.get("source"),
                fetched_at=evidence.get("fetched_at"),
            )
            day.weather_advice = self._weather_advice(evidence["condition"])
        return {"itinerary_draft": updated}

    @staticmethod
    def _weather_advice(condition: str) -> list[str]:
        if not any(keyword in condition for keyword in ("雨", "雷", "台风", "暴雨", "阵雨")):
            return []
        return ["建议携带雨具，路面湿滑时注意防滑。"]

    def _enrich_map_routes(self, state: GraphState) -> dict[str, Any]:
        itinerary = state["itinerary_draft"]
        if self.trip_service.map_enricher is None:
            raise _GraphDegraded("not_configured")
        try:
            return {"itinerary_draft": self.trip_service.enrich_map(itinerary)}
        except Exception as exc:
            raise _GraphDegraded(type(exc).__name__) from exc

    def _enrich_images(self, state: GraphState) -> dict[str, Any]:
        itinerary = state["itinerary_draft"]
        if self.trip_service.image_enricher is None:
            raise _GraphDegraded("not_configured")
        try:
            return {"itinerary_draft": self.trip_service.enrich_images(itinerary)}
        except Exception as exc:
            raise _GraphDegraded(type(exc).__name__) from exc

    def _critic_review(self, state: GraphState) -> dict[str, Any]:
        itinerary = state.get("itinerary_draft")
        if itinerary is None:
            raise _GraphFailure("ITINERARY_VALIDATION_ERROR", "缺少行程草稿")
        pool = state.get("candidate_pool")
        trusted_ids = set(pool.by_id) if getattr(pool, "meets_minimum", False) else None
        report = self.critic.review(state["request"], itinerary, trusted_poi_ids=trusted_ids)
        findings = list(report.findings)
        for index, day in enumerate(itinerary.days):
            evidence = state.get("weather_context", {}).get(
                day.date.isoformat(), {"status": "unknown"}
            )
            if evidence.get("status") == "available":
                expected = WeatherInfo(
                    status="available",
                    condition=evidence["condition"],
                    low_celsius=evidence["low_celsius"],
                    high_celsius=evidence["high_celsius"],
                    source=evidence.get("source"),
                    fetched_at=evidence.get("fetched_at"),
                )
            else:
                expected = WeatherInfo(status="unknown")
            if day.weather != expected:
                findings.append(
                    CriticFinding(
                        "WEATHER_EVIDENCE_MISMATCH",
                        "天气字段与同日供应商证据不一致",
                        f"days.{index}.weather",
                    )
                )
        report = CriticReport(accepted=not findings, findings=tuple(findings))
        if not report.accepted:
            marker = getattr(self.trip_service.generator, "mark_validation", None)
            if callable(marker):
                marker("critic_rejected", "CRITIC_REJECTED")
            raise _GraphFailure(
                "CRITIC_REJECTED",
                "行程未通过规则校验",
                {"critic_report": report},
            )
        marker = getattr(self.trip_service.generator, "mark_validation", None)
        if callable(marker):
            marker("accepted")
        return {"critic_report": report, "error_code": None, "error_message": None}

    def _route_after_critic(self, state: GraphState) -> str:
        if state.get("error_code") == "CRITIC_REJECTED":
            if state.get("repair_attempts", 0) < self.max_repair_attempts:
                return "repair"
            return "failure"
        if state.get("error_code"):
            return "failure"
        return "success"
