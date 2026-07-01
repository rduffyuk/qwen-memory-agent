from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from memory_agent.engine import MemoryEngine


def create_mcp_server(engine: MemoryEngine) -> FastMCP:
    mcp = FastMCP("qwen-memory-agent")

    @mcp.tool(name="memory.remember")
    def remember(
        text: str,
        type: str = "fact",
        subject: str | None = None,
        salience: float = 0.5,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        return engine.write(
            text,
            type=type,
            subject=subject,
            salience=salience,
            session_id=session_id,
        ).model_dump(mode="json")

    @mcp.tool(name="memory.recall")
    def recall(query: str, token_budget: int | None = None) -> list[dict[str, Any]]:
        return [
            record.model_dump(mode="json")
            for record in engine.retrieve(query, token_budget=token_budget)
        ]

    @mcp.tool(name="memory.forget")
    def forget(
        record_id: str | None = None,
        ttl_seconds: int | None = None,
        salience_below: float | None = None,
        subject: str | None = None,
    ) -> dict[str, int]:
        return {
            "forgotten": engine.forget(
                record_id=record_id,
                ttl_seconds=ttl_seconds,
                salience_below=salience_below,
                subject=subject,
            )
        }

    @mcp.tool(name="memory.stats")
    def stats() -> dict[str, int]:
        return engine.store.stats()

    @mcp.tool(name="memory.export")
    def export() -> dict[str, Any]:
        return {
            "markdown": engine.export_markdown(),
            "json": engine.export_json(),
        }

    @mcp.tool(name="memory.import")
    def import_memory(
        version: int = 1, records: list[dict[str, Any]] | None = None
    ) -> dict[str, int]:
        return {"imported": engine.import_json({"version": version, "records": records or []})}

    return mcp
