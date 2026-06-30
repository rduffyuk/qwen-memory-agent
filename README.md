# qwen-memory-agent

A **benchmarked, MCP-native persistent-memory agent** built on **Qwen Cloud** (Alibaba Cloud / DashScope). Submitted to the Qwen Cloud Hackathon, **Track 1 — MemoryAgent**.

It remembers user preferences across sessions, **forgets superseded facts**, and recalls the right memories inside a **tight token budget** — and proves it with numbers against naive baselines.

## Why it's different

Most memory agents are "stuff everything into RAG and hope." This one adds:

- **Supersession-aware forgetting** — when a new fact contradicts an old one of the same kind, the old record is retired (not just buried under recency).
- **Budget-constrained recall** — retrieval greedily packs the most useful memories until a configurable token budget is hit, so context stays small *and* relevant.
- **A reproducible benchmark** — synthetic multi-session personas, a held-out query set, and baselines (no-memory / full-history / naive-RAG / ours), scored on recall accuracy, **staleness rate**, and a **context-efficiency curve**.

## Architecture

```
            ┌─────────────── Alibaba Cloud ECS VM ───────────────┐
 MCP client │   FastAPI backend                                  │
 (demo /    │     ├─ /chat        (agent loop)                   │
  Claude)   │     ├─ MCP server (FastMCP)  ── memory.* tools     │
     │ MCP  │     │     remember / recall / forget / stats       │
     ▼      │     ├─ Memory Engine  (write / retrieve / forget)  │
 ───────────┼──►  └─ Qdrant (vector store)                       │
            └────────────────────┬───────────────────────────────┘
                                 ▼  OpenAI-compatible API
                    Qwen Cloud / DashScope-intl
                    (qwen reasoning + text-embedding)
```

## Stack

Python · FastAPI · FastMCP · `openai` SDK → DashScope-intl · Qwen text-embedding · Qdrant.

## Quickstart

```bash
uv sync
cp .env.example .env   # set DASHSCOPE_API_KEY + DASHSCOPE_BASE_URL
uv run pytest -q       # tests run fully mocked — zero Qwen credit spend
```

## Benchmark results

_Populated by `benchmark/` once the harness runs. (B3 = ours; lower staleness, higher accuracy at a fixed small budget.)_

## License

MIT — see [LICENSE](LICENSE).
