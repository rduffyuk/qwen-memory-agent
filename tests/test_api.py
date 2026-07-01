from __future__ import annotations

from fastapi.testclient import TestClient

from memory_agent.api import create_app
from memory_agent.engine import MemoryEngine
from memory_agent.qwen import ToolCall
from memory_agent.store import MemoryStore


class FakeQwen:
    """Offline stand-in: deterministic embeddings, echo-free canned chat reply."""

    def __init__(self) -> None:
        self.chat_calls = 0

    def embed(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count("tea")), float(lowered.count("coffee"))]

    def chat(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
        model: str | None = None,
    ) -> object:
        self.chat_calls += 1
        if self.chat_calls == 1:
            return type(
                "Turn",
                (),
                {
                    "content": None,
                    "tool_calls": [
                        ToolCall(
                            id="call_recall",
                            name="recall",
                            arguments={"query": "What about tea?", "token_budget": 128},
                        )
                    ],
                },
            )()
        return type("Turn", (), {"content": "fake-answer", "tool_calls": []})()


class RecallWithoutBudgetQwen(FakeQwen):
    def chat(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
        model: str | None = None,
    ) -> object:
        self.chat_calls += 1
        if self.chat_calls == 1:
            return type(
                "Turn",
                (),
                {
                    "content": None,
                    "tool_calls": [
                        ToolCall(
                            id="call_recall",
                            name="recall",
                            arguments={"query": "What about tea?"},
                        )
                    ],
                },
            )()
        return type("Turn", (), {"content": "fake-answer", "tool_calls": []})()


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
    assert body["tool_calls_made"] == ["recall"]
    assert any("tea" in memory["text"].lower() for memory in body["memories"])


def test_chat_request_token_budget_caps_agent_recall_when_tool_omits_budget() -> None:
    engine = MemoryEngine(qwen=RecallWithoutBudgetQwen(), store=MemoryStore(location=":memory:"))
    engine.write("Ryan prefers tea.", type="preference", subject="drink")
    client = TestClient(create_app(engine))

    response = client.post("/chat", json={"message": "What about tea?", "token_budget": 1})

    assert response.status_code == 200
    assert response.json()["memories"] == []


def test_create_app_default_supersede_threshold_is_0_9(monkeypatch) -> None:
    # Pin the API's env default: with SUPERSEDE_THRESHOLD unset, the default engine
    # must use 0.9 (a mutation of the "0.9" fallback literal to "1.9" would disable
    # semantic supersession on the live box and otherwise go untested).
    monkeypatch.delenv("SUPERSEDE_THRESHOLD", raising=False)
    app = create_app()
    assert app.state.engine.supersede_threshold == 0.9


def test_dream_apply_malformed_proposal_returns_422() -> None:
    client = TestClient(create_app(_engine()), raise_server_exceptions=False)

    response = client.post(
        "/dream/apply",
        json={
            "proposals": [
                {
                    "id": "bad-1",
                    "kind": "forget",
                    "target_ids": "not-a-list",
                    "rationale": "Malformed client payload.",
                }
            ],
            "approved_ids": ["bad-1"],
        },
    )

    assert response.status_code == 422


def test_memory_import_malformed_payload_returns_400() -> None:
    client = TestClient(create_app(_engine()), raise_server_exceptions=False)

    response = client.post("/memory/import", json={"records": "not-a-list"})

    assert response.status_code == 400
    assert "records list" in response.json()["detail"]
