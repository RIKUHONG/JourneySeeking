"""Replay anonymized prompt fixtures through the real graph and validators.

This command checks deterministic contracts. Synthetic responses do not establish
model quality or latency and therefore cannot authorize a default-version switch.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import time
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from backend.app.integrations.contracts import DailyForecast
from backend.app.integrations.mock_moma_client import MockMomaClient, MockMomaResponse
from backend.app.integrations.moma_client import MomaClient
from backend.app.models.schemas import TripRequest
from backend.app.services.itinerary_generator import ItineraryGenerator
from backend.app.services.langgraph_orchestration import LangGraphTripOrchestrator
from backend.app.services.poi_candidates import PoiCandidate, PoiCandidatePool, PoiCategory
from backend.app.services.prompt_builder import PromptBuilder
from backend.app.services.prompt_registry import COMPAT_VERSION, P2_VERSION, TARGET_VERSION
from backend.app.services.trip_service import TripService
from backend.app.services.weather_enrichment import WeatherEnrichmentService

VERSIONS = (P2_VERSION, COMPAT_VERSION, TARGET_VERSION)


class FixtureWeather:
    source = "fixture-weather"

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records

    def forecast_window(self, city: str, *, start_date: date, end_date: date):
        return [
            DailyForecast(
                date=date.fromisoformat(item["date"]),
                condition=item["condition"],
                low_celsius=item["low_celsius"],
                high_celsius=item["high_celsius"],
                source="fixture-weather",
                fetched_at="2026-10-13T00:00:00+00:00",
            )
            for item in self.records
            if start_date <= date.fromisoformat(item["date"]) <= end_date
        ]


def _pool(case: dict[str, Any]) -> PoiCandidatePool | None:
    candidates = tuple(
        PoiCandidate(
            poi_id=item["poi_id"],
            name=item["name"],
            category=PoiCategory(item["category"]),
            address=item.get("address", ""),
            latitude=30.25,
            longitude=120.15,
        )
        for item in case.get("candidates", [])
    )
    if not candidates:
        return None
    return PoiCandidatePool(
        city=case["request"]["destination"],
        candidates=candidates,
        minimum_counts={PoiCategory.SPOT: 1, PoiCategory.MEAL: 0, PoiCategory.HOTEL: 0},
    )


def _load_capture_checkpoint(
    path: Path | None,
    *,
    model: str | None,
    max_tokens: int | None,
    repeats: int,
) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    settings = checkpoint.get("capture_settings", {})
    if (
        checkpoint.get("kind") != "controlled_model_capture"
        or settings.get("model") != model
        or settings.get("max_tokens") != max_tokens
        or settings.get("repeats") != repeats
    ):
        return {}
    return {
        case["id"]: case
        for case in checkpoint.get("cases", [])
        if isinstance(case, dict) and isinstance(case.get("id"), str)
    }


def _has_complete_capture(case: Mapping[str, Any], version: str, model: str | None) -> bool:
    variant = case.get("versions", {}).get(version, {})
    return (
        isinstance(variant, dict)
        and "response" in variant
        and variant.get("model") == model
        and isinstance(variant.get("usage"), dict)
        and isinstance(variant.get("duration_ms"), (int, float))
    )


def _write_capture_checkpoint(path: Path | None, captured: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(captured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def capture_fixture(
    fixtures: dict[str, Any],
    client: Any,
    *,
    repeats: int = 1,
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    """Collect paired responses and checkpoint completed calls locally."""
    if fixtures.get("kind") != "synthetic":
        raise ValueError("only synthetic fixtures may be captured")
    if repeats < 1:
        raise ValueError("repeats must be positive")
    captured = copy.deepcopy(fixtures)
    captured["kind"] = "controlled_model_capture"
    source_cases = captured["cases"]
    captured["cases"] = [
        {
            **copy.deepcopy(case),
            "base_case_id": case["id"],
            "id": f"{case['id']}_r{index + 1}" if repeats > 1 else case["id"],
        }
        for case in source_cases
        for index in range(repeats)
    ]
    configured_model = getattr(getattr(client, "config", None), "moma_model", None)
    captured["capture_settings"] = {
        "model": configured_model,
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": getattr(getattr(client, "config", None), "moma_max_tokens", None),
        "repeats": repeats,
    }
    checkpoint_cases = _load_capture_checkpoint(
        checkpoint_path,
        model=configured_model,
        max_tokens=captured["capture_settings"]["max_tokens"],
        repeats=repeats,
    )
    for case in captured["cases"]:
        request = TripRequest.model_validate(case["request"])
        pool = _pool(case)
        by_date = {item["date"]: item for item in case.get("weather", [])}
        weather_context = {}
        day = request.start_date
        while day <= request.end_date:
            key = day.isoformat()
            item = by_date.get(key)
            weather_context[key] = (
                {"status": "available", **item, "source": "fixture-weather"}
                if item is not None
                else {"status": "unknown"}
            )
            day = date.fromordinal(day.toordinal() + 1)
        chunks = tuple(SimpleNamespace(**item) for item in case.get("knowledge_chunks", []))
        planning_context = {
            "weather_context": weather_context,
            "planning_context_status": {
                "weather": "succeeded" if by_date else "degraded",
                "candidate_pool": "succeeded" if pool is not None else "degraded",
                "knowledge": "succeeded" if chunks else "degraded",
            },
        }
        previous = checkpoint_cases.get(case["id"], {})
        case["versions"] = copy.deepcopy(previous.get("versions", {}))
        for version in VERSIONS:
            if _has_complete_capture(case, version, configured_model):
                print(f"reusing {case['id']} {version}", flush=True)
                continue
            print(f"capturing {case['id']} {version}", flush=True)
            messages = PromptBuilder(version).build_messages(
                request, pool, chunks, planning_context
            )
            started = time.perf_counter()
            response = client.chat(messages)
            usage = getattr(response, "usage", {}) or {}
            case["versions"][version] = {
                "response": getattr(response, "content", response),
                "model": configured_model,
                "usage": {
                    key: value
                    for key, value in usage.items()
                    if key in {"prompt_tokens", "completion_tokens"}
                    and isinstance(value, int)
                    and not isinstance(value, bool)
                    and value >= 0
                },
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            _write_capture_checkpoint(checkpoint_path, captured)
        _write_capture_checkpoint(checkpoint_path, captured)
    return captured


def evaluate_case(case: dict[str, Any], version: str) -> dict[str, Any]:
    request = TripRequest.model_validate(case["request"])
    variant = case.get("versions", {}).get(version, {})
    response = variant["response"] if "response" in variant else case["response"]
    responses = [
        MockMomaResponse(
            content=json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else item,
            usage=variant.get("usage", {"prompt_tokens": 100, "completion_tokens": 200}),
        )
        for item in ([response] + variant.get("repair_responses", []))
    ]
    pool = _pool(case)
    generator = ItineraryGenerator(
        MockMomaClient(responses),
        prompt_builder=PromptBuilder(version),
        candidate_provider=(lambda _: pool) if pool is not None else None,
    )
    orchestrator = LangGraphTripOrchestrator(
        TripService(
            generator,
            weather_enricher=WeatherEnrichmentService(FixtureWeather(case.get("weather", []))),
        ),
        max_repair_attempts=len(variant.get("repair_responses", [])),
    )
    output: dict[str, Any] = {
        "fixture_id": case["id"],
        "prompt_version": version,
        "first_pass": False,
        "final_pass": False,
        "date_budget_valid": False,
        "candidate_hit_rate": None,
        "weather_adapted": None,
        "repair_count": 0,
        "token_count": 0,
        "duration_ms": variant.get("duration_ms"),
        "degraded": [],
        "error_code": None,
    }
    try:
        result = orchestrator.run(request, request_id=f"eval_{case['id']}")
        itinerary = result.itinerary
        output["final_pass"] = result.critic.accepted
        output["date_budget_valid"] = (
            itinerary.start_date == request.start_date
            and itinerary.end_date == request.end_date
            and (request.budget is None or itinerary.total_estimated_cost <= request.budget)
        )
        if pool is not None:
            ids = [item.poi_id for day in itinerary.days for item in day.activities]
            output["candidate_hit_rate"] = (
                sum(poi_id in pool.by_id for poi_id in ids) / len(ids) if ids else 0.0
            )
        expected = case.get("weather_expectation", {})
        if expected:
            output["weather_adapted"] = all(
                any(needle in activity.name for activity in day.activities)
                for day in itinerary.days
                if (needle := expected.get(day.date.isoformat()))
            )
        output["degraded"] = [step.name for step in result.trace if step.status.value == "degraded"]
    except Exception as exc:  # noqa: BLE001 - report stable code, not provider text
        output["error_code"] = getattr(exc, "code", "EVALUATION_ERROR")
    finally:
        trace = orchestrator.replay_trace()
        output["first_pass"] = any(
            step.name == "generate_base_itinerary" and step.status.value == "succeeded"
            for step in trace
        )
        output["repair_count"] = sum(
            record.prompt_key.startswith(("structured_repair/", "critic_repair/"))
            for record in generator.call_records
        )
        output["token_count"] = sum(
            record.prompt_tokens + record.completion_tokens for record in generator.call_records
        )
    return output


def evaluate(fixtures: dict[str, Any]) -> dict[str, Any]:
    cases = fixtures["cases"]
    if not cases:
        raise ValueError("evaluation fixtures must contain at least one case")
    results = [evaluate_case(case, version) for case in cases for version in VERSIONS]
    by_version = {}
    for version in VERSIONS:
        rows = [row for row in results if row["prompt_version"] == version]
        durations = sorted(
            row["duration_ms"] for row in rows if isinstance(row["duration_ms"], (int, float))
        )
        candidate_rates = [
            row["candidate_hit_rate"] for row in rows if row["candidate_hit_rate"] is not None
        ]
        weather_rates = [
            row["weather_adapted"] for row in rows if row["weather_adapted"] is not None
        ]
        by_version[version] = {
            "first_pass_rate": sum(row["first_pass"] for row in rows) / len(rows),
            "final_pass_rate": sum(row["final_pass"] for row in rows) / len(rows),
            "date_budget_rate": sum(row["date_budget_valid"] for row in rows) / len(rows),
            "candidate_hit_rate": sum(candidate_rates) / len(candidate_rates)
            if candidate_rates
            else None,
            "weather_adaptation_rate": sum(weather_rates) / len(weather_rates)
            if weather_rates
            else None,
            "mean_tokens": sum(row["token_count"] for row in rows) / len(rows),
            "p95_duration_ms": durations[math.ceil(0.95 * len(durations)) - 1]
            if durations
            else None,
        }
    model_id = fixtures.get("capture_settings", {}).get("model")
    captured = (
        fixtures.get("kind") == "controlled_model_capture"
        and bool(model_id)
        and all(
            all(
                isinstance(
                    case.get("versions", {}).get(version, {}).get("duration_ms"), (int, float)
                )
                and isinstance(case.get("versions", {}).get(version, {}).get("usage"), dict)
                and "response" in case.get("versions", {}).get(version, {})
                and case.get("versions", {}).get(version, {}).get("model") == model_id
                for version in VERSIONS
            )
            for case in cases
        )
    )
    baseline = by_version[COMPAT_VERSION]
    target = by_version[TARGET_VERSION]
    old = by_version[P2_VERSION]
    release_reasons = []
    distinct_cases = {case.get("base_case_id", case["id"]) for case in cases}
    if not captured or len(cases) < 12 or len(distinct_cases) < 12:
        release_reasons.append("paired_model_samples_missing_or_fewer_than_12_distinct_cases")
    if target["first_pass_rate"] < max(old["first_pass_rate"], baseline["first_pass_rate"]):
        release_reasons.append("first_pass_regression")
    if target["date_budget_rate"] < max(old["date_budget_rate"], baseline["date_budget_rate"]):
        release_reasons.append("date_budget_regression")
    for metric in ("candidate_hit_rate", "weather_adaptation_rate"):
        if baseline[metric] is not None and (
            target[metric] is None or target[metric] < baseline[metric]
        ):
            release_reasons.append(f"{metric}_regression")
    if baseline["mean_tokens"] and target["mean_tokens"] > 1.2 * baseline["mean_tokens"]:
        release_reasons.append("token_budget_exceeded")
    if (
        baseline["p95_duration_ms"] is not None
        and target["p95_duration_ms"] is not None
        and target["p95_duration_ms"] > 1.2 * baseline["p95_duration_ms"]
    ):
        release_reasons.append("p95_latency_exceeded")
    hard_contract_pass = all(
        item["final_pass"]
        and item["date_budget_valid"]
        and item["candidate_hit_rate"] in (None, 1.0)
        and item["weather_adapted"] in (None, True)
        for item in results
        if item["prompt_version"] == TARGET_VERSION
    )
    if not hard_contract_pass:
        release_reasons.append("hard_contract_failed")
    return {
        "fixture_kind": fixtures.get("kind", "synthetic"),
        "case_count": len(cases),
        "distinct_case_count": len(distinct_cases),
        "by_version": by_version,
        "release_gate_pass": not release_reasons,
        "release_gate_reasons": release_reasons,
        "results": results,
        "hard_contract_pass": hard_contract_pass,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("backend/eval/fixtures/p3_03_smoke.json"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--capture-output",
        type=Path,
        help="Call the configured model and save paired responses to a local ignored file",
    )
    parser.add_argument("--capture-repeats", type=int, default=1)
    parser.add_argument("--require-release-gate", action="store_true")
    args = parser.parse_args()
    fixtures = json.loads(args.fixtures.read_text(encoding="utf-8"))
    if args.capture_output:
        capture_root = Path("backend/eval/captures").resolve()
        output_path = args.capture_output.resolve()
        if not output_path.is_relative_to(capture_root):
            print("capture output must be inside backend/eval/captures", file=sys.stderr)
            return 3
        try:
            captured = capture_fixture(
                fixtures,
                MomaClient(),
                repeats=args.capture_repeats,
                checkpoint_path=output_path,
            )
        except Exception as exc:  # noqa: BLE001 - keep provider text out of terminal output
            print(f"capture failed: {type(exc).__name__}", file=sys.stderr)
            return 3
        _write_capture_checkpoint(output_path, captured)
        print(f"captured {len(captured['cases'])} paired cases at {output_path}")
        return 0
    report = evaluate(fixtures)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    if args.require_release_gate:
        return 0 if report["release_gate_pass"] else 2
    return 0 if report["hard_contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
