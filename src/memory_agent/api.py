from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Load DASHSCOPE_* from a local .env when running the server (e.g. `uv run uvicorn`)
# so the key doesn't have to be re-exported into every shell. Real environment
# variables always win (override=False); a no-op if python-dotenv or .env is absent.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is an optional convenience
    pass

from memory_agent.agent import MemoryAgent
from memory_agent.dream import DreamLoop, DreamProposal
from memory_agent.engine import MemoryEngine
from memory_agent.mcp_server import create_mcp_server
from memory_agent.qwen import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_EMBED_MODEL,
    ChatTurn,
    QwenClient,
)
from memory_agent.store import MemoryStore


class LazyQwenClient:
    def __init__(self) -> None:
        self._client: QwenClient | None = None
        self.chat_model = DEFAULT_CHAT_MODEL
        self.embed_model = DEFAULT_EMBED_MODEL

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> str | ChatTurn:
        return self._get_client().chat(messages, tools=tools, model=model)

    def embed(self, text: str) -> list[float]:
        return self._get_client().embed(text)

    def usage_summary(self) -> dict[str, Any]:
        if self._client is None:
            return _zero_usage_summary()
        return self._client.usage_summary()

    def _get_client(self) -> QwenClient:
        if self._client is None:
            self._client = QwenClient()
            self.chat_model = self._client.chat_model
            self.embed_model = self._client.embed_model
        return self._client


def _zero_usage_summary() -> dict[str, Any]:
    return {
        "total_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "by_model": {},
    }


def _zero_usage_delta() -> dict[str, int]:
    return {
        "calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def _usage_summary(qwen: Any) -> dict[str, Any]:
    if not hasattr(qwen, "usage_summary"):
        return _zero_usage_summary()
    return qwen.usage_summary()


def _usage_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    return {
        "calls": int(after["total_calls"]) - int(before["total_calls"]),
        "prompt_tokens": int(after["prompt_tokens"]) - int(before["prompt_tokens"]),
        "completion_tokens": int(after["completion_tokens"]) - int(before["completion_tokens"]),
        "total_tokens": int(after["total_tokens"]) - int(before["total_tokens"]),
    }


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    token_budget: int = 1024


class ChatResponse(BaseModel):
    answer: str
    tool_calls_made: list[str]
    memories: list[dict[str, Any]]
    usage: dict[str, int] = Field(default_factory=_zero_usage_delta)


class DreamProposalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    target_ids: list[str]
    rationale: str
    merged_text: str | None = None
    subject: str | None = None
    type: str | None = None
    new_salience: float | None = None

    def to_proposal(self) -> DreamProposal:
        return DreamProposal(**self.model_dump())


class DreamApplyRequest(BaseModel):
    proposals: list[DreamProposalPayload]
    approved_ids: list[str]


def create_app(engine: MemoryEngine | None = None) -> FastAPI:
    app = FastAPI(title="qwen-memory-agent")
    resolved_engine = engine or MemoryEngine(
        qwen=LazyQwenClient(),
        store=MemoryStore(persist_path=os.getenv("MEMORY_PERSIST_PATH") or None),
        supersede_threshold=float(os.getenv("SUPERSEDE_THRESHOLD", "0.9")),
    )
    app.state.engine = resolved_engine
    app.state.mcp = create_mcp_server(resolved_engine)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", **resolved_engine.stats()}

    @app.get("/demo", response_class=HTMLResponse)
    def demo() -> HTMLResponse:
        # Single-file memory inspector (chat + live store table + dreaming loop).
        # Read per request: trivial cost, and edits show up without a restart.
        page = Path(__file__).with_name("inspector.html")
        return HTMLResponse(page.read_text(encoding="utf-8"))

    @app.get("/usage")
    def usage() -> dict[str, Any]:
        return _usage_summary(resolved_engine.qwen)

    @app.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        before = _usage_summary(resolved_engine.qwen)
        result = MemoryAgent(resolved_engine).run(
            request.message,
            session_id=request.session_id,
            token_budget=request.token_budget,
        )
        after = _usage_summary(resolved_engine.qwen)
        return ChatResponse(
            answer=result.answer,
            tool_calls_made=result.tool_calls_made,
            memories=result.memories,
            usage=_usage_delta(before, after),
        )

    @app.get("/memory/export")
    def export_memory() -> dict[str, Any]:
        return {
            "markdown": resolved_engine.export_markdown(),
            "json": resolved_engine.export_json(),
        }

    @app.post("/memory/import")
    def import_memory(data: dict[str, Any]) -> dict[str, Any]:
        try:
            imported = resolved_engine.import_json(data)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"imported": imported, "stats": resolved_engine.stats()}

    @app.post("/memory/reembed")
    def reembed_memory() -> dict[str, int]:
        try:
            reembedded = resolved_engine.reembed()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"reembedded": reembedded}

    @app.post("/dream")
    def dream() -> dict[str, Any]:
        proposals = DreamLoop(resolved_engine).dream()
        return {"proposals": [asdict(proposal) for proposal in proposals]}

    @app.post("/dream/apply")
    def dream_apply(request: DreamApplyRequest) -> dict[str, Any]:
        proposals = [proposal.to_proposal() for proposal in request.proposals]
        report = DreamLoop(resolved_engine).apply(proposals, request.approved_ids)
        return asdict(report)

    return app


app = create_app()
