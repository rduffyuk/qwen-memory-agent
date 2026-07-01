from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from memory_agent.api import create_app
from memory_agent.engine import MemoryEngine
from memory_agent.qwen import QwenClient
from memory_agent.store import MemoryStore


class FakeCompletions:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses

    def create(self, **kwargs: Any) -> Any:
        return self.responses.pop(0)


class FakeEmbeddings:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses

    def create(self, **kwargs: Any) -> Any:
        return self.responses.pop(0)


class FakeOpenAIClient:
    def __init__(self, *, chat_responses: list[Any], embedding_responses: list[Any]) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(chat_responses))
        self.embeddings = FakeEmbeddings(embedding_responses)


def _usage(
    *,
    prompt_tokens: int,
    total_tokens: int,
    completion_tokens: int | None = None,
) -> SimpleNamespace:
    values = {"prompt_tokens": prompt_tokens, "total_tokens": total_tokens}
    if completion_tokens is not None:
        values["completion_tokens"] = completion_tokens
    return SimpleNamespace(**values)


def _chat_response(
    content: str | None,
    *,
    model: str,
    usage: Any | None,
    tool_calls: list[Any] | None = None,
) -> SimpleNamespace:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls or []))
        ],
        model=model,
    )
    if usage is not None:
        response.usage = usage
    return response


def _embedding_response(*, model: str, usage: Any | None) -> SimpleNamespace:
    response = SimpleNamespace(
        data=[SimpleNamespace(embedding=[1.0, 0.0])],
        model=model,
    )
    if usage is not None:
        response.usage = usage
    return response


def _tool_call(name: str, arguments: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"call_{name}",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def test_qwen_usage_summary_accumulates_chat_and_embedding_by_model() -> None:
    fake = FakeOpenAIClient(
        chat_responses=[
            _chat_response(
                "answer",
                model="qwen-plus-actual",
                usage=_usage(prompt_tokens=10, completion_tokens=4, total_tokens=14),
            )
        ],
        embedding_responses=[
            _embedding_response(
                model="text-embedding-v3-actual",
                usage=_usage(prompt_tokens=6, total_tokens=6),
            )
        ],
    )
    qwen = QwenClient(client=fake)

    assert qwen.chat([{"role": "user", "content": "hello"}]) == "answer"
    assert qwen.embed("hello") == [1.0, 0.0]

    assert qwen.usage_summary() == {
        "total_calls": 2,
        "prompt_tokens": 16,
        "completion_tokens": 4,
        "total_tokens": 20,
        "by_model": {
            "qwen-plus-actual": {
                "calls": 1,
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 14,
            },
            "text-embedding-v3-actual": {
                "calls": 1,
                "prompt_tokens": 6,
                "completion_tokens": 0,
                "total_tokens": 6,
            },
        },
    }


def test_qwen_response_without_usage_leaves_totals_unchanged() -> None:
    fake = FakeOpenAIClient(
        chat_responses=[
            _chat_response(
                "counted",
                model="qwen-plus",
                usage=_usage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
            ),
            _chat_response("uncounted", model="qwen-plus", usage=None),
        ],
        embedding_responses=[],
    )
    qwen = QwenClient(client=fake)

    assert qwen.chat([{"role": "user", "content": "hello"}]) == "counted"
    assert qwen.chat([{"role": "user", "content": "hello again"}]) == "uncounted"

    assert qwen.usage_summary()["total_calls"] == 1
    assert qwen.usage_summary()["total_tokens"] == 5


def test_qwen_derives_total_tokens_when_usage_omits_it() -> None:
    # When the API returns usage without a total_tokens field, the client must
    # derive it as prompt + completion. Pins the fallback branch in _record_usage
    # so a '+' -> '-' mutant (which would report 5, not 15) dies.
    usage_without_total = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    fake = FakeOpenAIClient(
        chat_responses=[_chat_response("derived", model="qwen-plus", usage=usage_without_total)],
        embedding_responses=[],
    )
    qwen = QwenClient(client=fake)

    assert qwen.chat([{"role": "user", "content": "hello"}]) == "derived"

    summary = qwen.usage_summary()
    assert summary["total_tokens"] == 15
    assert summary["by_model"]["qwen-plus"]["total_tokens"] == 15


def test_usage_route_returns_summary_or_zero_fallback() -> None:
    fake = FakeOpenAIClient(
        chat_responses=[],
        embedding_responses=[
            _embedding_response(
                model="text-embedding-v3",
                usage=_usage(prompt_tokens=7, total_tokens=7),
            )
        ],
    )
    qwen = QwenClient(client=fake)
    qwen.embed("tracked")
    tracked_client = TestClient(
        create_app(MemoryEngine(qwen=qwen, store=MemoryStore(location=":memory:")))
    )

    response = tracked_client.get("/usage")

    assert response.status_code == 200
    assert response.json()["total_tokens"] == 7
    assert response.json()["by_model"]["text-embedding-v3"]["calls"] == 1

    class NoUsageQwen:
        def embed(self, text: str) -> list[float]:
            return [0.0, 1.0]

        def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
        ) -> str:
            return "ok"

    fallback_client = TestClient(
        create_app(MemoryEngine(qwen=NoUsageQwen(), store=MemoryStore(location=":memory:")))
    )

    assert fallback_client.get("/usage").json() == {
        "total_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "by_model": {},
    }


def test_chat_response_includes_request_usage_delta() -> None:
    fake = FakeOpenAIClient(
        chat_responses=[
            _chat_response(
                None,
                model="qwen-plus",
                usage=_usage(prompt_tokens=11, completion_tokens=2, total_tokens=13),
                tool_calls=[
                    _tool_call(
                        "recall",
                        '{"query": "tea", "token_budget": 128}',
                    )
                ],
            ),
            _chat_response(
                "Ryan prefers tea.",
                model="qwen-plus",
                usage=_usage(prompt_tokens=17, completion_tokens=5, total_tokens=22),
            ),
        ],
        embedding_responses=[
            _embedding_response(
                model="text-embedding-v3",
                usage=_usage(prompt_tokens=3, total_tokens=3),
            ),
            _embedding_response(
                model="text-embedding-v3",
                usage=_usage(prompt_tokens=4, total_tokens=4),
            ),
        ],
    )
    engine = MemoryEngine(qwen=QwenClient(client=fake), store=MemoryStore(location=":memory:"))
    engine.write("Ryan prefers tea.", type="preference", subject="drink")
    client = TestClient(create_app(engine))

    response = client.post("/chat", json={"message": "What does Ryan prefer?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "Ryan prefers tea."
    assert response.json()["usage"] == {
        "calls": 3,
        "prompt_tokens": 32,
        "completion_tokens": 7,
        "total_tokens": 39,
    }
