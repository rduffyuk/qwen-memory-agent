from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from benchmark.baselines import (
    b0_no_memory,
    b1_full_history,
    b2_naive_top_k,
    b3_ours,
    build_history,
)
from benchmark.generate import capability_cases, synthetic_personas
from benchmark.score import score_abstention, score_predictions, score_temporal
from memory_agent.engine import MemoryEngine
from memory_agent.store import MemoryStore

# Small budgets that actually bite: the persona holds ~42 tokens of active
# memory, so at 8 tokens only one memory fits and retrieval must *choose*.
BUDGETS = [8, 16, 32, 64]

# A tiny topical vocabulary shared by memories AND queries, so the fake embedder
# ranks by shared concepts rather than collapsing queries to a zero vector.
_VOCAB = [
    "ryan",
    "sam",
    "maya",
    "morning",
    "drink",
    "coffee",
    "tea",
    "soda",
    "lunch",
    "music",
    "jazz",
    "coding",
    "language",
    "python",
    "ruby",
    "prototypes",
    "prefers",
    "prefer",
    "uses",
    "use",
    "likes",
    "writes",
    "tests",
]


class KeywordQwen:
    """Deterministic, offline bag-of-vocabulary embedder (zero API spend).

    Both memory text and query text map into the same topical space, so cosine
    similarity ranks the *relevant* memory highest — which is what lets the
    budget-constrained retrieval keep the right fact at small budgets.
    """

    def embed(self, text: str) -> list[float]:
        counts = Counter(re.findall(r"[a-z]+", text.lower()))
        return [float(counts[word]) for word in _VOCAB]


def run(results_dir: Path = Path("benchmark/results")) -> dict[str, Any]:
    results_dir.mkdir(parents=True, exist_ok=True)
    personas = synthetic_personas()
    output: dict[str, Any] = {
        "budgets": BUDGETS,
        "baselines": {name: {} for name in ("B0", "B1", "B2", "B3")},
    }

    for budget in BUDGETS:
        for name in ("B0", "B1", "B2", "B3"):
            predictions, fixtures = _evaluate(name, personas, budget=budget)
            output["baselines"][name][str(budget)] = score_predictions(predictions, fixtures)

    output["capabilities"] = _evaluate_capabilities(personas)

    destination = results_dir / "latest.json"
    destination.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return output


def _evaluate(
    name: str,
    personas: list[dict[str, Any]],
    *,
    budget: int,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    predictions: dict[str, str] = {}
    fixtures: list[dict[str, Any]] = []
    for persona in personas:
        history = build_history(persona)
        engine = _build_engine(history, budget=budget) if name == "B3" else None
        for query in persona["queries"]:
            fixtures.append(query)
            predictions[query["id"]] = _predict(name, query["query"], history, engine, budget)
    return predictions, fixtures


def _build_engine(history: list[dict[str, str]], *, budget: int) -> MemoryEngine:
    engine = MemoryEngine(
        qwen=KeywordQwen(),
        store=MemoryStore(location=":memory:"),
        token_budget=budget,
    )
    for item in history:
        engine.write(item["text"], type="preference", subject=item["subject"])
    return engine


def _evaluate_capabilities(personas: list[dict[str, Any]]) -> dict[str, Any]:
    budget = 64
    history = build_history(personas[0])
    cases = capability_cases()
    abstention = cases["abstention"]
    engine = _build_engine(history, budget=budget)

    abstention_predictions = {
        "B1": {
            case["id"]: b1_full_history(case["query"], history, token_budget=budget)
            for case in abstention
        },
        "B2": {
            case["id"]: b2_naive_top_k(case["query"], history, token_budget=budget)
            for case in abstention
        },
        "B3": {
            case["id"]: "\n".join(
                record.text
                for record in engine.retrieve(
                    case["query"],
                    token_budget=budget,
                    min_relevance=0.05,
                )
            )
            for case in abstention
        },
    }

    present_case, past_case = cases["temporal"]
    present_pred = "\n".join(
        record.text for record in engine.retrieve(present_case["query"], token_budget=budget)
    )
    past_pred = "\n".join(record.text for record in engine.history(past_case["subject"]))

    return {
        "abstention": {
            name: score_abstention(predictions, abstention)
            for name, predictions in abstention_predictions.items()
        },
        # B1 full history keeps every fact and can answer historical questions at
        # full token cost. This is a B3 present/past separation score, not a
        # claim that B3 beats B1 on historical recall.
        "temporal": {
            "B3": score_temporal(present_pred, past_pred, present_case, past_case),
        },
    }


def _predict(
    name: str,
    query: str,
    history: list[dict[str, str]],
    engine: MemoryEngine | None,
    budget: int,
) -> str:
    if name == "B0":
        return b0_no_memory(query, history, token_budget=budget)
    if name == "B1":
        return b1_full_history(query, history, token_budget=budget)
    if name == "B2":
        return b2_naive_top_k(query, history, token_budget=budget)
    assert engine is not None
    return b3_ours(query, engine, token_budget=budget)


if __name__ == "__main__":
    run()
