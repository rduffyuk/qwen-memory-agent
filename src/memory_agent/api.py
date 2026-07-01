from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from memory_agent.agent import MemoryAgent
from memory_agent.engine import MemoryEngine
from memory_agent.mcp_server import create_mcp_server
from memory_agent.qwen import ChatTurn, QwenClient
from memory_agent.store import MemoryStore


class LazyQwenClient:
    def __init__(self) -> None:
        self._client: QwenClient | None = None

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


def create_app(engine: MemoryEngine | None = None) -> FastAPI:
    app = FastAPI(title="qwen-memory-agent")
    resolved_engine = engine or MemoryEngine(qwen=LazyQwenClient(), store=MemoryStore())
    app.state.engine = resolved_engine
    app.state.mcp = create_mcp_server(resolved_engine)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/usage")
    def usage() -> dict[str, Any]:
        return _usage_summary(resolved_engine.qwen)

    @app.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        before = _usage_summary(resolved_engine.qwen)
        result = MemoryAgent(resolved_engine).run(request.message, session_id=request.session_id)
        after = _usage_summary(resolved_engine.qwen)
        return ChatResponse(
            answer=result.answer,
            tool_calls_made=result.tool_calls_made,
            memories=result.memories,
            usage=_usage_delta(before, after),
        )

    return app


app = create_app()
