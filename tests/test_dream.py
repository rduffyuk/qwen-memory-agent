from __future__ import annotations

import asyncio
import json
from dataclasses import FrozenInstanceError
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from memory_agent.api import create_app
from memory_agent.dream import DreamLoop, DreamProposal, DreamReport
from memory_agent.engine import MemoryEngine
from memory_agent.mcp_server import create_mcp_server
from memory_agent.store import MemoryStore


class FakeQwen:
    def __init__(self, replies: list[str] | None = None) -> None:
        self.replies = replies or []
        self.chat_calls = 0

    def embed(self, text: str) -> list[float]:
        lowered = text.lower()
        return [
            float(lowered.count("coffee")),
            float(lowered.count("tea")),
            float(lowered.count("jazz")),
            float(lowered.count("python")),
            float(lowered.count("coding")),
        ]

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> str:
        self.chat_calls += 1
        return self.replies.pop(0) if self.replies else "[]"


def make_engine(replies: list[str] | None = None) -> MemoryEngine:
    return MemoryEngine(
        qwen=FakeQwen(replies),
        store=MemoryStore(location=":memory:"),
        token_budget=128,
    )


def test_dream_empty_store_returns_empty_without_qwen_call() -> None:
    engine = make_engine()

    proposals = DreamLoop(engine).dream()

    assert proposals == []
    assert engine.qwen.chat_calls == 0


def test_dream_parses_proposals_without_mutating_store() -> None:
    engine = make_engine()
    first = engine.write("Ryan prefers coffee.", type="preference", subject="drink")
    second = engine.write("Ryan likes jazz.", type="preference", subject="music")
    engine.qwen.replies.append(
        json.dumps(
            [
                {
                    "kind": "merge",
                    "target_ids": [first.id, second.id],
                    "rationale": "Related preferences can be compacted.",
                    "merged_text": "Ryan prefers coffee and likes jazz.",
                    "subject": "preferences",
                    "type": "preference",
                    "new_salience": 0.8,
                }
            ]
        )
    )
    before = engine.store.stats()

    proposals = DreamLoop(engine).dream()

    assert engine.store.stats() == before
    assert len(proposals) == 1
    assert proposals[0].kind == "merge"
    assert proposals[0].target_ids == [first.id, second.id]
    assert proposals[0].merged_text == "Ryan prefers coffee and likes jazz."
    assert proposals[0].id


def test_dream_drops_proposals_that_reference_unknown_record_ids() -> None:
    engine = make_engine()
    record = engine.write("Ryan writes Python tests.", type="fact", subject="testing")
    engine.qwen.replies.append(
        json.dumps(
            [
                {
                    "kind": "forget",
                    "target_ids": [record.id],
                    "rationale": "No longer useful.",
                },
                {
                    "kind": "forget",
                    "target_ids": ["missing-id"],
                    "rationale": "Hallucinated id.",
                },
            ]
        )
    )

    proposals = DreamLoop(engine).dream()

    assert len(proposals) == 1
    assert proposals[0].target_ids == [record.id]


def test_dream_tolerates_fenced_non_list_and_malformed_replies() -> None:
    engine = make_engine()
    record = engine.write("Ryan prefers tea.", type="preference", subject="drink")
    engine.qwen.replies.extend(
        [
            "```json\n"
            + json.dumps(
                [
                    {
                        "kind": "forget",
                        "target_ids": [record.id],
                        "rationale": "Duplicate.",
                    }
                ]
            )
            + "\n```",
            json.dumps({"kind": "forget", "target_ids": [record.id]}),
            "{not json",
        ]
    )
    loop = DreamLoop(engine)

    assert len(loop.dream()) == 1
    assert loop.dream() == []
    assert loop.dream() == []


def test_apply_merge_only_when_approved() -> None:
    engine = make_engine()
    first = engine.write("Ryan prefers coffee.", type="preference", subject="drink")
    second = engine.write("Ryan prefers tea.", type="preference", subject="drink")
    unapproved = engine.write("Ryan likes jazz.", type="preference", subject="music")
    merge = DreamProposal(
        id="merge-1",
        kind="merge",
        target_ids=[first.id, second.id],
        rationale="Keep a compact current drink preference.",
        merged_text="Ryan currently prefers tea over coffee.",
        subject="drink",
        type="preference",
        new_salience=0.9,
    )
    forget = DreamProposal(
        id="forget-1",
        kind="forget",
        target_ids=[unapproved.id],
        rationale="Not approved.",
    )

    report = DreamLoop(engine).apply([merge, forget], approved_ids=["merge-1"])
    recalled_text = "\n".join(
        record.text for record in engine.retrieve("tea coffee preference", token_budget=128)
    )

    assert report.merged == 1
    assert report.forgotten == 0
    assert report.applied == ["merge-1"]
    assert "currently prefers tea over coffee" in recalled_text
    assert "Ryan prefers coffee." not in recalled_text
    assert engine.store.get(unapproved.id) is not None


