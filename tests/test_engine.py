from __future__ import annotations

import pytest

from memory_agent.engine import MemoryEngine
from memory_agent.models import MemoryRecord
from memory_agent.store import MemoryStore


class FakeQwen:
    def embed(self, text: str) -> list[float]:
        lowered = text.lower()
        return [
            float(lowered.count("coffee")),
            float(lowered.count("tea")),
            float(lowered.count("jazz")),
            float(lowered.count("python")),
        ]

    def chat(self, messages: list[dict[str, str]], model: str | None = None) -> str:
        return messages[-1]["content"]


class VectorQwen:
    def __init__(
        self,
        vectors: dict[str, list[float]],
        *,
        embed_model: str | None = None,
        chat_model: str | None = None,
    ) -> None:
        self.vectors = vectors
        if embed_model is not None:
            self.embed_model = embed_model
        if chat_model is not None:
            self.chat_model = chat_model

    def embed(self, text: str) -> list[float]:
        return self.vectors[text]

    def chat(self, messages: list[dict[str, str]], model: str | None = None) -> str:
        return messages[-1]["content"]


def make_engine(token_budget: int = 128) -> MemoryEngine:
    return MemoryEngine(
        qwen=FakeQwen(),
        store=MemoryStore(location=":memory:"),
        token_budget=token_budget,
    )


def test_supersession_retires_prior_fact_and_retrieval_hides_stale_value() -> None:
    engine = make_engine()

    old = engine.write(
        "Ryan prefers coffee in the morning.",
        type="preference",
        subject="morning_drink",
    )
    new = engine.write(
        "Ryan prefers tea in the morning.",
        type="preference",
        subject="morning_drink",
    )

    stored_old = engine.store.get(old.id)
    assert stored_old is not None
    assert stored_old.superseded_by == new.id

    recalled = engine.retrieve("What morning drink does Ryan prefer?")
    recalled_text = "\n".join(record.text for record in recalled)
    assert "tea" in recalled_text
    assert "coffee" not in recalled_text


def test_retrieve_budget_packing_never_exceeds_configured_token_budget() -> None:
    engine = make_engine(token_budget=18)
    for idx in range(6):
        engine.write(
            f"coffee preference memory number {idx} with extra detail",
            type="preference",
            subject=f"coffee_{idx}",
        )

    recalled = engine.retrieve("coffee preference", token_budget=18)

    assert len(recalled) < 6
    assert engine.count_tokens("\n".join(record.text for record in recalled)) <= 18


def test_retrieve_ranks_relevant_memory_above_distractor() -> None:
    engine = make_engine()
    engine.write("Ryan likes jazz while coding.", type="preference", subject="music")
    engine.write("Ryan likes coffee before coding.", type="preference", subject="drink")

    recalled = engine.retrieve("coffee preference", token_budget=128)

    assert recalled
    assert recalled[0].subject == "drink"
    assert "coffee" in recalled[0].text


def test_retrieve_min_relevance_can_filter_unrelated_zero_overlap_query() -> None:
    engine = make_engine()
    engine.write("Ryan likes jazz while coding.", type="preference", subject="music")

    default_recalled = engine.retrieve("weather forecast", token_budget=128)
    filtered_recalled = engine.retrieve("weather forecast", token_budget=128, min_relevance=0.05)

    assert default_recalled
    assert filtered_recalled == []


def test_history_returns_superseded_records_newest_retired_first() -> None:
    engine = make_engine()
    first = engine.write(
        "Ryan prefers coffee in the morning.",
        type="preference",
        subject="morning_drink",
    )
    second = engine.write(
        "Ryan prefers tea in the morning.",
        type="preference",
        subject="morning_drink",
    )
    active = engine.write(
        "Ryan prefers water in the morning.",
        type="preference",
        subject="morning_drink",
    )

    retired = engine.history("morning_drink")

    assert [record.id for record in retired] == [second.id, first.id]
    assert active.id not in {record.id for record in retired}
    assert all(record.superseded_by is not None for record in retired)


