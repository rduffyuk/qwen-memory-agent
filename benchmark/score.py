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


def score_abstention(
    predictions: Mapping[str, str],
    fixtures: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    total = len(fixtures)
    if total == 0:
        return {"abstention_accuracy": 0.0}

    correct = 0
    for fixture in fixtures:
        prediction = predictions.get(str(fixture["id"]), "").casefold()
        forbidden = [str(value).casefold() for value in fixture["must_not_contain"]]
        if not any(value in prediction for value in forbidden):
            correct += 1

    return {"abstention_accuracy": correct / total}


def score_temporal(
    present_pred: str,
    past_pred: str,
    present_fixture: Mapping[str, Any],
    past_fixture: Mapping[str, Any],
) -> dict[str, float]:
    present = present_pred.casefold()
    past = past_pred.casefold()
    present_expected = str(present_fixture["expected"]).casefold()
    present_stale = [str(value).casefold() for value in present_fixture.get("stale", [])]
    past_expected = str(past_fixture["expected"]).casefold()

    present_correct = present_expected in present and not any(
        value in present for value in present_stale
    )
    past_correct = past_expected in past

    return {"temporal_accuracy": (int(present_correct) + int(past_correct)) / 2}