def test_apply_merge_preserves_deliberate_zero_salience() -> None:
    engine = make_engine()
    first = engine.write("Ryan prefers coffee.", type="preference", subject="drink")
    second = engine.write("Ryan prefers tea.", type="preference", subject="drink")
    merge = DreamProposal(
        id="merge-1",
        kind="merge",
        target_ids=[first.id, second.id],
        rationale="Keep a compact current drink preference with no boost.",
        merged_text="Ryan currently prefers tea.",
        subject="drink",
        type="preference",
        new_salience=0.0,
    )

    report = DreamLoop(engine).apply([merge], approved_ids=["merge-1"])

    assert report.merged == 1
    merged_records = [
        record
        for record in engine.store.list_records()
        if record.text == "Ryan currently prefers tea."
    ]
    assert len(merged_records) == 1
    assert merged_records[0].salience == 0.0


def test_apply_forget_and_resalience_preserves_vector() -> None:
    engine = make_engine()
    forgotten = engine.write("Ryan no longer needs this chore.", type="chore", subject="old")
    adjusted = engine.write("Ryan writes Python tests.", type="fact", subject="testing")
    vector_before = dict((record.id, vector) for record, vector in engine.store.export_records())[
        adjusted.id
    ]
    proposals = [
        DreamProposal(
            id="forget-1",
            kind="forget",
            target_ids=[forgotten.id],
            rationale="Stale chore.",
        ),
        DreamProposal(
            id="salience-1",
            kind="resalience",
            target_ids=[adjusted.id],
            rationale="Important implementation fact.",
            new_salience=0.95,
        ),
    ]

    report = DreamLoop(engine).apply(proposals, approved_ids=["forget-1", "salience-1"])

    assert report.forgotten == 1
    assert report.resalienced == 1
    assert engine.store.get(forgotten.id) is None
    stored = engine.store.get(adjusted.id)
    assert stored is not None
    assert stored.salience == 0.95
    vector_after = dict((record.id, vector) for record, vector in engine.store.export_records())[
        adjusted.id
    ]
    assert vector_after == vector_before
    assert engine.retrieve("Python tests", token_budget=128)[0].id == adjusted.id


def test_apply_counts_unknown_approved_ids_as_skipped() -> None:
    engine = make_engine()
    record = engine.write("Ryan likes jazz.", type="preference", subject="music")
    proposal = DreamProposal(
        id="forget-1",
        kind="forget",
        target_ids=[record.id],
        rationale="Approved.",
    )

    report = DreamLoop(engine).apply([proposal], approved_ids=["forget-1", "missing-proposal"])

    assert report.applied == ["forget-1"]
    assert report.forgotten == 1
    assert report.skipped == 1


def test_dream_dataclasses_are_immutable() -> None:
    # DreamProposal / DreamReport are frozen so a proposal cannot be tampered with
    # between dream() and apply() — the human approves exactly what was proposed.
    proposal = DreamProposal(id="p1", kind="forget", target_ids=["a"], rationale="stale")
    report = DreamReport(applied=[], merged=0, forgotten=0, resalienced=0, skipped=0)
    with pytest.raises(FrozenInstanceError):
        proposal.kind = "merge"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        report.merged = 99  # type: ignore[misc]


def test_api_dream_and_apply_routes() -> None:
    engine = make_engine()
    record = engine.write("Ryan prefers tea.", type="preference", subject="drink")
    engine.qwen.replies.append(
        json.dumps(
            [
                {
                    "kind": "forget",
                    "target_ids": [record.id],
                    "rationale": "Approved stale memory.",
                }
            ]
        )
    )
    client = TestClient(create_app(engine))

    dream_response = client.post("/dream")
    proposals = dream_response.json()["proposals"]
    apply_response = client.post(
        "/dream/apply",
        json={"proposals": proposals, "approved_ids": [proposals[0]["id"]]},
    )

    assert dream_response.status_code == 200
    assert apply_response.status_code == 200
    assert apply_response.json()["forgotten"] == 1
    assert engine.store.get(record.id) is None


def test_mcp_dream_tools_are_registered_and_functional() -> None:
    engine = make_engine()
    record = engine.write("Ryan prefers coffee.", type="preference", subject="drink")
    proposal = {
        "kind": "forget",
        "target_ids": [record.id],
        "rationale": "Approved stale memory.",
    }
    engine.qwen.replies.append(json.dumps([proposal]))
    mcp = create_mcp_server(engine)

    tool_names = asyncio.run(_list_mcp_tool_names(mcp))
    proposals = asyncio.run(_call_mcp_tool(mcp, "memory.dream", {}))
    report = asyncio.run(
        _call_mcp_tool(
            mcp,
            "memory.dream_apply",
            {"proposals": proposals, "approved_ids": [proposals[0]["id"]]},
        )
    )

    assert {"memory.dream", "memory.dream_apply"}.issubset(tool_names)
    assert report["forgotten"] == 1
    assert engine.store.get(record.id) is None


async def _list_mcp_tool_names(mcp: Any) -> set[str]:
    async with Client(mcp) as client:
        tools = await client.list_tools()
        return {tool.name for tool in tools}


async def _call_mcp_tool(mcp: Any, name: str, arguments: dict[str, Any]) -> Any:
    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments)
        return result.data
