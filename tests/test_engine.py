from __future__ import annotations

from memory_agent.engine import MemoryEngine
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