def test_semantic_supersession_retires_different_subject_paraphrase() -> None:
    engine = MemoryEngine(
        qwen=VectorQwen(
            {
                "Ryan prefers coffee in the morning.": [1.0, 0.0],
                "Ryan's morning beverage is coffee.": [0.95, 0.05],
            }
        ),
        store=MemoryStore(location=":memory:"),
        supersede_threshold=0.9,
    )

    old = engine.write("Ryan prefers coffee in the morning.", type="fact", subject="s1")
    new = engine.write("Ryan's morning beverage is coffee.", type="fact", subject="s2")

    stored_old = engine.store.get(old.id)
    assert stored_old is not None
    assert stored_old.superseded_by == new.id


def test_semantic_supersession_preserves_distinct_low_similarity_fact() -> None:
    engine = MemoryEngine(
        qwen=VectorQwen(
            {
                "Ryan prefers coffee in the morning.": [1.0, 0.0],
                "Ryan likes jazz while coding.": [0.0, 1.0],
                "coffee query": [1.0, 0.0],
            }
        ),
        store=MemoryStore(location=":memory:"),
        supersede_threshold=0.9,
    )

    old = engine.write("Ryan prefers coffee in the morning.", type="fact", subject="s1")
    new = engine.write("Ryan likes jazz while coding.", type="fact", subject="s2")

    stored_old = engine.store.get(old.id)
    assert stored_old is not None
    assert stored_old.superseded_by is None
    recalled_ids = {record.id for record in engine.retrieve("coffee query", token_budget=128)}
    assert {old.id, new.id}.issubset(recalled_ids)


def test_semantic_supersession_only_matches_same_type() -> None:
    engine = MemoryEngine(
        qwen=VectorQwen(
            {
                "Ryan prefers coffee in the morning.": [1.0, 0.0],
                "Ryan's morning beverage is coffee.": [1.0, 0.0],
            }
        ),
        store=MemoryStore(location=":memory:"),
        supersede_threshold=0.9,
    )

    old = engine.write("Ryan prefers coffee in the morning.", type="fact", subject="s1")
    engine.write("Ryan's morning beverage is coffee.", type="preference", subject="s2")

    stored_old = engine.store.get(old.id)
    assert stored_old is not None
    assert stored_old.superseded_by is None


def test_semantic_supersession_threshold_is_honored() -> None:
    vectors = {
        "Ryan prefers coffee in the morning.": [1.0, 0.0],
        "Ryan's morning beverage is coffee.": [0.8, 0.6],
    }
    low_threshold_engine = MemoryEngine(
        qwen=VectorQwen(vectors),
        store=MemoryStore(location=":memory:"),
        supersede_threshold=0.75,
    )
    high_threshold_engine = MemoryEngine(
        qwen=VectorQwen(vectors),
        store=MemoryStore(location=":memory:"),
        supersede_threshold=0.85,
    )

    low_old = low_threshold_engine.write(
        "Ryan prefers coffee in the morning.", type="fact", subject="s1"
    )
    low_new = low_threshold_engine.write(
        "Ryan's morning beverage is coffee.", type="fact", subject="s2"
    )
    high_old = high_threshold_engine.write(
        "Ryan prefers coffee in the morning.", type="fact", subject="s1"
    )
    high_threshold_engine.write("Ryan's morning beverage is coffee.", type="fact", subject="s2")

    low_stored_old = low_threshold_engine.store.get(low_old.id)
    high_stored_old = high_threshold_engine.store.get(high_old.id)
    assert low_stored_old is not None
    assert high_stored_old is not None
    assert low_stored_old.superseded_by == low_new.id
    assert high_stored_old.superseded_by is None


