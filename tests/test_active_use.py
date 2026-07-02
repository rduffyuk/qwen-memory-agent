from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from benchmark.active_use import (
    SCENARIOS,
    aggregate,
    run_scenario,
    score_scenario,
)
from memory_agent.agent import MemoryAgent
from memory_agent.engine import MemoryEngine
from memory_agent.qwen import ToolCall
from memory_agent.store import MemoryStore

# ---------------------------------------------------------------------------
# scenario lint: the set must keep the shape the README table claims
# ---------------------------------------------------------------------------


def test_scenario_set_shape() -> None:
    ids = [scenario["id"] for scenario in SCENARIOS]
    assert len(ids) == len(set(ids)), "scenario ids must be unique"

    by_depth = {depth: 0 for depth in (1, 2, 3)}
    for scenario in SCENARIOS:
        by_depth[scenario["depth"]] += 1
    assert by_depth == {1: 6, 2: 3, 3: 1}


def test_every_scenario_is_multi_session_with_decision_last() -> None:
    for scenario in SCENARIOS:
        assert len(scenario["sessions"]) >= 2, scenario["id"]
        assert all(session for session in scenario["sessions"]), scenario["id"]


def test_expect_and_must_not_tokens_never_overlap() -> None:
    # a must_not token that is a substring of an expect token (or vice versa)
    # would make a correct answer self-defeating - e.g. "peanut-free" vs "peanut".
    for scenario in SCENARIOS:
        for expected in scenario.get("expect_any", []):
            for forbidden in scenario.get("must_not", []):
                assert forbidden.casefold() not in expected.casefold(), scenario["id"]
                assert expected.casefold() not in forbidden.casefold(), scenario["id"]


def test_depth2_scenarios_check_supersession_in_store() -> None:
    for scenario in SCENARIOS:
        if scenario["depth"] == 2:
            assert scenario.get("store_superseded_required"), scenario["id"]


# ---------------------------------------------------------------------------
# scorer unit tests
# ---------------------------------------------------------------------------


def _records(*entries: tuple[str, bool]) -> list[dict[str, Any]]:
    return [
        {"text": text, "superseded_by": "someid" if superseded else None}
        for text, superseded in entries
    ]


SCENARIO = {
    "id": "city-move-d2",
    "depth": 2,
    "sessions": [["seed"], ["update"], ["decide"]],
    "expect_any": ["porto"],
    "must_not": ["madrid"],
    "store_active_required": ["porto"],
    "store_superseded_required": ["valencia"],
}


def test_score_scenario_full_pass() -> None:
    row = score_scenario(
        answer="They should fly to Porto.",
        tool_calls=["recall"],
        records=_records(("I live in Valencia.", True), ("I live in Porto now.", False)),
        scenario=SCENARIO,
    )
    assert row["task_success"]
    assert row["outcome_pass"] and row["store_pass"] and row["process_pass"]
    assert row["violations"] == []


def test_score_scenario_violation_token_fails_outcome() -> None:
    row = score_scenario(
        answer="Porto, or maybe Madrid.",
        tool_calls=["recall"],
        records=_records(("I live in Valencia.", True), ("I live in Porto now.", False)),
        scenario=SCENARIO,
    )
    assert row["violations"] == ["madrid"]
    assert not row["outcome_pass"]
    assert not row["task_success"]


def test_score_scenario_stale_constraint_still_active_fails_store() -> None:
    # the update never superseded the old record: both cities active
    row = score_scenario(
        answer="They should fly to Porto.",
        tool_calls=["recall"],
        records=_records(("I live in Valencia.", False), ("I live in Porto now.", False)),
        scenario=SCENARIO,
    )
    assert row["missing_superseded"] == ["valencia"]
    assert not row["store_pass"]
    assert not row["task_success"]


def test_score_scenario_lucky_guess_without_recall_fails_process() -> None:
    row = score_scenario(
        answer="They should fly to Porto.",
        tool_calls=[],
        records=_records(("I live in Valencia.", True), ("I live in Porto now.", False)),
        scenario=SCENARIO,
    )
    assert row["outcome_pass"] and row["store_pass"]
    assert not row["process_pass"]
    assert not row["task_success"]


def test_score_scenario_empty_expect_any_passes_on_no_violation() -> None:
    scenario = {**SCENARIO, "expect_any": []}
    row = score_scenario(
        answer="Anywhere is fine.",
        tool_calls=["recall"],
        records=_records(("I live in Valencia.", True), ("I live in Porto now.", False)),
        scenario=scenario,
    )
    assert row["outcome_pass"]


