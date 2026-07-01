from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any
from uuid import uuid4

from memory_agent.engine import MemoryEngine


@dataclass(frozen=True)
class DreamProposal:
    id: str
    kind: str
    target_ids: list[str]
    rationale: str
    merged_text: str | None = None
    subject: str | None = None
    type: str | None = None
    new_salience: float | None = None


@dataclass(frozen=True)
class DreamReport:
    applied: list[str]
    merged: int
    forgotten: int
    resalienced: int
    skipped: int


class DreamLoop:
    def __init__(self, engine: MemoryEngine, *, model: str | None = None) -> None:
        self.engine = engine
        self.model = model

    def dream(self) -> list[DreamProposal]:
        records = self.engine.store.list_records()
        if not records:
            return []
        active_ids = {record.id for record in records}
        digest = "\n".join(
            f"{record.id} · {record.type} · {record.subject} · "
            f"sal {record.salience:.2f} · {record.text}"
            for record in records
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You review active memory records and propose human-approved "
                    "consolidations. Return only a JSON array."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Review these active memories and return a JSON array of proposal "
                    "objects. Each object must include kind, target_ids, and rationale. "
                    "kind must be one of merge, forget, or resalience. merge proposals "
                    "must include merged_text and may include subject, type, and "
                    "new_salience. resalience proposals must include new_salience.\n\n"
                    f"{digest}"
                ),
            },
        ]

        raw_reply = self.engine.qwen.chat(messages, model=self.model)
        payload = _parse_json_array(str(raw_reply))
        if payload is None:
            return []

        proposals: list[DreamProposal] = []
        for entry in payload:
            proposal = _coerce_proposal(entry)
            if proposal is None or not _is_valid_proposal(proposal, active_ids):
                continue
            proposals.append(proposal)
        return proposals

    def apply(
        self,
        proposals: Sequence[DreamProposal],
        approved_ids: Iterable[str],
    ) -> DreamReport:
        approved = list(approved_ids)
        by_id = {proposal.id: proposal for proposal in proposals}
        vectors_by_id = dict(
            (record.id, vector) for record, vector in self.engine.store.export_records()
        )
        applied: list[str] = []
        merged = 0
        forgotten = 0
        resalienced = 0
        skipped = 0

        for approved_id in approved:
            proposal = by_id.get(approved_id)
            if proposal is None:
                skipped += 1
                continue
            if not _is_valid_proposal(proposal, set(vectors_by_id)):
                skipped += 1
                continue

            if proposal.kind == "merge":
                self.engine.write(
                    proposal.merged_text or "",
                    type=proposal.type or "fact",
                    subject=proposal.subject,
                    salience=0.5 if proposal.new_salience is None else proposal.new_salience,
                )
                for target_id in proposal.target_ids:
                    if self.engine.store.get(target_id) is not None:
                        self.engine.forget(record_id=target_id)
                merged += 1
                applied.append(proposal.id)
            elif proposal.kind == "forget":
                for target_id in proposal.target_ids:
                    self.engine.forget(record_id=target_id)
                forgotten += 1
                applied.append(proposal.id)
            elif proposal.kind == "resalience":
                for target_id in proposal.target_ids:
                    record = self.engine.store.get(target_id)
                    vector = vectors_by_id.get(target_id)
                    if record is None or vector is None:
                        continue
                    self.engine.store.upsert(
                        record.model_copy(update={"salience": proposal.new_salience}),
                        vector,
                    )
                resalienced += 1
                applied.append(proposal.id)
            else:
                skipped += 1

            vectors_by_id = dict(
                (record.id, vector) for record, vector in self.engine.store.export_records()
            )

        return DreamReport(
            applied=applied,
            merged=merged,
            forgotten=forgotten,
            resalienced=resalienced,
            skipped=skipped,
        )


def _parse_json_array(raw_reply: str) -> list[Any] | None:
    text = raw_reply.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        payload = json.loads(text)
    except JSONDecodeError:
        return None
    return payload if isinstance(payload, list) else None


def _coerce_proposal(entry: Any) -> DreamProposal | None:
    if not isinstance(entry, dict):
        return None
    kind = str(entry.get("kind") or "").strip()
    raw_target_ids = entry.get("target_ids")
    if not isinstance(raw_target_ids, list):
        return None
    target_ids = [str(target_id).strip() for target_id in raw_target_ids if str(target_id).strip()]
    return DreamProposal(
        id=str(uuid4()),
        kind=kind,
        target_ids=target_ids,
        rationale=str(entry.get("rationale") or "").strip(),
        merged_text=_optional_str(entry.get("merged_text")),
        subject=_optional_str(entry.get("subject")),
        type=_optional_str(entry.get("type")),
        new_salience=_optional_float(entry.get("new_salience")),
    )


def _is_valid_proposal(proposal: DreamProposal, active_ids: set[str]) -> bool:
    if proposal.kind not in {"merge", "forget", "resalience"}:
        return False
    if not proposal.target_ids:
        return False
    if any(target_id not in active_ids for target_id in proposal.target_ids):
        return False
    if proposal.kind == "merge" and not proposal.merged_text:
        return False
    if proposal.kind == "resalience" and proposal.new_salience is None:
        return False
    return True


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
