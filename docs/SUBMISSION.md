# Devpost submission — qwen-memory-agent

**Track:** Track 1 — MemoryAgent
**Repo:** https://github.com/rduffyuk/qwen-memory-agent (public, MIT)

---

## Text description (paste into Devpost "What it does" / description)

**qwen-memory-agent** is a persistent-memory agent on Qwen Cloud that accumulates
experience across sessions, remembers user preferences, **forgets superseded
facts**, and recalls only the most relevant memories within a tight token budget —
and it proves the gain with a reproducible benchmark instead of a single anecdote.

### The problem
Every agent that talks to a user more than once hits the same wall: where do
memories live, when should stale ones be dropped, and how do you fit the *right*
memories into a limited context window? Most demos just stuff the whole history
into the prompt (expensive, and it drags in outdated facts) or do naive top-k RAG
(no notion of "this preference was replaced last week"). This project treats
memory as a first-class, measurable engineering problem.

### What it does
- **Agentic memory via Qwen function-calling.** The agent itself decides when to
  call `remember` / `recall` / `forget` through Qwen's tool-calling — it's an agent
  *with* memory, not a database with an LLM bolted on.
- **Supersession-aware forgetting (exact + semantic).** When a new fact contradicts
  an existing one, the old record is retired (`superseded_by`). Exact `(subject, type)`
  match handles the clean case; a **cosine-similarity** pass (configurable
  `SUPERSEDE_THRESHOLD`) also retires near-paraphrases the model filed under a different
  subject — the case that defeats exact matching in a live agent loop.
- **Graded decay + reinforce-on-recall.** `effective_salience = salience · 0.5^(age /
  half_life)` with per-type half-lives (`preference` pinned); recalling a memory
  refreshes it. Hot memories persist, cold ones fade — *timely forgetting.*
- **Typed retrieval — a second self-correcting layer.** A type-aware ranking prior
  lets a durable `preference` outrank an equal-cosine throwaway note, and a
  retrieval-time "one-active-per-`(subject,type)`, keep-newest" veto catches stale
  contradictions the write path can miss (e.g. imported records).
- **Budget-constrained recall.** Retrieval scores memories by
  `α·cosine + β·recency + γ·effective_salience + δ·type_prior` and greedily packs
  them until a configurable token budget is hit — relevant context stays small.
- **Portable memory.** The whole store round-trips as JSON (vectors preserved, no
  re-embedding) or renders to Markdown — memory moves across sessions and machines.
- **Persistent across restarts.** With `MEMORY_PERSIST_PATH` set, the store writes an
  atomic JSON snapshot on every change and reloads it on startup (rebuilding the vector
  index) — memories survive a full server restart, not just process lifetime.
- **The dreaming loop (propose → approve).** An out-of-band Qwen pass proposes
  consolidations (merge / forget / re-salience); a human approves, then only
  approved proposals are applied. It validates proposals against live record ids, so
  it won't act on its own hallucinations.
- **Token & model observability.** Every Qwen call's token usage is metered per
  model and exposed at `/usage`; `/chat` reports the per-request delta.
- **Exposed over MCP + HTTP.** Eight FastMCP tools and the matching HTTP routes let
  any MCP client (Claude, a demo UI) or plain `curl` drive the same memory engine.

### How it's built (architecture)
A FastAPI backend on **Alibaba Cloud ECS** runs the agent loop, the dreaming loop, a
FastMCP server, and the memory engine, backed by **Qdrant**. The agent and the
dreaming loop both call **Qwen Cloud / DashScope** (reasoning model for the loop,
`text-embedding-v3` for vectors) over the OpenAI-compatible endpoint. The Qwen client
has bounded retry/backoff for resilience and meters token usage on every call. See
`docs/architecture.png` for the rendered diagram.

### Why it should win (maps to the rubric)
- **Technical Depth & Engineering (30%)** — Qwen function-calling tool-use, an
  eight-tool FastMCP integration, graded decay, a two-layer self-correcting
  retrieval path, and a benchmark with real performance-optimization numbers.
