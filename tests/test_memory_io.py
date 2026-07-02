from __future__ import annotations

import asyncio
from typing import Any

from fastapi.testclient import TestClient
from fastmcp import Client

from memory_agent.api import create_app
from memory_agent.engine import MemoryEngine
from memory_agent.mcp_server import create_mcp_server
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


class RaisingQwen:
    def embed(self, text: str) -> list[float]:
        raise AssertionError("import_json must not embed records")


def make_engine(qwen: Any | None = None) -> MemoryEngine:
    return MemoryEngine(
        qwen=qwen or FakeQwen(),
        store=MemoryStore(location=":memory:"),
        token_budget=128,
    )


def seed_engine(engine: MemoryEngine) -> None:
    engine.write("Ryan prefers coffee in the morning.", type="preference", subject="drink")
    engine.write("Ryan prefers tea in the morning.", type="preference", subject="drink")
    engine.write("Ryan likes jazz while coding.", type="preference", subject="music")
    engine.write("Ryan writes Python tests.", type="fact", subject="testing")


def test_json_round_trip_preserves_ids_supersession_and_retrieval_without_reembedding() -> None:
    source = make_engine()
    seed_engine(source)
    snapshot = source.export_json()
    source_top = source.retrieve("tea preference", token_budget=128)[0].text

    imported = make_engine(qwen=RaisingQwen())
    imported_count = imported.import_json(snapshot)
    imported.qwen = FakeQwen()

    assert imported_count == len(snapshot["records"])
    assert {record.id for record in imported.store.list_records(include_superseded=True)} == {
        record.id for record in source.store.list_records(include_superseded=True)
    }

    source_superseded = [
        record
        for record in source.store.list_records(include_superseded=True)
        if record.superseded_by
    ]
    imported_superseded = [
        record
        for record in imported.store.list_records(include_superseded=True)
        if record.superseded_by
    ]
    assert len(source_superseded) == 1
    assert [(record.id, record.superseded_by) for record in imported_superseded] == [
        (record.id, record.superseded_by) for record in source_superseded
    ]
    assert imported.retrieve("tea preference", token_budget=128)[0].text == source_top


def test_markdown_export_lists_only_active_records_and_counts_superseded() -> None:
    engine = make_engine()
    seed_engine(engine)
    markdown = engine.export_markdown()
    lines = markdown.splitlines()
    bullets = [line for line in lines if line.startswith("- ")]

    assert lines[0] == "# Memory export — 3 active, 1 superseded"
    assert len(bullets) == 3
    assert all(" · sal " in bullet for bullet in bullets)
    assert all(" · used " in bullet for bullet in bullets)
    assert any("[preference · sal 0.50 · used 0] Ryan prefers tea" in bullet for bullet in bullets)
    assert all("Ryan prefers coffee" not in bullet for bullet in bullets)


def test_api_exports_markdown_and_json_then_imports_into_fresh_app() -> None:
    source = make_engine()
    seed_engine(source)
    source_client = TestClient(create_app(source))

    export_response = source_client.get("/memory/export")

    assert export_response.status_code == 200
    payload = export_response.json()
    assert set(payload) == {"markdown", "json"}

    fresh = make_engine(qwen=RaisingQwen())
    fresh_client = TestClient(create_app(fresh))
    import_response = fresh_client.post("/memory/import", json=payload["json"])

    assert import_response.status_code == 200
    body = import_response.json()
    assert body["imported"] == 4
    assert body["stats"] == {
        "total": 4,
        "active": 3,
        "superseded": 1,
        "embed_model_mismatch": 0,
    }


def test_mcp_memory_export_and_import_are_registered_and_functional() -> None:
    source = make_engine()
    seed_engine(source)
    exported = asyncio.run(_call_mcp_tool(create_mcp_server(source), "memory.export", {}))

    assert set(exported) == {"markdown", "json"}

    fresh = make_engine(qwen=RaisingQwen())
    mcp = create_mcp_server(fresh)
    tool_names = asyncio.run(_list_mcp_tool_names(mcp))
    imported = asyncio.run(_call_mcp_tool(mcp, "memory.import", exported["json"]))

    assert {"memory.export", "memory.import"}.issubset(tool_names)
    assert imported == {"imported": 4}


async def _list_mcp_tool_names(mcp: Any) -> set[str]:
    async with Client(mcp) as client:
        tools = await client.list_tools()
        return {tool.name for tool in tools}


async def _call_mcp_tool(mcp: Any, name: str, arguments: dict[str, Any]) -> Any:
    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments)
        return result.data
