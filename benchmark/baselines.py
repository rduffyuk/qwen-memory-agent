from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from memory_agent.engine import MemoryEngine


def b0_no_memory(query: str, history: Iterable[dict[str, str]]) -> str:
    del query, history
    return ""


def b1_full_history(query: str, history: Iterable[dict[str, str]]) -> str:
    del query
    return "\n".join(item["text"] for item in history)


def b2_naive_top_k(query: str, history: Iterable[dict[str, str]], *, k: int = 3) -> str:
    query_terms = set(query.lower().split())
    scored = []
    for item in history:
        overlap = len(query_terms & set(item["text"].lower().split()))
        scored.append((overlap, item["text"]))
    return "\n".join(text for _, text in sorted(scored, reverse=True)[:k])


def b3_ours(query: str, engine: MemoryEngine, *, token_budget: int) -> str:
    return "\n".join(record.text for record in engine.retrieve(query, token_budget=token_budget))


def build_history(persona: dict[str, Any]) -> list[dict[str, str]]:
    return [*persona["sessions"], *persona.get("distractors", [])]
