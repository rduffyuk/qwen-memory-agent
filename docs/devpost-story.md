## What inspired it

Every agent that talks to a user more than once hits the same wall: where do
memories live, when should stale ones be dropped, and how do you fit the *right*
memories into a limited context window? Most "memory" demos either stuff the
whole history into the prompt — expensive, and it drags in outdated facts — or do
naive top-k RAG, which has no notion of "this preference was replaced last week."
I wanted to treat memory as a **measurable engineering problem**, not a party
trick, and prove the behaviour with numbers.

## What it does

**Qwen MemoryAgent** is a persistent-memory agent on Qwen Cloud that accumulates
experience across sessions and makes increasingly accurate decisions:

- **Agentic memory via Qwen function-calling.** The agent itself decides when to
  call `remember` / `recall` / `forget` through Qwen's tool-calling — it's an
  agent *with* memory, not a database with an LLM bolted on.
- **Supersession-aware forgetting.** When a new fact contradicts an older one,
  the old record is retired (`superseded_by`) so retrieval stops surfacing the
  stale value. An exact `(subject, type)` match handles the clean case; a
  **cosine-similarity** pass catches near-paraphrases the model filed under a
  different subject.
- **Graded decay + reinforce-on-recall.** Memories fade over time on a per-type
  half-life *unless* recall reinforces them — so the working set stays focused on
  what's still used, and truly stale memories are forgotten. Pinned types (user
  preferences) never decay.
- **Budget-constrained recall.** Retrieval scores memories by
  \\( \alpha\cdot\text{cosine} + \beta\cdot\text{recency} + \gamma\cdot\text{effective salience} + \delta\cdot\text{type prior} \\)
  and greedily packs them until a configurable token budget is hit.
- **Real token observability.** Every answer reports what it actually cost
  (`GET /usage` + a `usage` field per `/chat`), using Qwen's real `usage` object
  rather than estimates.
- **Portable memory.** Export the store to a human-readable `MEMORY.md` index and
  a JSON snapshot; import to restore it — memory survives restarts and moves
  between machines.
- **MCP-native.** The memory tools are a FastMCP server, so any MCP client can
  drive the same engine.

## How I built it

A FastAPI backend runs the agent loop, a FastMCP server, and the memory engine,
backed by **Qdrant**, deployed on **Alibaba Cloud ECS** (Singapore). It calls
**Qwen Cloud / DashScope** over the OpenAI-compatible endpoint — `qwen-plus` for
the reasoning loop, `text-embedding-v3` for vectors. The whole test suite is
fully offline (mocked Qwen + in-memory Qdrant), so development cost **zero API
credits**. I worked architecture-first on one model and handed bounded, spec'd
implementation to a second via a handoff lane gated by pytest, test-integrity,
and **mutation testing**.

## The benchmark (the proof)

Synthetic multi-session personas state preferences, **update** some (the
supersession test), and inject distractors; a held-out query set asks for the
*current* preference. Four systems are scored — **B0** no-memory, **B1**
full-history stuffing, **B2** naive top-k, **B3** ours — on context recall
(retrieval-level, model-free) and **staleness rate** (retrieved context contains
a superseded fact; lower is better), across a shrinking token budget with all
systems competing under the same ceiling.

| Budget | 8 | 16 | 32 | 64 |
|---|:--:|:--:|:--:|:--:|
| B1 full-history — recall / stale | 0.000 / 0.250 | 0.375 / 0.250 | 0.958 / 0.250 | 1.000 / 0.250 |
| B2 naive top-k — recall / stale | 0.875 / 0.125 | 1.000 / 0.250 | 1.000 / 0.250 | 1.000 / 0.250 |
| **B3 ours — recall / stale** | **1.000 / 0.000** | **1.000 / 0.000** | **1.000 / 0.000** | **1.000 / 0.000** |

*(B0 no-memory scores 0.000 recall at every budget — it retrieves nothing.)*

B3 holds context recall **1.000** and staleness **0.000** at every budget. The
sharpest finding is what happens to the baseline: **B2's staleness *rises* with
budget** (0.125 → 0.250). With no supersession, giving naive RAG more room
actively pulls retired facts back in. Only B3 stays current *and* small —
measured, not asserted.

## The harder proof (including the misses)

Recall benchmarks saturate, so I also measured whether the agent *uses* memory.
Ten multi-session scenarios seed constraints (including superseded ones) and
demand a decision in a **later** session, each graded by three independent
oracles: the decision outcome, the store state via `/memory/export`, and
recall-before-decision in the tool-call trace. A lucky guess that never consulted
memory scores zero.

Live on the ECS deployment, against real Qwen with a fresh store:
**task_success 0.60** — inside the 40–60% band MemoryArena (arXiv 2602.16313)
reports for agents that ace passive recall. I publish the number *and* the full
triage: three named defects — decision turns that skip recall, a generic-subject
supersession collision, and a sub-threshold paraphrase band — each with a
designed fix in the README and `docs/design/memory-governance.md`.

The gap between recall 1.000 and active use 0.60 **is** the finding. Measured,
not asserted, including the misses.

## What I learned

- **Mutation testing earns its keep.** All-passing behavioural tests still left
  numeric constants (decay half-lives, a token-fallback branch) un-pinned — the
  mutation gate caught each one.
- **Benchmark honesty is a discipline.** My first graded run *disproved* the
  headline because a distractor's keyword collided with the staleness metric. The
  engine was right; the measuring stick was contaminated. Fixing the instrument,
  not the result, is the job.
- **Subject assignment is the weak joint.** Supersession depends on the model
  choosing a stable `subject` key, and it doesn't always — which is exactly why
  the cosine path exists, and exactly where the remaining failures live.
- **Two different token numbers do two different jobs** — `tiktoken` for packing
  a budget, the API's real `usage` for measuring spend. Conflating them hides
  cost.

## Challenges

Keeping the whole thing testable and zero-spend on a finite free credit budget;
a cardless ECS deploy (solved via the free trial); and shipping to Singapore over
UK-latency SSH.
