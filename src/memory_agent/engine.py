from __future__ import annotations

from datetime import datetime, timezone

import tiktoken

from memory_agent.models import MemoryRecord
from memory_agent.qwen import QwenClient
from memory_agent.store import MemoryStore, SearchResult

DECAY_HALF_LIVES = {"fact": 30.0, "episodic": 7.0}
DEFAULT_HALF_LIFE_DAYS = 30.0
PINNED_TYPES = {"preference"}


class MemoryEngine:
    def __init__(
        self,
        *,
        qwen: QwenClient,
        store: MemoryStore | None = None,
        token_budget: int = 1024,
        alpha: float = 0.70,
        beta: float = 0.15,
        gamma: float = 0.15,
    ) -> None:
        self.qwen = qwen
        self.store = store or MemoryStore(location=":memory:")
        self.token_budget = token_budget
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self._encoding = _load_encoding()

    def write(
        self,
        text: str,
        *,
        type: str = "fact",
        subject: str | None = None,
        salience: float = 0.5,
        session_id: str | None = None,
    ) -> MemoryRecord:
        record = MemoryRecord(
            text=text,
            type=type,
            subject=subject or _infer_subject(text),
            salience=salience,
            session_id=session_id,
        )
        for prior in self.store.active_by_subject_type(record.subject, record.type):
            if prior.text.strip().casefold() != record.text.strip().casefold():
                self.store.mark_superseded(prior.id, record.id)

        vector = self.qwen.embed(record.text)
        return self.store.upsert(record, vector)

    def retrieve(
        self,
        query: str,
        *,
        token_budget: int | None = None,
        limit: int = 50,
    ) -> list[MemoryRecord]:
        budget = token_budget if token_budget is not None else self.token_budget
        query_vector = self.qwen.embed(query)
        candidates = self.store.search(query_vector, limit=limit)
        ranked = sorted(candidates, key=self._hybrid_score, reverse=True)

        packed: list[MemoryRecord] = []
        used = 0
        for result in ranked:
            cost = self.count_tokens(result.record.text)
            separator_cost = 1 if packed else 0
            if used + separator_cost + cost > budget:
                continue
            packed.append(result.record)
            used += separator_cost + cost
        return self._reinforce(packed)

    def forget(
        self,
        *,
        record_id: str | None = None,
        ttl_seconds: int | None = None,
        salience_below: float | None = None,
        decayed_below: float | None = None,
        subject: str | None = None,
    ) -> int:
        if record_id is not None:
            return int(self.store.delete(record_id))

        now = datetime.now(timezone.utc)
        to_delete: list[str] = []
        for record in self.store.list_records(include_superseded=True):
            if subject is not None and record.subject != subject:
                continue
            expired = ttl_seconds is not None and (now - record.ts).total_seconds() > ttl_seconds
            low_salience = salience_below is not None and record.salience < salience_below
            decayed = decayed_below is not None and effective_salience(record) < decayed_below
            if expired or low_salience or decayed:
                to_delete.append(record.id)

        for delete_id in to_delete:
            self.store.delete(delete_id)
        return len(to_delete)

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self._encoding.encode(text))

    def _hybrid_score(self, result: SearchResult) -> float:
        return (
            self.alpha * result.cosine
            + self.beta * _recency_score(result.record)
            + self.gamma * effective_salience(result.record)
        )

    def _reinforce(self, records: list[MemoryRecord]) -> list[MemoryRecord]:
        now = datetime.now(timezone.utc)
        reinforced: list[MemoryRecord] = []
        for record in records:
            updated = record.model_copy(
                update={"access_count": record.access_count + 1, "last_accessed": now}
            )
            self.store.upsert(updated, self.store._vectors[record.id])
            reinforced.append(updated)
        return reinforced


def effective_salience(record: MemoryRecord) -> float:
    if record.type in PINNED_TYPES:
        return record.salience

    age_days = max(
        (datetime.now(timezone.utc) - record.last_accessed).total_seconds() / 86_400, 0.0
    )
    half_life_days = DECAY_HALF_LIVES.get(record.type, DEFAULT_HALF_LIFE_DAYS)
    factor = 0.5 ** (age_days / half_life_days)
    return record.salience * factor


def _recency_score(record: MemoryRecord) -> float:
    age_days = max((datetime.now(timezone.utc) - record.ts).total_seconds() / 86_400, 0.0)
    return 1.0 / (1.0 + age_days)


def _infer_subject(text: str) -> str:
    before_colon = text.split(":", 1)[0].strip()
    if before_colon and before_colon != text:
        return before_colon[:80]
    words = [word.strip(".,:;!?").casefold() for word in text.split()[:6]]
    return "_".join(word for word in words if word) or "general"


def _load_encoding() -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model("gpt-4o-mini")
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")
