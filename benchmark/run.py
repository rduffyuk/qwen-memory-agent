from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmark.baselines import (
    b0_no_memory,
    b1_full_history,
    b2_naive_top_k,
    b3_ours,
    build_history,
)
from benchmark.generate import synthetic_personas
from benchmark.score import score_predictions
from memory_agent.engine import MemoryEngine
from memory_agent.store import MemoryStore


class KeywordQwen:
    def embed(self, text: str) -> list[float]:
        lowered = text.lower()
        return [
            float(lowered.count("coffee")),
            float(lowered.count("tea")),
            float(lowered.count("jazz")),
            float(lowered.count("python")),
            float(lowered.count("ruby")),
        ]


def run(results_dir: Path = Path("benchmark/results")) -> dict[str, Any]:
    results_dir.mkdir(parents=True, exist_ok=True)
    personas = synthetic_personas()
    budgets = [512, 1000, 2000]
    output: dict[str, Any] = {"budgets": budgets, "baselines": {}}

    for baseline in ["B0", "B1", "B2"]:
        predictions, fixtures = _run_stateless_baseline(baseline, personas)
        output["baselines"][baseline] = score_predictions(predictions, fixtures)

    output["baselines"]["B3"] = {}
    for budget in budgets:
        predictions, fixtures = _run_engine_baseline(personas, budget=budget)
        output["baselines"]["B3"][str(budget)] = score_predictions(predictions, fixtures)

    destination = results_dir / "latest.json"
    destination.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return output


def _run_stateless_baseline(
    baseline: str,
    personas: list[dict[str, Any]],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    predictions: dict[str, str] = {}
    fixtures: list[dict[str, Any]] = []
    for persona in personas:
        history = build_history(persona)
        for query in persona["queries"]:
            fixtures.append(query)
            if baseline == "B0":
                predictions[query["id"]] = b0_no_memory(query["query"], history)
            elif baseline == "B1":
                predictions[query["id"]] = b1_full_history(query["query"], history)
            else:
                predictions[query["id"]] = b2_naive_top_k(query["query"], history)
    return predictions, fixtures


def _run_engine_baseline(
    personas: list[dict[str, Any]],
    *,
    budget: int,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    predictions: dict[str, str] = {}
    fixtures: list[dict[str, Any]] = []
    for persona in personas:
        engine = MemoryEngine(
            qwen=KeywordQwen(),
            store=MemoryStore(location=":memory:"),
            token_budget=budget,
        )
        for item in build_history(persona):
            engine.write(item["text"], type="preference", subject=item["subject"])
        for query in persona["queries"]:
            fixtures.append(query)
            predictions[query["id"]] = b3_ours(query["query"], engine, token_budget=budget)
    return predictions, fixtures


if __name__ == "__main__":
    run()
