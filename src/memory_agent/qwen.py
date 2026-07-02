from __future__ import annotations

import json
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any

from openai import OpenAI

DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DEFAULT_CHAT_MODEL = "qwen-plus"
DEFAULT_EMBED_MODEL = "text-embedding-v3"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ChatTurn:
    content: str | None
    tool_calls: list[ToolCall]


class TransientQwenError(RuntimeError):
    """Test-friendly marker for retryable injected client failures."""


class QwenClient:
    def __init__(
        self,
        client: Any | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        chat_model: str | None = None,
        embed_model: str | None = None,
        max_retries: int = 3,
        backoff_base: float = 0.1,
    ) -> None:
        # Env-overridable so a deployment can swap models without a code change.
        self.chat_model = chat_model or os.getenv("QWEN_CHAT_MODEL", DEFAULT_CHAT_MODEL)
        self.embed_model = embed_model or os.getenv("QWEN_EMBED_MODEL", DEFAULT_EMBED_MODEL)
        self.max_retries = max(1, max_retries)
        self.backoff_base = max(0.0, backoff_base)
        self._usage = _zero_usage_summary()
        if client is not None:
            self.client = client
            return

        resolved_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not resolved_key:
            raise RuntimeError(
                "DASHSCOPE_API_KEY is required unless an OpenAI-compatible client is injected"
            )
        self.client = OpenAI(
            api_key=resolved_key,
            base_url=base_url or os.getenv("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL),
        )

    def chat(
        self,
        messages: Sequence[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> str | ChatTurn:
        request: dict[str, Any] = {
            "model": model or self.chat_model,
            "messages": list(messages),
        }
        if tools is not None:
            request["tools"] = tools

        response = self._with_retries(
            lambda: self.client.chat.completions.create(**request),
        )
        self._record_usage(response, request["model"])
        turn = _normalize_chat_turn(response.choices[0].message)
        if tools is None:
            return turn.content or ""
        return turn

    def embed(self, text: str) -> list[float]:
        response = self._with_retries(
            lambda: self.client.embeddings.create(
                model=self.embed_model,
                input=[text],
            )
        )
        self._record_usage(response, self.embed_model)
        return list(response.data[0].embedding)

    def usage_summary(self) -> dict[str, Any]:
        return {
            "total_calls": self._usage["total_calls"],
            "prompt_tokens": self._usage["prompt_tokens"],
            "completion_tokens": self._usage["completion_tokens"],
            "total_tokens": self._usage["total_tokens"],
            "by_model": {model: values.copy() for model, values in self._usage["by_model"].items()},
        }

    def _record_usage(self, response: Any, model: str) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return

        prompt_tokens = int(_get_attr_or_key(usage, "prompt_tokens") or 0)
        completion_tokens = int(_get_attr_or_key(usage, "completion_tokens") or 0)
        raw_total_tokens = _get_attr_or_key(usage, "total_tokens")
        total_tokens = (
            int(raw_total_tokens)
            if raw_total_tokens is not None
            else prompt_tokens + completion_tokens
        )
        response_model = str(getattr(response, "model", None) or model)

        self._usage["total_calls"] += 1
        self._usage["prompt_tokens"] += prompt_tokens
        self._usage["completion_tokens"] += completion_tokens
        self._usage["total_tokens"] += total_tokens

        by_model = self._usage["by_model"].setdefault(
            response_model,
            {
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )
        by_model["calls"] += 1
        by_model["prompt_tokens"] += prompt_tokens
        by_model["completion_tokens"] += completion_tokens
        by_model["total_tokens"] += total_tokens

    def _with_retries(self, call: Any) -> Any:
        for attempt in range(self.max_retries):
            try:
                return call()
            except Exception as exc:
                if _is_auth_error(exc) or not _is_transient_error(exc):
                    raise
                if attempt == self.max_retries - 1:
                    raise
                delay = self.backoff_base * (2**attempt)
                if delay > 0:
                    time.sleep(delay)
        raise RuntimeError("retry loop exhausted unexpectedly")


def _zero_usage_summary() -> dict[str, Any]:
    return {
        "total_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "by_model": {},
    }


def _normalize_chat_turn(message: Any) -> ChatTurn:
    content = _get_attr_or_key(message, "content")
    raw_tool_calls = _get_attr_or_key(message, "tool_calls") or []
    return ChatTurn(
        content=content,
        tool_calls=[_normalize_tool_call(raw_call) for raw_call in raw_tool_calls],
    )


def _normalize_tool_call(raw_call: Any) -> ToolCall:
    function = _get_attr_or_key(raw_call, "function") or {}
    name = _get_attr_or_key(function, "name") or _get_attr_or_key(raw_call, "name")
    raw_arguments = _get_attr_or_key(function, "arguments") or _get_attr_or_key(
        raw_call,
        "arguments",
    )
    return ToolCall(
        id=str(_get_attr_or_key(raw_call, "id") or ""),
        name=str(name or ""),
        arguments=_parse_arguments(raw_arguments),
    )


def _parse_arguments(raw_arguments: Any) -> dict[str, Any]:
    if raw_arguments is None:
        return {}
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if isinstance(raw_arguments, str):
        try:
            parsed = json.loads(raw_arguments)
        except JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _get_attr_or_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _is_auth_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in {401, 403}:
        return True
    if isinstance(exc, PermissionError):
        return True
    name = exc.__class__.__name__.lower()
    return "auth" in name or "permission" in name


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, (TransientQwenError, TimeoutError, ConnectionError)):
        return True
    status_code = getattr(exc, "status_code", None)
    if status_code in {408, 409, 429, 500, 502, 503, 504}:
        return True
    name = exc.__class__.__name__.lower()
    return any(marker in name for marker in ("timeout", "connection", "ratelimit", "rate_limit"))
