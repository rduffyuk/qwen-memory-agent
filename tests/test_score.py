from __future__ import annotations

from benchmark.score import score_predictions


def test_score_computes_recall_and_staleness_on_fixture() -> None:
    fixtures = [
        {"id": "q1", "expected": "tea", "stale": ["coffee"]},
        {"id": "q2", "expected": "python", "stale": ["ruby"]},
    ]
    predictions = {
        "q1": "Ryan now prefers tea in the morning.",
        "q2": "Ryan used to prefer ruby.",
    }

    scores = score_predictions(predictions, fixtures)

    assert scores["recall_accuracy"] == 0.5
    assert scores["staleness_rate"] == 0.5
