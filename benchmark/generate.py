from __future__ import annotations

from typing import Any


def synthetic_personas() -> list[dict[str, Any]]:
    return [
        {
            "id": "ryan",
            "sessions": [
                {"text": "Ryan prefers coffee in the morning.", "subject": "morning_drink"},
                {"text": "Ryan likes jazz while coding.", "subject": "music"},
                {"text": "Ryan prefers tea in the morning.", "subject": "morning_drink"},
                {"text": "Ryan uses Python for prototypes.", "subject": "language"},
            ],
            "queries": [
                {
                    "id": "q1",
                    "query": "What morning drink does Ryan prefer?",
                    "expected": "tea",
                    "stale": ["coffee"],
                },
                {
                    "id": "q2",
                    "query": "What language does Ryan use for prototypes?",
                    "expected": "python",
                    "stale": [],
                },
            ],
            "distractors": [
                {"text": "A distractor says Sam likes coffee.", "subject": "sam_drink"},
                {"text": "A distractor says Maya likes Ruby.", "subject": "maya_language"},
            ],
        }
    ]
