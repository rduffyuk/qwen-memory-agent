# qwen-memory-agent

A **benchmarked, MCP-native persistent-memory agent** built on **Qwen Cloud** (Alibaba Cloud / DashScope). Submitted to the Qwen Cloud Hackathon, **Track 1 — MemoryAgent**.

The agent *itself* decides — via Qwen function-calling — when to remember, recall, or forget. It carries user preferences across sessions, **forgets superseded facts**, and recalls the right memories inside a **tight token budget** — and proves it with numbers against naive baselines.

## Why it's different

Most memory agents are "stuff everything into RAG and hope." This one adds:

- **Agentic memory via Qwen function-calling** — the model invokes `remember` / `recall` / `forget` tools through a real agent loop. It's an agent *with* memory, not a database with an LLM bolted on.
- **Supersession-aware forgetting** — when a new fact contradicts an old one of the same kind, the old record is retired (not just buried under recency).
- **Budget-constrained recall** — retrieval greedily packs the most useful memories until a configurable token budget is hit, so context stays small *and* relevant.
- **A reproducible benchmark** — synthetic multi-session personas, a held-out query set, and baselines (no-memory / full-history / naive-RAG / ours), scored on recall accuracy, **staleness rate**, and a **context-efficiency curve**.

## Architecture

```mermaid
flowchart TB
    U["MCP client / demo UI"]

    subgraph ecs["Alibaba Cloud ECS (Singapore)"]
        API["FastAPI backend<br/>/chat · /health"]
        AGENT["MemoryAgent loop<br/>Qwen function-calling"]
        MCP["FastMCP server<br/>memory.remember / recall / forget / stats"]
        ENG["Memory Engine<br/>write · retrieve · forget<br/>supersession + token-budget packing"]
        QD[("Qdrant<br/>vector store")]
    end

    DS["Qwen Cloud / DashScope-intl<br/>reasoning model + text-embedding"]

    U -->|HTTP| API
    U -.->|MCP| MCP
    API --> AGENT
    AGENT -->|"decides which tool to call"| ENG
    MCP --> ENG
    AGENT <-->|"chat + tool specs"| DS
    ENG <-->|"embed"| DS
    ENG <--> QD
```

The agent loop (`/chat`) lets Qwen choose tool calls; the same memory engine is also exposed directly over MCP for any MCP client. The Qwen client has bounded retry/backoff for resilience.

## Stack

Python · FastAPI · **Qwen function-calling agent loop** · FastMCP · `openai` SDK → DashScope-intl · Qwen text-embedding · Qdrant.

## Quickstart

```bash
uv sync
cp .env.example .env   # set DASHSCOPE_API_KEY + DASHSCOPE_BASE_URL
uv run pytest -q       # tests run fully mocked — zero Qwen credit spend
```

## Benchmark results

Reproducible and **fully offline** — `uv run python -m benchmark.run` uses a deterministic
bag-of-vocabulary embedder, so the harness measures the *memory engine's* ranking +
supersession logic (not embedding noise) and costs **zero Qwen credits**. All three systems
compete under the **same shrinking token budget**, so this is a fair context-efficiency test.

![Context-efficiency curves](benchmark/results/context_efficiency.png)

Recall accuracy and staleness rate (fraction of answers containing a *retired* fact; lower is
better) vs the memory token budget, over the synthetic multi-session persona set in
`benchmark/generate.py`:

| Budget (tokens) | 8 | 16 | 32 | 64 |
|---|:--:|:--:|:--:|:--:|
| B1 full-history — recall / staleness | 0.00 / 0.50 | 0.00 / 0.50 | 1.00 / 0.50 | 1.00 / 0.50 |
| B2 naive top-k — recall / staleness | 0.50 / 0.00 | 1.00 / 0.00 | 1.00 / **0.50** | 1.00 / **0.50** |
| **B3 ours — recall / staleness** | **1.00 / 0.00** | **1.00 / 0.00** | **1.00 / 0.00** | **1.00 / 0.00** |

**B3 holds recall 1.00 and staleness 0.00 at every budget** — it's the only system that recalls
the current preference *and* never re-surfaces the retired one. Two things the naive baselines
can't do:

- **B1** (dump history chronologically) wastes its budget on the oldest facts, so it needs a
  large budget just to recall the current answer — and it permanently carries the stale one.
- **B2** (keyword top-k) *gets staler as the budget grows*: with no notion of "replaced," extra
  budget pulls the retired "coffee" fact back in, so its staleness climbs 0.00 → 0.50.

Only **supersession-aware forgetting + budget-constrained recall** keeps the working set both
correct and small.

## License

MIT — see [LICENSE](LICENSE).
