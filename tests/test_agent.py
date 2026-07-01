from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from memory_agent.agent import MemoryAgent
from memory_agent.engine import MemoryEngine
from memory_agent.qwen import QwenClient, ToolCall, TransientQwenError
from memory_agent.store import MemoryStore


class ScriptedQwen:
    def __init__(self, turns: list[Any]) -> None:
        self.turns = turns
        self.chat_calls = 0

    def embed(self, text: str) -> list[float]:
        lowered = text.lower()
        return [
            float(lowered.count("tea")),
            float(lowered.count("coffee")),
            float(lowered.count("python")),
            float(lowered.count("jazz")),
        ]

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> Any:
        self.chat_calls += 1
        if self.turns:
            return self.turns.pop(0)
        return SimpleNamespace(content="done", tool_calls=[])


def make_engine(qwen: Any) -> MemoryEngine:
    return MemoryEngine(qwen=qwen, store=MemoryStore(location=":memory:"))


def test_agent_executes_recall_then_returns_final_answer() -> None:
    qwen = ScriptedQwen(
        [
            SimpleNamespace(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_recall",
                        name="recall",
                        arguments={"query": "tea", "token_budget": 128},
                    )
                ],
            ),
            SimpleNamespace(content="Ryan prefers tea.", tool_calls=[]),
        ]
    )
    engine = make_engine(qwen)
    engine.write("Ryan prefers tea.", type="preference", subject="drink")

    result = MemoryAgent(engine).run("What does Ryan prefer?")

    assert result.answer == "Ryan prefers tea."
    assert result.tool_calls_made == ["recall"]
    assert any("tea" in memory["text"].lower() for memory in result.memories)


def test_agent_executes_remember_and_persists_fact() -> None:
    qwen = ScriptedQwen(
        [
            SimpleNamespace(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_remember",
                        name="remember",
                        arguments={
                            "text": "Ryan likes jazz while coding.",
                            "type": "preference",
                            "subject": "music",
                        },
                    )
                ],
            ),
            SimpleNamespace(content="Stored.", tool_calls=[]),
        ]
    )
    engine = make_engine(qwen)

    result = MemoryAgent(engine).run("Remember that Ryan likes jazz while coding.")

    assert result.answer == "Stored."
    assert result.tool_calls_made == ["remember"]
    assert any(
        record.text == "Ryan likes jazz while coding." for record in engine.store.list_records()
    )


def test_agent_stops_at_max_iters_with_best_effort_answer() -> None:
    class LoopingQwen(ScriptedQwen):
        def __init__(self) -> None:
            super().__init__([])

        def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
        ) -> Any:
            self.chat_calls += 1
            return SimpleNamespace(
                content="Still checking memory.",
                tool_calls=[
                    ToolCall(
                        id=f"call_{self.chat_calls}",
                        name="recall",
                        arguments={"query": "tea"},
                    )
                ],
            )

    qwen = LoopingQwen()
    engine = make_engine(qwen)

    result = MemoryAgent(engine, max_iters=3).run("What does Ryan prefer?")

    assert result.answer == "Still checking memory."
    assert result.tool_calls_made == ["recall", "recall", "recall"]
    assert qwen.chat_calls == 3


@dataclass
class FakeMessage:
    content: str | None
    tool_calls: list[Any] | None = None


class FakeCompletions:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def create(self, **kwargs: Any) -> Any:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return SimpleNamespace(choices=[SimpleNamespace(message=FakeMessage(content=outcome))])


class FakeOpenAIClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(outcomes))


def test_qwen_chat_retries_transient_errors_then_succeeds() -> None:
    client = FakeOpenAIClient(
        [
            TransientQwenError("timeout"),
            TransientQwenError("rate limit"),
            "final answer",
        ]
    )
    qwen = QwenClient(client=client, max_retries=3, backoff_base=0)

    result = qwen.chat([{"role": "user", "content": "hello"}])

    assert result == "final answer"
    assert client.chat.completions.calls == 3


def test_qwen_chat_does_not_retry_auth_errors() -> None:
    client = FakeOpenAIClient([PermissionError("bad key"), "should not be called"])
    qwen = QwenClient(client=client, max_retries=3, backoff_base=0)

    with pytest.raises(PermissionError):
        qwen.chat([{"role": "user", "content": "hello"}])

    assert client.chat.completions.calls == 1


def test_agent_executes_forget_and_removes_memory() -> None:
    qwen = ScriptedQwen(
        [
            SimpleNamespace(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_forget",
                        name="forget",
                        arguments={"subject": "drink", "salience_below": 1.0},
                    )
                ],
            ),
            SimpleNamespace(content="Forgotten.", tool_calls=[]),
        ]
    )
    engine = make_engine(qwen)
    engine.write("Ryan prefers tea.", type="preference", subject="drink", salience=0.5)
    assert any(record.subject == "drink" for record in engine.store.list_records())

    result = MemoryAgent(engine).run("Forget my drink preference.")

    assert result.tool_calls_made == ["forget"]
    assert result.answer == "Forgotten."
    assert not any(record.subject == "drink" for record in engine.store.list_records())


def test_agent_remember_propagates_run_session_id() -> None:
    qwen = ScriptedQwen(
        [
            SimpleNamespace(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_remember",
                        name="remember",
                        arguments={"text": "Ryan uses Python.", "subject": "language"},
                    )
                ],
            ),
            SimpleNamespace(content="Noted.", tool_calls=[]),
        ]
    )
    engine = make_engine(qwen)

    MemoryAgent(engine).run("Remember I use Python.", session_id="sess-1")

    records = [record for record in engine.store.list_records() if record.subject == "language"]
    assert records and records[0].session_id == "sess-1"


def test_agent_final_turn_without_content_falls_back_to_best_effort_string() -> None:
    # the model "gives up": a tool-calling turn, then a final turn with no content.
    # answer must be the prior non-empty content (a str), never None.
    qwen = ScriptedQwen(
        [
            SimpleNamespace(
                content="Let me check.",
                tool_calls=[ToolCall(id="c1", name="recall", arguments={"query": "tea"})],
            ),
            SimpleNamespace(content=None, tool_calls=[]),
        ]
    )
    engine = make_engine(qwen)

    result = MemoryAgent(engine).run("What does Ryan prefer?")

    assert isinstance(result.answer, str)
    assert result.answer == "Let me check."


def test_system_prompt_directs_immediate_persistence_of_corrections() -> None:
    # Live ECS bug: "yes I like anime that was my bad" produced NO tool call — the
    # correction was acknowledged conversationally but never persisted, and it took
    # two more explicit nudges before remember fired. The correction directive in
    # the system prompt IS the fix, so pin its presence in what the model receives.
    class CapturingQwen(ScriptedQwen):
        def __init__(self) -> None:
            super().__init__([SimpleNamespace(content="ok", tool_calls=[])])
            self.seen_system = ""

        def chat(self, messages, tools=None, model=None):
            self.seen_system = messages[0]["content"]
            return super().chat(messages, tools=tools, model=model)

    qwen = CapturingQwen()
    MemoryAgent(make_engine(qwen)).run("hello")

    assert messages_mention_corrections(qwen.seen_system)


def messages_mention_corrections(system_prompt: str) -> bool:
    lowered = system_prompt.lower()
    return "correct" in lowered and "immediately" in lowered and "supersession" in lowered
