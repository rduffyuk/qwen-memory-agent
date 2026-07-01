from __future__ import annotations

import json

from benchmark.baselines import (
    b0_no_memory,
    b1_full_history,
    b2_naive_top_k,
    build_history,
)
from benchmark.generate import synthetic_personas
from benchmark.run import BUDGETS, run
from benchmark.score import score_predictions


def _history() -> list[dict[str, str]]:
    return [
        {"text": "Ryan prefers coffee in the morning.", "subject": "morning_drink"},
        {"text": "Ryan prefers tea in the morning.", "subject": "morning_drink"},
        {"text": "Ryan uses Python for prototypes.", "subject": "language"},
    ]


def test_b0_no_memory_returns_empty() -> None:
    assert b0_no_memory("What does Ryan prefer?", _history(), token_budget=64) == ""


def test_b1_full_history_packs_in_chronological_order_within_budget() -> None:
    history = _history()
    # a tiny budget fits only the first (oldest) item — the naive weakness
    assert b1_full_history("q", history, token_budget=8) == "Ryan prefers coffee in the morning."
    # a large budget keeps everything, still in chronological order
    assert b1_full_history("q", history, token_budget=1000).splitlines() == [
        item["text"] for item in history
    ]


def test_b2_ranks_by_overlap_then_packs_to_budget() -> None:
    history = _history()
    top = b2_naive_top_k("What language does Ryan use for prototypes?", history, token_budget=8)
    assert top == "Ryan uses Python for prototypes."


def test_score_empty_fixtures_returns_zeros() -> None:
    # the scorer's empty-input branch must report zero, not a vacuous perfect score
    assert score_predictions({}, []) == {"recall_accuracy": 0.0, "staleness_rate": 0.0}


def test_run_end_to_end_structure(tmp_path) -> None:
    results_dir = tmp_path / "nested" / "out"

    results = run(results_dir=results_dir)

    assert results["budgets"] == BUDGETS
    written = results_dir / "latest.json"
    assert written.exists()
    # results JSON is committed + diffed, so the file must be a stable dump
    assert written.read_text(encoding="utf-8") == json.dumps(results, indent=2, sort_keys=True)
    for name in ("B0", "B1", "B2", "B3"):
        assert set(results["baselines"][name]) == {str(b) for b in BUDGETS}


def test_run_includes_capability_scores(tmp_path) -> None:
    results = run(results_dir=tmp_path / "out")

    assert set(results["capabilities"]) == {"abstention", "temporal"}
    assert set(results["capabilities"]["abstention"]) == {"B1", "B2", "B3"}
    assert set(results["capabilities"]["temporal"]) == {"B3"}


def test_capability_abstention_rewards_relevance_floor(tmp_path) -> None:
    abstention = run(results_dir=tmp_path / "out")["capabilities"]["abstention"]

    assert abstention["B3"]["abstention_accuracy"] == 1.0
    assert any(abstention[name]["abstention_accuracy"] < 1.0 for name in ("B1", "B2"))


def test_capability_temporal_scores_b3_present_past_separation(tmp_path) -> None:
    temporal = run(results_dir=tmp_path / "out")["capabilities"]["temporal"]

    assert temporal["B3"]["temporal_accuracy"] == 1.0


def test_b3_dominates_recall_and_staleness_at_every_budget(tmp_path) -> None:
    # ours is the only system with perfect recall AND zero staleness at every
    # budget, and is never beaten by a naive baseline on either axis.
    baselines = run(results_dir=tmp_path / "out")["baselines"]
    for budget in (str(b) for b in BUDGETS):
        assert baselines["B3"][budget]["recall_accuracy"] == 1.0
        assert baselines["B3"][budget]["staleness_rate"] == 0.0
        for naive in ("B1", "B2"):
            assert (
                baselines["B3"][budget]["recall_accuracy"]
                >= baselines[naive][budget]["recall_accuracy"]
            )
            assert (
                baselines["B3"][budget]["staleness_rate"]
                <= baselines[naive][budget]["staleness_rate"]
            )


def test_naive_top_k_gets_staler_as_budget_grows(tmp_path) -> None:
    # the supersession thesis: with no notion of "replaced", a bigger budget pulls
    # the retired fact back in, so B2's staleness *rises* with the budget.
    baselines = run(results_dir=tmp_path / "out")["baselines"]
    assert (
        baselines["B2"][str(BUDGETS[-1])]["staleness_rate"]
        > baselines["B2"][str(BUDGETS[0])]["staleness_rate"]
    )


def test_naive_full_history_needs_budget_to_recall(tmp_path) -> None:
    # chronological dumping can't recall the current answer at the smallest budget
    baselines = run(results_dir=tmp_path / "out")["baselines"]
    assert baselines["B1"][str(BUDGETS[0])]["recall_accuracy"] < 1.0


def test_persona_history_exceeds_smallest_budget(tmp_path) -> None:
    # guards the premise of the whole curve: the memory set must not all fit at
    # the smallest budget, or the budget would never force a choice.
    persona = synthetic_personas()[0]
    assert len(build_history(persona)) > 1
