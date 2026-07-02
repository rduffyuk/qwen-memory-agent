"""Active-use eval: does the agent *use* stored constraints to gate later decisions?

MemoryArena-style (arXiv 2602.16313): passive recall benchmarks saturate while the
same systems drop to 40-60% when a memory written in one session must constrain a
decision made in a later one. Each scenario here seeds constraint(s) across one or
more sessions, then asks for a decision in a FINAL, separate session. A scenario
passes only if three independent checks agree:

  1. outcome  - the decision reflects the constraint (expect_any) and commits no
                violation (must_not),
  2. store    - the constraint is active in the store (and superseded where the
                scenario updated it) - graded on store state, never prose,
  3. process  - the final decision turn actually called `recall` (the agent
                consulted memory rather than guessing right).

Token matching is casefold substring, consistent with benchmark/score.py. must_not
is reserved for tokens a CORRECT answer would essentially never contain (a wrong
dish, a retired budget); constraints a correct answer may legitimately mention
("since you dislike metal...") are graded via expect_any + store checks instead.

Offline-importable: no network at import, no Qwen client. Drive it with any
`chat(message, session_id) -> (answer, tool_calls_made)` callable - scripted fakes
in tests (zero credit), HTTP in scripts/active_use_live.py.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

ChatFn = Callable[[str, str], tuple[str, list[str]]]

# depth = number of stored constraints (or constraint updates) the final decision
# depends on. Every scenario is multi-session: the decision turn NEVER shares a
# session with the seeding turns.
SCENARIOS: list[dict[str, Any]] = [
    # ---------- depth 1: single constraint, later decision ----------
    {
        "id": "veg-dish-d1",
        "depth": 1,
        "sessions": [
            ["Remember I'm strictly vegetarian."],
            ["Suggest one dinner dish for me tonight - name the dish."],
        ],
        # "veg" covers vegetarian/veggie/vegetable/vegan phrasings; dish names cover
        # terse answers like "Vegetable Biryani" (live run 1: correct answer, too-narrow list).
        "expect_any": [
            "veg",
            "plant-based",
            "tofu",
            "paneer",
            "lentil",
            "mushroom",
            "aubergine",
            "risotto",
            "curry",
            "halloumi",
            "falafel",
            "biryani",
            "dal",
        ],
        "must_not": [
            "chicken",
            "beef",
            "pork",
            "steak",
            "lamb",
        ],
        "store_active_required": ["vegetarian"],
    },
    {
        "id": "shellfish-gift-d1",
        "depth": 1,
        "sessions": [
            ["Remember my brother is severely allergic to shellfish."],
            ["Suggest a food gift hamper I could send my brother."],
        ],
        "expect_any": [
            "allerg",
            "chocolat",
            "cheese",
            "fruit",
            "biscuit",
            "coffee",
            "tea",
            "jam",
            "honey",
        ],
        # live run 1: the agent CORRECTLY said "avoid shrimp/lobster/crab" and a
        # species must_not list penalized the avoidance sentence - negation false
        # positive. The wrong decision (a seafood hamper) is caught by expect_any
        # missing + the store check instead.
        "must_not": [],
        "store_active_required": ["shellfish"],
    },
    {
        "id": "laptop-budget-d1",
        "depth": 1,
        "sessions": [
            ["Remember my laptop budget is a hard cap of £700."],
            ["Which laptop should I buy? Name one and confirm it fits my budget."],
        ],
        "expect_any": ["700"],
        "must_not": [],
        "store_active_required": ["700"],
    },
    {
        "id": "tokyo-meeting-d1",
        "depth": 1,
        "sessions": [
            ["Remember I'm based in Tokyo and I never take meetings before 10am my time."],
            ["Propose a start time for a 30-minute call with me next Tuesday."],
        ],
        "expect_any": ["tokyo", "jst", "10", "11", "noon", "afternoon", "evening"],
        "must_not": [],
        "store_active_required": ["tokyo"],
    },
    {
        "id": "metal-music-d1",
        "depth": 1,
        "sessions": [
            ["Remember that I can't stand heavy metal music."],
            ["Recommend one music genre for my focus playlist."],
        ],
        # a correct answer may mention metal while steering away, so the wrong
        # decision is caught by expect_any missing, not by a must_not hit.
        "expect_any": [
            "lo-fi",
            "lofi",
            "ambient",
            "classical",
            "jazz",
            "instrumental",
            "piano",
            "electronic",
            "chillhop",
            "downtempo",
            "acoustic",
        ],
        "must_not": [],
        "store_active_required": ["metal"],
    },
    {
        "id": "neovim-editor-d1",
        "depth": 1,
        "sessions": [
            ["Remember I use Neovim exclusively and refuse to touch VS Code."],
            ["Which editor should I set up for a new Python project? One answer."],
        ],
        "expect_any": ["neovim", "nvim"],
        "must_not": [],
        "store_active_required": ["neovim"],
    },
    # ---------- depth 2: constraint superseded later; decision must follow the NEW one ----------
    # NOTE: live run 1 used a steak->vegan supersession here; its diet vocabulary
    # collided with veg-dish-d1 and birthday-dinner-d3 through the SHARED store
    # (scenarios run against one deployment), confounding the store checks. Every
    # scenario now owns a unique constraint domain - enforced by a lint test.
    {
        "id": "coffee-supersede-d2",
        "depth": 2,
        "sessions": [
            ["Remember I drink a double espresso every morning."],
            ["Big change: I've quit caffeine completely - decaf only from now on."],
            ["Suggest a morning drink for me - name one."],
        ],
        "expect_any": [
            "decaf",
            "caffeine-free",
            "herbal",
            "chamomile",
            "rooibos",
            "peppermint",
            "juice",
            "water",
        ],
        "must_not": [],
        "store_active_required": ["decaf"],
        "store_superseded_required": ["espresso"],
    },
    {
        "id": "city-move-d2",
        "depth": 2,
        "sessions": [
            ["Remember I live in Valencia."],
            ["I've moved house - I live in Porto now, not Valencia."],
            ["My friend wants to visit me next month - which city should they fly to?"],
        ],
        "expect_any": ["porto"],
        "must_not": [],
        "store_active_required": ["porto"],
        "store_superseded_required": ["valencia"],
    },
    {
        "id": "headphone-budget-d2",
        "depth": 2,
        "sessions": [
            ["Remember my headphone budget is £400."],
            ["Money's tight - cut my headphone budget to £150."],
            ["Pick headphones for me and remind me of my budget."],
        ],
        "expect_any": ["150"],
        "must_not": [],
        "store_active_required": ["150"],
        "store_superseded_required": ["400"],
    },
    # ---------- depth 3: three interacting constraints across three sessions ----------
    {
        "id": "birthday-dinner-d3",
        "depth": 3,
        "sessions": [
            ["Remember I'm coeliac - strictly gluten-free."],
            ["Remember my dinner budget is £20 a head, tops."],
            ["Remember I really don't enjoy Italian restaurants."],
            ["Choose a type of restaurant for my birthday dinner and briefly explain the choice."],
        ],
        "expect_any": ["gluten"],
        "must_not": [],
        "store_active_required": ["gluten", "20", "italian"],
    },
]


def run_scenario(
    chat: ChatFn, scenario: Mapping[str, Any], *, session_prefix: str = ""
) -> tuple[str, list[str]]:
    """Drive every session in order; return (answer, tool_calls_made) of the FINAL turn."""
    answer: str = ""
    tool_calls: list[str] = []
    for index, session in enumerate(scenario["sessions"]):
        session_id = f"{session_prefix}{scenario['id']}-s{index}"
        for message in session:
            answer, tool_calls = chat(message, session_id)
    return answer, tool_calls


def score_scenario(
    *,
    answer: str,
    tool_calls: Sequence[str],
    records: Sequence[Mapping[str, Any]],
    scenario: Mapping[str, Any],
) -> dict[str, Any]:
    """Grade one scenario. `records` is the FULL store (active + superseded) as dicts."""
    lowered = answer.casefold()
    expect_any = [str(token).casefold() for token in scenario.get("expect_any", [])]
    must_not = [str(token).casefold() for token in scenario.get("must_not", [])]

    violations = [token for token in must_not if token in lowered]
    expected_hit = not expect_any or any(token in lowered for token in expect_any)
    outcome_pass = expected_hit and not violations

    active = [r for r in records if not r.get("superseded_by")]
    superseded = [r for r in records if r.get("superseded_by")]
    missing_active = [
        token
        for token in scenario.get("store_active_required", [])
        if not _any_text_contains(active, token)
    ]
    missing_superseded = [
        token
        for token in scenario.get("store_superseded_required", [])
        if not _any_text_contains(superseded, token)
    ]
    forbidden_active = [
        token
        for token in scenario.get("store_active_forbidden", [])
        if _any_text_contains(active, token)
    ]
    store_pass = not missing_active and not missing_superseded and not forbidden_active

    process_pass = "recall" in tool_calls

    return {
        "id": scenario["id"],
        "depth": scenario["depth"],
        "outcome_pass": outcome_pass,
        "store_pass": store_pass,
        "process_pass": process_pass,
        "task_success": outcome_pass and store_pass and process_pass,
        "violations": violations,
        "missing_active": missing_active,
        "missing_superseded": missing_superseded,
        "forbidden_active": forbidden_active,
        "tool_calls": list(tool_calls),
        "answer_head": answer[:120],
    }


def aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {"scenarios": 0}

    by_depth: dict[int, dict[str, float]] = {}
    for depth in sorted({int(row["depth"]) for row in rows}):
        depth_rows = [row for row in rows if int(row["depth"]) == depth]
        by_depth[depth] = {
            "n": len(depth_rows),
            "task_success": _rate(depth_rows, "task_success"),
        }

    return {
        "scenarios": total,
        "task_success_rate": _rate(rows, "task_success"),
        "outcome_pass_rate": _rate(rows, "outcome_pass"),
        "store_pass_rate": _rate(rows, "store_pass"),
        "process_pass_rate": _rate(rows, "process_pass"),
        "constraint_violation_rate": sum(1 for row in rows if row["violations"]) / total,
        "by_depth": by_depth,
    }


def _any_text_contains(records: Sequence[Mapping[str, Any]], token: str) -> bool:
    needle = token.casefold()
    return any(needle in str(record.get("text", "")).casefold() for record in records)


def _rate(rows: Sequence[Mapping[str, Any]], key: str) -> float:
    return sum(1 for row in rows if row[key]) / len(rows)
