from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from memory_agent.engine import effective_salience
from memory_agent.models import MemoryRecord
from tests.test_engine import make_engine


def old_record(
    text: str,
    *,
    type: str = "fact",
    subject: str,
    salience: float = 0.8,
    days_old: int = 45,
) -> MemoryRecord:
    timestamp = datetime.now(timezone.utc) - timedelta(days=days_old)
    return MemoryRecord(
        text=text,
        type=type,
        subject=subject,
        salience=salience,
        ts=timestamp,
        last_accessed=timestamp,
    )


def test_effective_salience_decays_facts_but_keeps_pinned_preferences() -> None:
    faded = old_record("Ryan uses Python.", type="fact", subject="language")
    pinned = old_record("Ryan prefers tea.", type="preference", subject="drink")

    assert effective_salience(faded) < faded.salience
    assert effective_salience(pinned) == pinned.salience


def test_effective_salience_halves_at_exactly_one_half_life() -> None:
    # Pins the decay math to the half-life CONSTANTS: at exactly one half-life of
    # age, effective salience must be salience * 0.5. Kills the mutants that nudge
    # DECAY_HALF_LIVES["fact"] and DEFAULT_HALF_LIFE_DAYS off 30.0 (30->31 would
    # give factor 0.51, not 0.5). 'note' is non-pinned + absent from the table, so
    # it exercises DEFAULT_HALF_LIFE_DAYS; 'fact' exercises DECAY_HALF_LIVES["fact"].
    fact = old_record("Ryan uses Python.", type="fact", subject="lang", days_old=30)
    default_typed = old_record("A passing note.", type="note", subject="misc", days_old=30)

    assert math.isclose(effective_salience(fact), fact.salience * 0.5, rel_tol=0.01)
    assert math.isclose(effective_salience(default_typed), default_typed.salience * 0.5, rel_tol=0.01)


def test_retrieve_reinforces_packed_memory_and_resets_decay_clock() -> None:
    engine = make_engine(token_budget=8)
    recalled = old_record("Ryan drinks coffee while writing Python.", subject="recalled")
    peer = old_record("Ryan drinks coffee while reading Python.", subject="peer")
    engine.store.upsert(recalled, engine.qwen.embed(recalled.text))
    engine.store.upsert(peer, engine.qwen.embed(peer.text))

    results = engine.retrieve("coffee python")

    stored_recalled = engine.store.get(results[0].id)
    stored_peer = engine.store.get(peer.id)
    assert stored_recalled is not None
    assert stored_peer is not None
    assert stored_recalled.access_count == 1
    assert stored_recalled.last_accessed > recalled.last_accessed
    assert effective_salience(stored_recalled) > effective_salience(stored_peer)


def test_forget_decayed_below_deletes_faded_and_keeps_reinforced_memory() -> None:
    engine = make_engine(token_budget=8)
    faded = old_record("Ryan uses Python for scripts.", subject="faded", days_old=90)
    reinforced = old_record("Ryan uses Python for agents.", subject="reinforced", days_old=90)
    engine.store.upsert(faded, engine.qwen.embed(faded.text))
    engine.store.upsert(reinforced, engine.qwen.embed(reinforced.text))

    recalled = engine.retrieve("agents python")
    assert recalled
    assert recalled[0].id == reinforced.id

    forgotten = engine.forget(decayed_below=0.2)

    assert forgotten == 1
    assert engine.store.get(faded.id) is None
    assert engine.store.get(reinforced.id) is not None
