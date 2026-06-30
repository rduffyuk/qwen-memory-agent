from __future__ import annotations

from fastapi.testclient import TestClient

from memory_agent.api import create_app
from memory_agent.engine import MemoryEngine
from memory_agent.store import MemoryStore


class FakeQwen:
    """Offline stand-in: deterministic embeddings, echo-free canned chat reply."""

    def embed(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count("tea")), float(lowered.count("coffee"))]

    def chat(self, messages: list[dict[str, str]], model: str | None = None) -> str:
        return "fake-answer"


def _engine() -> MemoryEngine:
    return MemoryEngine(qwen=FakeQwen(), store=MemoryStore(location=":memory:"))


def test_health_returns_ok() -> None:
    client = TestClient(create_app(_engine()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_answer_and_relevant_memories() -> None:
    engine = _engine()
    engine.write("Ryan prefers tea.", type="preference", subject="drink")
    client = TestClient(create_app(engine))

    response = client.post("/chat", json={"message": "What about tea?", "token_budget": 128})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "fake-answer"
    assert any("tea" in memory["text"].lower() for memory in body["memories"])
