"""Run the deterministic P2-03 retrieval evaluation set."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.knowledge import load_default_knowledge_base

CASES = Path(__file__).resolve().parents[1] / "eval" / "rag_eval_cases.json"
MIN_POSITIVE_HIT_RATE = 0.80
MAX_POLLUTION_RATE = 0.0


def main() -> int:
    knowledge = load_default_knowledge_base()
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    positive_cases = [case for case in cases if case.get("expect_hit", True)]
    hits = 0
    pollution = 0
    returned = 0
    for case in cases:
        results = knowledge.search(case["destination"], case["query"], top_k=3)
        titles = [result.title for result in results]
        expected = set(case["expected"])
        hit = bool(expected.intersection(titles)) if case.get("expect_hit", True) else not results
        hits += int(hit)
        returned += len(results)
        pollution += sum(result.destination != case["destination"] for result in results)
        print(f"{case['id']}: pass={hit} titles={titles}")
    positive_hits = sum(
        bool(
            set(case["expected"]).intersection(
                result.title for result in knowledge.search(case["destination"], case["query"], 3)
            )
        )
        for case in positive_cases
    )
    positive_rate = positive_hits / len(positive_cases) if positive_cases else 0.0
    pollution_rate = pollution / returned if returned else 0.0
    overall_rate = hits / len(cases) if cases else 0.0
    print(f"positive_top_k_hit_rate: {positive_hits}/{len(positive_cases)} ({positive_rate:.1%})")
    print(f"overall_case_pass_rate: {hits}/{len(cases)} ({overall_rate:.1%})")
    print(f"cross_destination_pollution_rate: {pollution}/{returned} ({pollution_rate:.1%})")
    if positive_rate < MIN_POSITIVE_HIT_RATE or pollution_rate > MAX_POLLUTION_RATE:
        print("evaluation_status: FAIL")
        return 1
    print("evaluation_status: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
