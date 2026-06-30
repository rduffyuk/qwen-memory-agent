from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from openai import OpenAI

DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DEFAULT_CHAT_MODEL = "qwen-plus"
DEFAULT_EMBED_MODEL = "text-embedding-v3"


class QwenClient:
    def __init__(
        self,
        client: Any | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        chat_model: str = DEFAULT_CHAT_MODEL,
        embed_model: str = DEFAULT_EMBED_MODEL,
    ) -> None:
        self.chat_model = chat_model
        self.embed_model = embed_model
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

    def chat(self, messages: Sequence[dict[str, str]], model: str | None = None) -> str:
        response = self.client.chat.completions.create(
            model=model or self.chat_model,
            messages=list(messages),
        )
        content = response.choices[0].message.content
        return content or ""

    def embed(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model=self.embed_model,
            input=[text],
        )
        return list(response.data[0].embedding)
