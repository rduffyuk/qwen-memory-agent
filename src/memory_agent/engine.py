from __future__ import annotations

from datetime import datetime, timezone

import tiktoken

from memory_agent.models import MemoryRecord
from memory_agent.qwen import QwenClient
from memory_agent.store import MemoryStore, SearchResult

DECAY_HALF_LIVES = {"fact": 30.0, "episodic": 7.0}
DEFAULT_HALF_LIFE_DAYS = 30.0
PINNED_TYPES = {"preference"}
TYPE_PRIORS = {
    "identity": 1.0,
    "preference": 1.0,
    "decision": 1.0,
    "fact": 0.8,
    "episodic": 0.5,
    "chore": 0.3,
}
DEFAULT_TYPE_PRIOR = 0.7


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
        delta: float = 0.10,
        supersede_threshold: float = 0.9,
    ) -> None:
        self.qwen = qwen
        self.store = store or MemoryStore(location=":memory:")
        self.token_budget = token_budget
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.delta = delta
        self.supersede_threshold = supersede_threshold
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
        vector = self.qwen.embed(record.text)
        for prior in self.store.active_by_subject_type(record.subject, record.type):
            if prior.text.strip().casefold() != record.text.strip().casefold():
                self.store.mark_superseded(prior.id, record.id)

        stored = self.store.upsert(record, vector)
        match = self.store.most_similar_active(
            vector,
            type=record.type,
            exclude_id=record.id,
            min_cosine=self.supersede_threshold,
        )
        if match is not None and match.superseded_by is None and match.id != record.id:
            self.store.mark_superseded(match.id, record.id)
        return stored

    def retrieve(
        self,
        query: str,
        *,
        token_budget: int | None = None,
        limit: int = 50,
        prefer_type: str | None = None,
        min_relevance: float = 0.0,
    ) -> list[MemoryRecord]:
        budget = token_budget if token_budget is not None else self.token_budget
        query_vector = self.qwen.embed(query)
        candidates = self.store.search(query_vector, limit=limit)
        ranked = sorted(
            candidates,
            key=lambda result: self._hybrid_score(result, prefer_type=prefer_type),
            reverse=True,
        )
        ranked = [result for result in ranked if result.cosine >= min_relevance]
        current = self._veto_stale_siblings(ranked)

        packed: list[MemoryRecord] = []
        used = 0
        for result in current:
            cost = self.count_tokens(result.record.text)
            separator_cost = 1 if packed else 0
            if used + separator_cost + cost > budget:
                continue
            packed.append(result.record)
            used += separator_cost + cost
        return self._reinforce(packed)

    def history(self, subject: str, *, type: str | None = None) -> list[MemoryRecord]:
        records = [
            record
            for record in self.store.list_records(include_superseded=True)
            if record.subject == subject
            and record.superseded_by is not None
            and (type is None or record.type == type)
        ]
        return sorted(records, key=lambda record: record.ts, reverse=True)

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
        # subject with no other criteria means "delete everything under this subject" —
        # the forget tool advertises delete-by-subject, so a bare subject must act.
        subject_only = subject is not None and (
            ttl_seconds is None and salience_below is None and decayed_below is None
        )
        to_delete: list[str] = []
        for record in self.store.list_records(include_superseded=True):
            if subject is not None and record.subject != subject:
                continue
            expired = ttl_seconds is not None and (now - record.ts).total_seconds() > ttl_seconds
            low_salience = salience_below is not None and record.salience < salience_below
            decayed = decayed_below is not None and effective_salience(record) < decayed_below
            if subject_only or expired or low_salience or decayed:
                to_delete.append(record.id)

        for delete_id in to_delete:
            self.store.delete(delete_id)
        return len(to_delete)

    def export_json(self) -> dict[str, object]:
        return {
            "version": 1,
            "records": [
                {
                    "record": record.model_dump(mode="json"),
                    "vector": vector,
                }
                for record, vector in self.store.export_records()
            ],
        }

    def import_json(self, data: dict[str, object]) -> int:
        imported = 0
        records = data.get("records", [])
        if not isinstance(records, list):
            raise ValueError("memory import payload must contain a records list")

        for entry in records:
            if not isinstance(entry, dict):
                raise ValueError("memory import entries must be objects")
            record = MemoryRecord.model_validate(entry["record"])
            vector = list(entry["vector"])
            self.store.upsert(record, vector)
            imported += 1
        return imported

    def export_markdown(self) -> str:
        stats = self.store.stats()
        lines = [
            f"# Memory export — {stats['active']} active, {stats['superseded']} superseded",
        ]
        records = sorted(
            self.store.list_records(),
            key=lambda record: (-record.salience, record.text),
        )
        for record in records:
            lines.append(
                f"- [{record.type} · sal {record.salience:.2f} · used {record.access_count}] "
                f"{record.text}"
            )
        return "\n".join(lines)

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self._encoding.encode(text))

    def _hybrid_score(self, result: SearchResult, *, prefer_type: str | None = None) -> float:
        score = (
            self.alpha * result.cosine
            + self.beta * _recency_score(result.record)
            + self.gamma * effective_salience(result.record)
            + self.delta * type_prior(result.record)
        )
        if prefer_type is not None and result.record.type == prefer_type:
            score += self.delta
        return score

    def _veto_stale_siblings(self, ranked: list[SearchResult]) -> list[SearchResult]:
        selected: dict[tuple[str, str], SearchResult] = {}
        for result in ranked:
            key = (result.record.subject, result.record.type)
            current = selected.get(key)
            if current is None or result.record.ts > current.record.ts:
                selected[key] = result
        return [
            result
            for result in ranked
            if selected[(result.record.subject, result.record.type)] is result
        ]

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


def type_prior(record: MemoryRecord) -> float:
    return TYPE_PRIORS.get(record.type, DEFAULT_TYPE_PRIOR)


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
