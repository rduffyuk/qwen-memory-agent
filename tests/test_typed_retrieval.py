from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from memory_agent.engine import (
    DEFAULT_TYPE_PRIOR,
    TYPE_PRIORS,
    MemoryEngine,
    type_prior,
)
from memory_agent.models import MemoryRecord
from memory_agent.store import MemoryStore


class EqualVectorQwen:
    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0]


def make_engine(**kwargs: Any) -> MemoryEngine:
    return MemoryEngine(
        qwen=EqualVectorQwen(),
        store=MemoryStore(location=":memory:"),
        token_budget=512,
        **kwargs,
    )


def record(
    text: str,
    *,
    type: str,
    subject: str,
    ts: datetime,
    salience: float = 0.0,
) -> MemoryRecord:
    return MemoryRecord(
        text=text,
        type=type,
        subject=subject,
        salience=salience,
        ts=ts,
        last_accessed=ts,
    )


def import_records(engine: MemoryEngine, *records: MemoryRecord) -> None:
    imported = engine.import_json(
        {
            "version": 1,
            "records": [
                {"record": item.model_dump(mode="json"), "vector": [1.0, 0.0]} for item in records
            ],
        }
    )
    assert imported == len(records)


def test_type_prior_breaks_cosine_tie_for_higher_value_memory_type() -> None:
    engine = make_engine()
    now = datetime.now(timezone.utc)
    episodic = record(
        "Ryan mentioned coffee during a standup.",
        type="episodic",
        subject="coffee_note",
        ts=now,
    )
    preference = record(
        "Ryan prefers coffee in the morning.",
        type="preference",
        subject="coffee_preference",
        ts=now,
    )
    import_records(engine, episodic, preference)

    recalled = engine.retrieve("coffee", token_budget=512)

    assert recalled[0].id == preference.id


def test_type_prior_returns_catalogued_values_and_default_for_unknown_type() -> None:
    preference = MemoryRecord(text="Ryan prefers tea.", type="preference", subject="drink")
    chore = MemoryRecord(text="Water the plants.", type="chore", subject="plants")
    unknown = MemoryRecord(text="A custom note.", type="custom", subject="misc")

    # pin against literals, NOT the symbols under test — asserting
    # `type_prior(x) == DEFAULT_TYPE_PRIOR` is self-referential (a mutation of the
    # constant moves both sides together and the assertion still passes).
    assert type_prior(preference) == TYPE_PRIORS["preference"] == 1.0
    assert type_prior(chore) == TYPE_PRIORS["chore"] == 0.3
    assert type_prior(unknown) == DEFAULT_TYPE_PRIOR == 0.7
    # an uncatalogued type must rank *between* the lowest and highest priors,
    # never above a preference — this is what the 0.7 default encodes.
    assert TYPE_PRIORS["chore"] < type_prior(unknown) < TYPE_PRIORS["preference"]


def test_retrieve_veto_drops_stale_same_subject_type_sibling_from_import() -> None:
    engine = make_engine()
    now = datetime.now(timezone.utc)
    stale = record(
        "Ryan prefers coffee in the morning.",
        type="preference",
        subject="morning_drink",
        ts=now - timedelta(days=1),
        salience=1.0,
    )
    current = record(
        "Ryan prefers tea in the morning.",
        type="preference",
        subject="morning_drink",
        ts=now,
        salience=0.0,
    )
    import_records(engine, stale, current)

    recalled_text = "\n".join(item.text for item in engine.retrieve("morning drink"))

    assert "Ryan prefers tea in the morning." in recalled_text
    assert "Ryan prefers coffee in the morning." not in recalled_text


def test_retrieve_veto_keeps_same_type_for_distinct_subjects() -> None:
    engine = make_engine()
    now = datetime.now(timezone.utc)
    drink = record(
        "Ryan prefers tea in the morning.",
        type="preference",
        subject="morning_drink",
        ts=now,
    )
    music = record(
        "Ryan prefers jazz while coding.",
        type="preference",
        subject="coding_music",
        ts=now,
    )
    import_records(engine, drink, music)

    recalled_text = "\n".join(item.text for item in engine.retrieve("preference"))

    assert "Ryan prefers tea in the morning." in recalled_text
    assert "Ryan prefers jazz while coding." in recalled_text


class QueryOnlyQwen:
    """Embeds the query as [1, 0]; record vectors are supplied explicitly on import
    so we can control each memory's cosine against the query independently."""

    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0]


def _import_with_vectors(engine: MemoryEngine, *pairs: tuple[MemoryRecord, list[float]]) -> None:
    imported = engine.import_json(
        {
            "version": 1,
            "records": [
                {"record": item.model_dump(mode="json"), "vector": vector} for item, vector in pairs
            ],
        }
    )
    assert imported == len(pairs)


def test_default_delta_keeps_cosine_dominant_over_type_prior() -> None:
    # A clearly-more-relevant episodic (cosine 0.90, prior 0.5) must outrank a
    # barely-relevant preference (cosine 0.50, prior 1.0) at the default delta.
    # If delta were large enough to let the type prior override relevance, the
    # order would flip — so this locks delta's *magnitude*, not just its sign.
    engine = MemoryEngine(
        qwen=QueryOnlyQwen(),
        store=MemoryStore(location=":memory:"),
        token_budget=512,
    )
    now = datetime.now(timezone.utc)
    relevant_episodic = record("A relevant standup remark.", type="episodic", subject="a", ts=now)
    tangential_preference = record(
        "A tangential coffee preference.", type="preference", subject="b", ts=now
    )
    _import_with_vectors(
        engine,
        (relevant_episodic, [0.9, 0.4359]),  # cosine 0.90 vs [1, 0] query
        (tangential_preference, [0.5, 0.8660]),  # cosine 0.50 vs [1, 0] query
    )

    recalled = engine.retrieve("coffee", token_budget=512)

    assert recalled[0].id == relevant_episodic.id


def test_prefer_type_bias_promotes_requested_lower_prior_type() -> None:
    engine = make_engine()
    now = datetime.now(timezone.utc)
    preference = record(
        "Ryan prefers coffee in the morning.",
        type="preference",
        subject="coffee_preference",
        ts=now,
    )
    episodic = record(
        "Ryan mentioned coffee during a standup.",
        type="episodic",
        subject="coffee_note",
        ts=now,
    )
    import_records(engine, preference, episodic)

    recalled = engine.retrieve("coffee", token_budget=512, prefer_type="episodic")

    assert recalled[0].id == episodic.id
