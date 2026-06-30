from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from memory_agent.engine import MemoryEngine
from memory_agent.mcp_server import create_mcp_server
from memory_agent.qwen import QwenClient
from memory_agent.store import MemoryStore


class LazyQwenClient:
    def __init__(self) -> None:
        self._client: QwenClient | None = None

    def chat(self, messages: list[dict[str, str]], model: str | None = None) -> str:
        return self._get_client().chat(messages, model=model)

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
        memories = resolved_engine.retrieve(request.message, token_budget=request.token_budget)
        context = "\n".join(record.text for record in memories)
        answer = resolved_engine.qwen.chat(
            [
                {
                    "role": "system",
                    "content": "Use the supplied memories when they are relevant.",
                },
                {"role": "user", "content": f"Memories:\n{context}\n\nUser:\n{request.message}"},
            ]
        )
        return ChatResponse(
            answer=answer,
            memories=[record.model_dump(mode="json") for record in memories],
        )

    return app


app = create_app()
