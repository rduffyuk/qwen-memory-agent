from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

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

    def _get_client(self) -> QwenClient:
        if self._client is None:
            self._client = QwenClient()
        return self._client


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    token_budget: int = 1024


class ChatResponse(BaseModel):
    answer: str
    tool_calls_made: list[str]
    memories: list[dict[str, Any]]


def create_app(engine: MemoryEngine | None = None) -> FastAPI:
    app = FastAPI(title="qwen-memory-agent")
    resolved_engine = engine or MemoryEngine(qwen=LazyQwenClient(), store=MemoryStore())
    app.state.engine = resolved_engine
    app.state.mcp = create_mcp_server(resolved_engine)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        result = MemoryAgent(resolved_engine).run(request.message, session_id=request.session_id)
        return ChatResponse(
            answer=result.answer,
            tool_calls_made=result.tool_calls_made,
            memories=result.memories,
        )

    return app


app = create_app()
