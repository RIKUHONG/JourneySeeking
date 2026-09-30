"""Run the deterministic P2-03 retrieval evaluation set.

Usage: python -m backend.scripts.evaluate_rag
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.knowledge import load_default_knowledge_base

CASES = Path(__file__).resolve().parents[1] / "eval" / "rag_eval_cases.json"


def main() -> int:
    knowledge = load_default_knowledge_base()
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    hits = 0
    pollution = 0
    for case in cases:
        results = knowledge.search(case["destination"], case["query"], top_k=3)
        titles = [result.title for result in results]
        expected = set(case["expected"])
        hit = bool(expected.intersection(titles))
        hits += int(hit)
        pollution += sum(result.destination != case["destination"] for result in results)
        print(f"{case['id']}: hit={hit} titles={titles}")
    total = len(cases)
    print(f"top_k_hit_rate: {hits}/{total} ({hits / total * 100:.1f}%)")
    print(f"cross_destination_pollution: {pollution}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