def test_aggregate_reports_by_depth_and_violation_rate() -> None:
    rows = [
        {
            "depth": 1,
            "task_success": True,
            "outcome_pass": True,
            "store_pass": True,
            "process_pass": True,
            "violations": [],
        },
        {
            "depth": 1,
            "task_success": False,
            "outcome_pass": False,
            "store_pass": True,
            "process_pass": True,
            "violations": ["steak"],
        },
        {
            "depth": 2,
            "task_success": True,
            "outcome_pass": True,
            "store_pass": True,
            "process_pass": True,
            "violations": [],
        },
    ]
    summary = aggregate(rows)
    assert summary["scenarios"] == 3
    assert summary["task_success_rate"] == 2 / 3
    assert summary["constraint_violation_rate"] == 1 / 3
    assert summary["by_depth"][1] == {"n": 2, "task_success": 0.5}
    assert summary["by_depth"][2] == {"n": 1, "task_success": 1.0}


def test_aggregate_empty() -> None:
    assert aggregate([]) == {"scenarios": 0}


# ---------------------------------------------------------------------------
# end-to-end offline: a scripted agent through the real engine (zero credit)
# ---------------------------------------------------------------------------


class VocabQwen:
    """Scripted chat turns + deterministic bag-of-words embeddings."""

    VOCAB = ["porto", "valencia", "city", "live"]

    def __init__(self, turns: list[Any]) -> None:
        self.turns = turns

    def embed(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count(word)) for word in self.VOCAB]

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> Any:
        return self.turns.pop(0)


def _remember_turn(call_id: str, text: str, subject: str) -> SimpleNamespace:
    return SimpleNamespace(
        content=None,
        tool_calls=[
            ToolCall(
                id=call_id,
                name="remember",
                arguments={"text": text, "type": "fact", "subject": subject},
            )
        ],
    )


def _final_turn(content: str) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=[])


def city_scenario() -> dict[str, Any]:
    return next(s for s in SCENARIOS if s["id"] == "city-move-d2")


def test_offline_agent_passes_city_move_scenario() -> None:
    qwen = VocabQwen(
        [
            # session 0: seed
            _remember_turn("c1", "I live in Valencia.", "home_city"),
            _final_turn("Noted."),
            # session 1: update - same subject, exact supersession retires the seed
            _remember_turn("c2", "I live in Porto now.", "home_city"),
            _final_turn("Updated."),
            # session 2: decision - recall first, then answer from memory
            SimpleNamespace(
                content=None,
                tool_calls=[
                    ToolCall(id="c3", name="recall", arguments={"query": "which city do I live in"})
                ],
            ),
            _final_turn("They should fly to Porto - that's where you live now."),
        ]
    )
    engine = MemoryEngine(qwen=qwen, store=MemoryStore(location=":memory:"))
    agent = MemoryAgent(engine)

    def chat(message: str, session_id: str) -> tuple[str, list[str]]:
        result = agent.run(message, session_id=session_id)
        return result.answer, result.tool_calls_made

    answer, tool_calls = run_scenario(chat, city_scenario())
    records = [
        record.model_dump(mode="json")
        for record in engine.store.list_records(include_superseded=True)
    ]

    row = score_scenario(
        answer=answer, tool_calls=tool_calls, records=records, scenario=city_scenario()
    )
    assert row["task_success"], row


def test_offline_agent_fails_when_it_guesses_without_recall() -> None:
    qwen = VocabQwen(
        [
            _remember_turn("c1", "I live in Valencia.", "home_city"),
            _final_turn("Noted."),
            _remember_turn("c2", "I live in Porto now.", "home_city"),
            _final_turn("Updated."),
            # decision WITHOUT consulting memory - a lucky guess must not count
            _final_turn("They should fly to Porto."),
        ]
    )
    engine = MemoryEngine(qwen=qwen, store=MemoryStore(location=":memory:"))
    agent = MemoryAgent(engine)

    def chat(message: str, session_id: str) -> tuple[str, list[str]]:
        result = agent.run(message, session_id=session_id)
        return result.answer, result.tool_calls_made

    answer, tool_calls = run_scenario(chat, city_scenario())
    records = [
        record.model_dump(mode="json")
        for record in engine.store.list_records(include_superseded=True)
    ]

    row = score_scenario(
        answer=answer, tool_calls=tool_calls, records=records, scenario=city_scenario()
    )
    assert not row["process_pass"]
    assert not row["task_success"]