- **Innovation & AI Creativity (30%)** — supersession-aware forgetting + typed
  retrieval veto + a human-in-the-loop dreaming loop that refuses to act on
  hallucinated ids; clean modular architecture, dependency-injected/mockable Qwen
  client, retry/backoff error handling.
- **Problem Value & Impact (25%)** — memory is the universal agent pain point;
  portable (export/import) and MIT-licensed, so it's productisable.
- **Presentation & Documentation (15%)** — a rendered architecture diagram + a
  benchmark curve + a fully offline test suite, not just "it remembered my name."

### The benchmark (the proof)
Synthetic multi-session personas state preferences, **update** some (the
supersession test), and inject distractors; a held-out query set asks for the
*current* preference. We score four systems — **B0** no-memory, **B1**
full-history-stuffing, **B2** naive top-k RAG, **B3** ours (salience + recency +
supersession) — on **context recall** (retrieval-level, model-free) and
**staleness rate** (retrieved context contains a superseded fact — lower is better)
across a **shrinking token budget** (8/16/32/64), all systems competing under the
same ceiling. The budget is metered with `tiktoken`'s `gpt-4o-mini` encoding, a
consistent approximation for Qwen context accounting. Win condition: **B3 matches
or beats B1/B2 on context recall at every budget, with the lowest staleness.**

**Graded run** (`PYTHONPATH=src uv run --no-sync python -m benchmark.run`, deterministic + offline, zero spend);
plot at `benchmark/results/context_efficiency.png`:

| Budget | 8 | 16 | 32 | 64 |
|---|:--:|:--:|:--:|:--:|
| B1 full-history — context recall / stale | 0.000 / 0.250 | 0.375 / 0.250 | 0.958 / 0.250 | 1.000 / 0.250 |
| B2 naive top-k — context recall / stale | 0.875 / 0.125 | 1.000 / 0.250 | 1.000 / 0.250 | 1.000 / 0.250 |
| **B3 ours — context recall / stale** | **1.000 / 0.000** | **1.000 / 0.000** | **1.000 / 0.000** | **1.000 / 0.000** |

B3 holds context recall 1.000 / staleness 0.000 at every budget on the expanded
six-persona, 24-query fixture. The sharpest finding still holds but is less dramatic
than the original two-query toy curve: **B2's staleness *rises* with budget**
(0.125 → 0.250, then plateaus) — with no supersession, more context pulls retired
facts back in. Only B3 stays current *and* small — measured, not asserted.

The semantic threshold is validated separately with live DashScope `text-embedding-v3`
cosines in `docs/embedding-validation.md`: supersession pairs scored 0.879-0.908,
while unrelated distractors scored 0.683-0.743. Because one pair landed below the
default `SUPERSEDE_THRESHOLD=0.9`, the threshold is left unchanged but documented as
conservative rather than treated as a proven universal constant.

### Built with
Python · FastAPI · FastMCP · Qdrant · `openai` SDK → Qwen Cloud / DashScope
(reasoning + `text-embedding-v3`) · `tiktoken` (token-budget accounting) · pytest
(fully offline test suite, zero-spend).

### Alibaba Cloud usage
- Backend deployed on **ECS** (see `deploy/ecs_setup.md`).
- Qwen Cloud / DashScope APIs in [`src/memory_agent/qwen.py`](../src/memory_agent/qwen.py).

---

## Submission checklist
- [x] Public repo + visible MIT license
- [x] Code file using Alibaba Cloud APIs → `src/memory_agent/qwen.py`
- [ ] Deploy-proof recording (backend on ECS) — **manual**
- [x] Architecture diagram (visual) → `docs/architecture.png` (+ Mermaid in README)
- [ ] ~3-min demo video (YouTube/Vimeo, public) — **manual**
- [x] Text description (above)
- [x] Track identified: Track 1
- [ ] (Optional) Blog/social post for the Blog Prize
