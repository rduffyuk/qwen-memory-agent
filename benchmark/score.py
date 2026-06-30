from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def score_predictions(
    predictions: Mapping[str, str],
    fixtures: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    total = len(fixtures)
    if total == 0:
        return {"recall_accuracy": 0.0, "staleness_rate": 0.0}

    recalled = 0
    stale = 0
    for fixture in fixtures:
        prediction = predictions.get(str(fixture["id"]), "").casefold()
        expected = str(fixture["expected"]).casefold()
        stale_values = [str(value).casefold() for value in fixture.get("stale", [])]
        if expected in prediction:
            recalled += 1
        if any(value in prediction for value in stale_values):
            stale += 1

    return {
        "recall_accuracy": recalled / total,
        "staleness_rate": stale / total,
    }