def test_default_supersede_threshold_is_0_9_and_enables_retirement() -> None:
    # Codex's semantic-supersession tests all pass an EXPLICIT threshold, so the
    # DEFAULT (0.9) was never exercised — a mutation to 1.9 (unreachable, cosine <= 1)
    # silently disabled the feature and survived. Pin the literal AND the behaviour.
    engine = MemoryEngine(
        qwen=VectorQwen(
            {
                "Ryan prefers coffee in the morning.": [1.0, 0.0],
                "Ryan's morning beverage is coffee.": [0.95, 0.05],  # cosine ~0.999 vs first
            }
        ),
        store=MemoryStore(location=":memory:"),
    )  # no supersede_threshold -> default

    assert engine.supersede_threshold == 0.9
    old = engine.write("Ryan prefers coffee in the morning.", type="fact", subject="s1")
    new = engine.write("Ryan's morning beverage is coffee.", type="fact", subject="s2")

    stored_old = engine.store.get(old.id)
    assert stored_old is not None
    assert stored_old.superseded_by == new.id


def test_forget_by_subject_alone_deletes_that_subject_only() -> None:
    # Live bug (found testing the dreaming loop on ECS): the forget tool advertises
    # "delete by subject", the model calls forget(subject=...) with no other args,
    # but engine.forget only deleted when ttl/salience/decay criteria also matched —
    # so subject-only forget silently returned 0 and the record was unremovable.
    engine = MemoryEngine(qwen=FakeQwen(), store=MemoryStore(location=":memory:"))
    keep = engine.write("Ryan likes jazz while coding.", type="preference", subject="music")
    drop = engine.write("Ryan likes anime, Overlord especially.", type="preference", subject="user")

    forgotten = engine.forget(subject="user")

    assert forgotten == 1
    assert engine.store.get(drop.id) is None
    assert engine.store.get(keep.id) is not None


def test_forget_by_query_deletes_closest_match_above_threshold() -> None:
    # Live bug, part 2: the model can't guess the stored subject string (a dream-merge
    # filed the record under subject='user'), so forget(subject=<guess>) misses. A
    # natural-language query must forget the closest matching memory semantically —
    # the same trick semantic supersession uses on the write path.
    engine = MemoryEngine(
        qwen=VectorQwen(
            {
                "User likes anime, Overlord especially.": [1.0, 0.0],
                "Ryan likes jazz while coding.": [0.0, 1.0],
                "anime preferences": [0.98, 0.02],
            }
        ),
        store=MemoryStore(location=":memory:"),
    )
    drop = engine.write("User likes anime, Overlord especially.", type="preference", subject="user")
    keep = engine.write("Ryan likes jazz while coding.", type="preference", subject="music")

    forgotten = engine.forget(query="anime preferences")

    assert forgotten == 1
    assert engine.store.get(drop.id) is None
    assert engine.store.get(keep.id) is not None


def test_forget_by_query_below_threshold_deletes_nothing() -> None:
    engine = MemoryEngine(
        qwen=VectorQwen(
            {
                "Ryan likes jazz while coding.": [0.0, 1.0],
                "totally unrelated topic": [1.0, 0.0],
            }
        ),
        store=MemoryStore(location=":memory:"),
    )
    keep = engine.write("Ryan likes jazz while coding.", type="preference", subject="music")

    forgotten = engine.forget(query="totally unrelated topic")

    assert forgotten == 0
    assert engine.store.get(keep.id) is not None


def test_write_stamps_model_provenance_and_json_round_trips_it() -> None:
    engine = MemoryEngine(
        qwen=VectorQwen(
            {
                "Ryan prefers tea.": [1.0, 0.0],
                "tea": [1.0, 0.0],
            },
            embed_model="embed-a",
        ),
        store=MemoryStore(location=":memory:"),
    )

    record = engine.write(
        "Ryan prefers tea.",
        type="preference",
        subject="drink",
        source_model="chat-a",
    )
    snapshot = engine.export_json()
    imported = MemoryEngine(
        qwen=VectorQwen({"tea": [1.0, 0.0]}, embed_model="embed-a"),
        store=MemoryStore(location=":memory:"),
    )
    imported_count = imported.import_json(snapshot)

    assert record.embed_model == "embed-a"
    assert record.source_model == "chat-a"
    exported_record = snapshot["records"][0]["record"]
    assert exported_record["embed_model"] == "embed-a"
    assert exported_record["source_model"] == "chat-a"
    assert imported_count == 1
    imported_record = imported.retrieve("tea")[0]
    assert imported_record.embed_model == "embed-a"
    assert imported_record.source_model == "chat-a"


