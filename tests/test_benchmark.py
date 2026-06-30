from __future__ import annotations

import json

from benchmark.baselines import (
    b0_no_memory,
    b1_full_history,
    b2_naive_top_k,
    build_history,
)
from benchmark.generate import synthetic_personas
from benchmark.run import _run_stateless_baseline, run
from benchmark.score import score_predictions


def test_b0_no_memory_returns_empty() -> None:
    history = [{"text": "Ryan prefers tea.", "subject": "drink"}]

    assert b0_no_memory("What does Ryan prefer?", history) == ""


def test_b1_full_history_joins_all_history_texts() -> None:
    history = [
        {"text": "Ryan prefers tea.", "subject": "drink"},
        {"text": "Ryan likes jazz.", "subject": "music"},
    ]

    assert b1_full_history("What does Ryan prefer?", history) == (
        "Ryan prefers tea.\nRyan likes jazz."
    )


def test_b2_ranks_highest_overlap_first() -> None:
    history = [
        {"text": "Unrelated note about Ruby.", "subject": "language"},
        {"text": "Ryan prefers morning tea.", "subject": "drink"},
        {"text": "Another unrelated note about jazz.", "subject": "music"},
    ]

    assert b2_naive_top_k("morning tea", history, k=1) == "Ryan prefers morning tea."


def test_b2_default_k_caps_result_count() -> None:
    history = [
        {"text": f"Ryan likes tea item {idx}.", "subject": f"drink_{idx}"} for idx in range(5)
    ]

    result = b2_naive_top_k("Ryan likes tea", history)

    assert len(result.splitlines()) == 3


def test_run_end_to_end(tmp_path) -> None:
    results_dir = tmp_path / "nested" / "out"

    results = run(results_dir=results_dir)

    assert results["budgets"] == [512, 1000, 2000]
    written = results_dir / "latest.json"
    assert written.exists()
    # results JSON is committed + diffed, so the file must be a stable (sorted, indented) dump
    assert written.read_text(encoding="utf-8") == json.dumps(results, indent=2, sort_keys=True)
    assert results["baselines"]["B1"]["recall_accuracy"] == 1.0
    assert "B2" in results["baselines"]
    assert set(results["baselines"]["B3"]) == {"512", "1000", "2000"}
    # B3's whole thesis: supersession retires stale facts the naive baselines keep.
    # At every budget B3 must be *strictly* less stale than naive top-k (B2),
    # while still recalling the current answer.
    for budget in ("512", "1000", "2000"):
        assert (
            results["baselines"]["B3"][budget]["staleness_rate"]
            < results["baselines"]["B2"]["staleness_rate"]
        )
        assert results["baselines"]["B3"][budget]["recall_accuracy"] == 1.0


def test_score_empty_fixtures_returns_zeros() -> None:
    # the scorer's empty-input branch must report zero, not a vacuous perfect score
    assert score_predictions({}, []) == {"recall_accuracy": 0.0, "staleness_rate": 0.0}


def test_run_dispatch_routes_b1_and_b2_distinctly() -> None:
    # guards the baseline dispatch: B1 = full history, B2 = top-k — never swapped/conflated
    personas = synthetic_personas()
    b1_preds, _ = _run_stateless_baseline("B1", personas)
    b2_preds, _ = _run_stateless_baseline("B2", personas)

    history_texts = [item["text"] for item in build_history(personas[0])]
    assert len(history_texts) > 3  # fixture must exceed b2's default k for the contrast to hold

    # B1 carries every history line; B2 (top-k) is strictly smaller
    for pred in b1_preds.values():
        for text in history_texts:
            assert text in pred
    for pred in b2_preds.values():
        assert len(pred.splitlines()) <= 3 < len(history_texts)

    assert b1_preds != b2_preds
