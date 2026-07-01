from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from memory_agent.engine import MemoryEngine
from memory_agent.qwen import ChatTurn, ToolCall


@dataclass(frozen=True)
class AgentResult:
    answer: str
    tool_calls_made: list[str]
    memories: list[dict[str, Any]]


class MemoryAgent:
    def __init__(self, engine: MemoryEngine, *, max_iters: int = 4) -> None:
        self.engine = engine
        self.max_iters = max(1, max_iters)

    def run(
        self,
        user_message: str,
        *,
        session_id: str | None = None,
        token_budget: int | None = None,
    ) -> AgentResult:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You can use memory tools when helpful. Recall before answering if stored "
                    "context may matter, remember durable user facts, and forget only when asked."
                ),
            },
            {"role": "user", "content": user_message},
        ]
        tool_calls_made: list[str] = []
        memories: list[dict[str, Any]] = []
        best_effort_answer = ""

        for _ in range(self.max_iters):
            turn = _coerce_turn(self.engine.qwen.chat(messages, tools=_tool_specs()))
            if turn.content:
                best_effort_answer = turn.content
            if not turn.tool_calls:
                return AgentResult(
                    answer=turn.content or best_effort_answer,
                    tool_calls_made=tool_calls_made,
                    memories=memories,
                )

            messages.append(_assistant_tool_call_message(turn))
            for tool_call in turn.tool_calls:
                tool_calls_made.append(tool_call.name)
                result = self._execute_tool_call(
                    tool_call,
                    session_id=session_id,
                    token_budget=token_budget,
                )
                if tool_call.name == "recall" and isinstance(result, list):
                    memories = result
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.name,
                        "content": json.dumps(result),
                    }
                )

        return AgentResult(
            answer=best_effort_answer,
            tool_calls_made=tool_calls_made,
            memories=memories,
        )

    def _execute_tool_call(
        self,
        tool_call: ToolCall,
        *,
        session_id: str | None,
        token_budget: int | None,
    ) -> Any:
        arguments = tool_call.arguments
        if tool_call.name == "remember":
            record = self.engine.write(
                str(arguments["text"]),
                type=str(arguments.get("type", "fact")),
                subject=arguments.get("subject"),
                salience=float(arguments.get("salience", 0.5)),
                session_id=arguments.get("session_id") or session_id,
            )
            return record.model_dump(mode="json")

        if tool_call.name == "recall":
            records = self.engine.retrieve(
                str(arguments["query"]),
                token_budget=_resolve_token_budget(arguments.get("token_budget"), token_budget),
            )
            return [record.model_dump(mode="json") for record in records]

        if tool_call.name == "forget":
            return {
                "forgotten": self.engine.forget(
                    record_id=arguments.get("record_id"),
                    ttl_seconds=arguments.get("ttl_seconds"),
                    salience_below=arguments.get("salience_below"),
                    subject=arguments.get("subject"),
                )
            }

        return {"error": f"unknown tool: {tool_call.name}"}


def _resolve_token_budget(tool_budget: Any, request_budget: int | None) -> int | None:
    budgets = []
    for value in (tool_budget, request_budget):
        if value is not None:
            budgets.append(int(value))
    return min(budgets) if budgets else None


def _coerce_turn(value: Any) -> ChatTurn:
    if isinstance(value, ChatTurn):
        return value
    if isinstance(value, str):
        return ChatTurn(content=value, tool_calls=[])
    return ChatTurn(
        content=getattr(value, "content", None),
        tool_calls=list(getattr(value, "tool_calls", [])),
    )


def _assistant_tool_call_message(turn: ChatTurn) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": turn.content,
        "tool_calls": [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": json.dumps(tool_call.arguments),
                },
            }
            for tool_call in turn.tool_calls
        ],
    }


def _tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "remember",
                "description": "Persist a durable memory fact.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "type": {"type": "string", "default": "fact"},
                        "subject": {"type": "string"},
                        "salience": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "session_id": {"type": "string"},
                    },
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "recall",
                "description": "Retrieve relevant memories for a query.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "token_budget": {"type": "integer", "minimum": 1},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "forget",
                "description": "Delete memories by id, age, salience threshold, or subject.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "record_id": {"type": "string"},
                        "ttl_seconds": {"type": "integer", "minimum": 0},
                        "salience_below": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "subject": {"type": "string"},
                    },
                },
            },
        },
    ]