def test_old_format_record_without_provenance_loads_and_retrieves() -> None:
    engine = MemoryEngine(
        qwen=VectorQwen({"tea query": [1.0, 0.0]}, embed_model="embed-a"),
        store=MemoryStore(location=":memory:"),
    )
    legacy_record = MemoryRecord(
        text="Ryan prefers tea.",
        type="preference",
        subject="drink",
    ).model_dump(mode="json", exclude={"embed_model", "source_model"})

    imported = engine.import_json(
        {"version": 1, "records": [{"record": legacy_record, "vector": [1.0, 0.0]}]}
    )
    recalled = engine.retrieve("tea query")

    assert imported == 1
    assert recalled
    assert recalled[0].text == "Ryan prefers tea."
    assert recalled[0].embed_model is None
    assert recalled[0].source_model is None


def test_same_dimension_embedder_swap_hides_mismatches_and_skips_cross_space_supersession() -> None:
    qwen_a = VectorQwen(
        {
            "Ryan prefers coffee.": [1.0, 0.0],
        },
        embed_model="embed-a",
    )
    engine = MemoryEngine(qwen=qwen_a, store=MemoryStore(location=":memory:"))
    old = engine.write("Ryan prefers coffee.", type="preference", subject="old-drink")
    engine.qwen = VectorQwen(
        {
            "coffee query": [1.0, 0.0],
            "Ryan's drink is coffee.": [1.0, 0.0],
        },
        embed_model="embed-b",
    )

    recalled = engine.retrieve("coffee query")
    new = engine.write("Ryan's drink is coffee.", type="preference", subject="new-drink")

    assert recalled == []
    assert engine.stats()["embed_model_mismatch"] == 1
    assert engine.store.get(old.id).superseded_by is None
    assert engine.store.get(new.id).embed_model == "embed-b"


def test_reembed_restamps_mismatches_and_restores_retrieval() -> None:
    engine = MemoryEngine(
        qwen=VectorQwen({"Ryan prefers coffee.": [1.0, 0.0]}, embed_model="embed-a"),
        store=MemoryStore(location=":memory:"),
    )
    record = engine.write("Ryan prefers coffee.", type="preference", subject="drink")
    engine.qwen = VectorQwen(
        {
            "Ryan prefers coffee.": [0.0, 1.0],
            "coffee query": [0.0, 1.0],
        },
        embed_model="embed-b",
    )

    before = engine.retrieve("coffee query")
    reembedded = engine.reembed()
    after = engine.retrieve("coffee query")

    assert before == []
    assert reembedded == 1
    assert after and after[0].id == record.id
    restored = engine.store.get(record.id)
    assert restored is not None
    assert restored.embed_model == "embed-b"
    assert engine.store._vectors[record.id] == [0.0, 1.0]  # noqa: SLF001
    assert engine.stats()["embed_model_mismatch"] == 0


def test_different_dimension_query_raises_clear_error_before_qdrant_traceback() -> None:
    engine = MemoryEngine(
        qwen=VectorQwen(
            {
                "Ryan prefers coffee.": [1.0, 0.0],
                "coffee query": [1.0, 0.0, 0.0],
            },
            embed_model="embed-a",
        ),
        store=MemoryStore(location=":memory:"),
    )
    engine.write("Ryan prefers coffee.", type="preference", subject="drink")

    with pytest.raises(ValueError, match="query vector dimension mismatch"):
        engine.retrieve("coffee query")
