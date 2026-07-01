from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import tiktoken

from memory_agent.engine import MemoryEngine


def _load_encoding() -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model("gpt-4o-mini")
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


_ENCODING = _load_encoding()


def _pack(texts: Sequence[str], token_budget: int) -> str:
    """Greedily pack texts (in order) until the token budget is hit.

    Same accounting rule as MemoryEngine.retrieve (one separator token between
    entries), so every baseline competes under an identical context ceiling.
    """
    packed: list[str] = []
    used = 0
    for text in texts:
        cost = len(_ENCODING.encode(text))
        separator = 1 if packed else 0
        if used + separator + cost > token_budget:
            continue
        packed.append(text)
        used += separator + cost
    return "\n".join(packed)


def b0_no_memory(query: str, history: Iterable[dict[str, str]], *, token_budget: int) -> str:
    del query, history, token_budget
    return ""


def b1_full_history(query: str, history: Iterable[dict[str, str]], *, token_budget: int) -> str:
    # Naive "stuff the history": take it in chronological order, truncated to the
    # budget. Wastes budget on the oldest facts first — including superseded ones.
    del query
    return _pack([item["text"] for item in history], token_budget)


def b2_naive_top_k(query: str, history: Iterable[dict[str, str]], *, token_budget: int) -> str:
    # Keyword-ranked retrieval, packed to the budget. No supersession awareness,
    # so a larger budget surfaces *more* — including retired facts.
    query_terms = set(query.lower().split())
    scored = sorted(
        ((len(query_terms & set(item["text"].lower().split())), item["text"]) for item in history),
        reverse=True,
    )
    return _pack([text for _, text in scored], token_budget)


def b3_ours(query: str, engine: MemoryEngine, *, token_budget: int) -> str:
    return "\n".join(record.text for record in engine.retrieve(query, token_budget=token_budget))


def build_history(persona: dict[str, Any]) -> list[dict[str, str]]:
    return [*persona["sessions"], *persona.get("distractors", [])]
