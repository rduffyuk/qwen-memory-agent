from __future__ import annotations

from typing import Any


def synthetic_personas() -> list[dict[str, Any]]:
    return [
        {
            "id": "ryan",
            "sessions": [
                {"text": "Ryan drink coffee.", "subject": "drink"},
                {"text": "Ryan music jazz.", "subject": "music"},
                {"text": "Ryan drink tea.", "subject": "drink"},
                {"text": "Ryan language python.", "subject": "language"},
                {"text": "Ryan shell zsh.", "subject": "shell"},
                {"text": "Ryan drink water.", "subject": "drink"},
            ],
            "queries": [
                {
                    "id": "ryan_drink",
                    "query": "Ryan drink",
                    "expected": "water",
                    "stale": ["coffee", "tea"],
                },
                {
                    "id": "ryan_music",
                    "query": "Ryan music",
                    "expected": "jazz",
                    "stale": [],
                },
                {
                    "id": "ryan_language",
                    "query": "Ryan language",
                    "expected": "python",
                    "stale": [],
                },
                {
                    "id": "ryan_shell",
                    "query": "Ryan shell",
                    "expected": "zsh",
                    "stale": [],
                },
            ],
            "distractors": [
                {"text": "Nina drink cola.", "subject": "nina_drink"},
                {"text": "Omar editor emacs.", "subject": "omar_editor"},
                {"text": "Iris snack pear.", "subject": "iris_snack"},
                {"text": "Luca cloud azure.", "subject": "luca_cloud"},
            ],
        },
        {
            "id": "maya",
            "sessions": [
                {"text": "Maya drink soda.", "subject": "drink"},
                {"text": "Maya editor vim.", "subject": "editor"},
                {"text": "Maya snack mango.", "subject": "snack"},
                {"text": "Maya drink matcha.", "subject": "drink"},
                {"text": "Maya framework django.", "subject": "framework"},
            ],
            "queries": [
                {
                    "id": "maya_drink",
                    "query": "Maya drink",
                    "expected": "matcha",
                    "stale": ["soda"],
                },
                {
                    "id": "maya_editor",
                    "query": "Maya editor",
                    "expected": "vim",
                    "stale": [],
                },
                {
                    "id": "maya_snack",
                    "query": "Maya snack",
                    "expected": "mango",
                    "stale": [],
                },
                {
                    "id": "maya_framework",
                    "query": "Maya framework",
                    "expected": "django",
                    "stale": [],
                },
            ],
            "distractors": [
                {"text": "Ryan drink water.", "subject": "ryan_external_drink"},
                {"text": "Noah framework rails.", "subject": "noah_framework"},
                {"text": "Zoe music techno.", "subject": "zoe_music"},
                {"text": "Tara shell fish.", "subject": "tara_shell"},
            ],
        },
        {
            "id": "sam",
            "sessions": [
                {"text": "Sam city paris.", "subject": "city"},
                {"text": "Sam snack almonds.", "subject": "snack"},
                {"text": "Sam city berlin.", "subject": "city"},
                {"text": "Sam theme solarized.", "subject": "theme"},
                {"text": "Sam language go.", "subject": "language"},
            ],
            "queries": [
                {
                    "id": "sam_city",
                    "query": "Sam city",
                    "expected": "berlin",
                    "stale": ["paris"],
                },
                {
                    "id": "sam_snack",
                    "query": "Sam snack",
                    "expected": "almonds",
                    "stale": [],
                },
                {
                    "id": "sam_theme",
                    "query": "Sam theme",
                    "expected": "solarized",
                    "stale": [],
                },
                {
                    "id": "sam_language",
                    "query": "Sam language",
                    "expected": "go",
                    "stale": [],
                },
            ],
            "distractors": [
                {"text": "Maya city madrid.", "subject": "maya_city"},
                {"text": "Ryan snack apple.", "subject": "ryan_snack"},
                {"text": "Leah theme dracula.", "subject": "leah_theme"},
                {"text": "Omar language rust.", "subject": "omar_language"},
            ],
        },
        {
            "id": "priya",
            "sessions": [
                {"text": "Priya commute bus.", "subject": "commute"},
                {"text": "Priya database postgres.", "subject": "database"},
                {"text": "Priya commute bike.", "subject": "commute"},
                {"text": "Priya editor neovim.", "subject": "editor"},
                {"text": "Priya music lofi.", "subject": "music"},
                {"text": "Priya commute train.", "subject": "commute"},
            ],
            "queries": [
                {
                    "id": "priya_commute",
                    "query": "Priya commute",
                    "expected": "train",
                    "stale": ["bus", "bike"],
                },
                {
                    "id": "priya_database",
                    "query": "Priya database",
                    "expected": "postgres",
                    "stale": [],
                },
                {
                    "id": "priya_editor",
                    "query": "Priya editor",
                    "expected": "neovim",
                    "stale": [],
                },
                {
                    "id": "priya_music",
                    "query": "Priya music",
                    "expected": "lofi",
                    "stale": [],
                },
            ],
            "distractors": [
                {"text": "Nina commute ferry.", "subject": "nina_commute"},
                {"text": "Alex database mysql.", "subject": "alex_database"},
                {"text": "Maya editor vim.", "subject": "maya_editor"},
                {"text": "Ryan music jazz.", "subject": "ryan_music"},
            ],
        },
        {
            "id": "alex",
            "sessions": [
                {"text": "Alex cloud aws.", "subject": "cloud"},
                {"text": "Alex language typescript.", "subject": "language"},
                {"text": "Alex cloud aliyun.", "subject": "cloud"},
                {"text": "Alex test pytest.", "subject": "test"},
                {"text": "Alex region singapore.", "subject": "region"},
            ],
            "queries": [
                {
                    "id": "alex_cloud",
                    "query": "Alex cloud",
                    "expected": "aliyun",
                    "stale": ["aws"],
                },
                {
                    "id": "alex_language",
                    "query": "Alex language",
                    "expected": "typescript",
                    "stale": [],
                },
                {
                    "id": "alex_test",
                    "query": "Alex test",
                    "expected": "pytest",
                    "stale": [],
                },
                {
                    "id": "alex_region",
                    "query": "Alex region",
                    "expected": "singapore",
                    "stale": [],
                },
            ],
            "distractors": [
                {"text": "Luca cloud azure.", "subject": "luca_cloud"},
                {"text": "Sam language go.", "subject": "sam_language"},
                {"text": "Iris test jest.", "subject": "iris_test"},
                {"text": "Noah region ireland.", "subject": "noah_region"},
            ],
        },
        {
            "id": "jordan",
            "sessions": [
                {"text": "Jordan breakfast oatmeal.", "subject": "breakfast"},
                {"text": "Jordan timezone utc.", "subject": "timezone"},
                {"text": "Jordan breakfast yogurt.", "subject": "breakfast"},
                {"text": "Jordan shell fish.", "subject": "shell"},
                {"text": "Jordan music ambient.", "subject": "music"},
            ],
            "queries": [
                {
                    "id": "jordan_breakfast",
                    "query": "Jordan breakfast",
                    "expected": "yogurt",
                    "stale": ["oatmeal"],
                },
                {
                    "id": "jordan_timezone",
                    "query": "Jordan timezone",
                    "expected": "utc",
                    "stale": [],
                },
                {
                    "id": "jordan_shell",
                    "query": "Jordan shell",
                    "expected": "fish",
                    "stale": [],
                },
                {
                    "id": "jordan_music",
                    "query": "Jordan music",
                    "expected": "ambient",
                    "stale": [],
                },
            ],
            "distractors": [
                {"text": "Priya breakfast toast.", "subject": "priya_breakfast"},
                {"text": "Ryan timezone pst.", "subject": "ryan_timezone"},
                {"text": "Alex shell bash.", "subject": "alex_shell"},
                {"text": "Maya music techno.", "subject": "maya_music"},
            ],
        },
    ]


def capability_cases() -> dict[str, list[dict[str, Any]]]:
    return {
        "abstention": [
            {
                "id": "weather",
                "query": "What is today's weather forecast?",
                "must_not_contain": [
                    "coffee",
                    "tea",
                    "water",
                    "jazz",
                    "python",
                    "zsh",
                    "cola",
                    "emacs",
                    "pear",
                    "azure",
                ],
            }
        ],
        "temporal": [
            {
                "id": "drink_present",
                "query": "Ryan drink",
                "expected": "water",
                "stale": ["coffee", "tea"],
            },
            {
                "id": "drink_original",
                "query": "Ryan original drink",
                "subject": "drink",
                "expected": "coffee",
            },
        ],
    }
