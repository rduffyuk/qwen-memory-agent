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
- **Supersession-aware forgetting.** When a new fact contradicts an existing one of
  the same subject/type (e.g. "prefers tea" replacing "prefers coffee"), the old
  record is retired (`superseded_by`) so retrieval stops surfacing the stale value.
- **Budget-constrained recall.** Retrieval scores memories by
  `α·cosine + β·recency + γ·salience` and greedily packs them until a configurable
  token budget is hit — relevant context stays small.
- **Exposed over MCP.** The memory tools are a FastMCP server, so any MCP client
  (Claude, a demo UI) can drive the same memory engine.

### How it's built (architecture)
A FastAPI backend on **Alibaba Cloud ECS** runs the agent loop + a FastMCP server +
the memory engine, backed by **Qdrant**. The agent calls **Qwen Cloud / DashScope**
(reasoning model for the loop, `text-embedding` for vectors) over the
OpenAI-compatible endpoint. The Qwen client has bounded retry/backoff for
resilience.

### Why it should win (maps to the rubric)
- **Technical Depth & Engineering (30%)** — Qwen function-calling tool-use, a
  FastMCP integration, and a benchmark with real performance-optimization numbers.
- **Innovation & AI Creativity (30%)** — supersession-aware forgetting +
  budget-constrained recall, clean modular architecture, dependency-injected/mockable
  Qwen client, retry/backoff error handling.
- **Problem Value & Impact (25%)** — memory is the universal agent pain point;
  MIT-licensed, productisable.
- **Presentation & Documentation (15%)** — architecture diagram + a benchmark curve,
  not just "it remembered my name."

### The benchmark (the proof)
Synthetic multi-session personas state preferences, **update** some (the
supersession test), and inject distractors; a held-out query set asks for the
*current* preference. We score four systems — **B0** no-memory, **B1**
full-history-stuffing, **B2** naive top-k RAG, **B3** ours (salience + recency +
supersession) — on recall accuracy, **staleness rate** (using a superseded fact —
lower is better), and a **context-efficiency curve** (accuracy at 512/1k/2k-token
budgets). Win condition: **B3 matches or beats B1/B2 on accuracy at a fixed small
budget, with the lowest staleness.**

> _Live results from the graded run go here (table + `context_efficiency.png`)._

### Built with
Python · FastAPI · FastMCP · Qdrant · `openai` SDK → Qwen Cloud / DashScope
(reasoning + `text-embedding`) · pytest (fully offline test suite, zero-spend).

### Alibaba Cloud usage
- Backend deployed on **ECS** (see `deploy/ecs_setup.md`).
- Qwen Cloud / DashScope APIs in [`src/memory_agent/qwen.py`](../src/memory_agent/qwen.py).

---

## Submission checklist
- [x] Public repo + visible MIT license
- [x] Code file using Alibaba Cloud APIs → `src/memory_agent/qwen.py`
- [ ] Deploy-proof recording (backend on ECS) — **manual**
- [ ] Architecture diagram (visual) — *in README*
- [ ] ~3-min demo video (YouTube/Vimeo, public) — **manual**
- [x] Text description (above)
- [x] Track identified: Track 1
- [ ] (Optional) Blog/social post for the Blog Prize
