# Gate spec — qwen-memory-agent core (VW-1090)

**Jira:** VW-1090 (use this key; do not create a new issue).
**Repo:** fresh, MIT, public. NOT the private Rootweaver platform — import nothing from it.
**Full design (context, not required reading):** the vault build-spec; this gate file is authoritative for scope.

## Goal
Build the core of a persistent-memory agent on Qwen Cloud: a memory engine (write / retrieve / forget with supersession + token-budget packing), a FastMCP server exposing `memory.*` tools, a Qdrant store wrapper, a mockable Qwen client, and a reproducible benchmark with baselines. **All tests run fully offline (mock Qwen, in-memory Qdrant) — zero API spend.**

## Files in scope (create)
- `src/memory_agent/models.py` — pydantic `MemoryRecord {id, text, type, subject, salience, ts, session_id, superseded_by}`.
- `src/memory_agent/qwen.py` — thin client over `openai` SDK pointed at `DASHSCOPE_BASE_URL`; `chat()` + `embed()`. **Must be injectable/mockable** (accept a client or be monkeypatchable); reads key from env, never hardcoded.
- `src/memory_agent/store.py` — Qdrant wrapper; `QdrantClient(location=":memory:")` path for tests; upsert / search / delete / mark_superseded.
- `src/memory_agent/engine.py` — `write()` (extract salient facts → embed → upsert), `retrieve()` (hybrid score `α·cosine + β·recency + γ·salience`, greedily pack to a **token budget** via tiktoken, never exceed it), `forget()` (TTL/decay evict + **supersession**: on write, a contradicting fact of the same `subject`/`type` retires the old one via `superseded_by`).
- `src/memory_agent/mcp_server.py` — FastMCP server; tools `remember / recall / forget / stats`.
- `src/memory_agent/api.py` — FastAPI app mounting a `/chat` loop + health; wire the MCP server.
- `benchmark/{generate,baselines,run,score}.py` — synthetic personas + multi-session scripts (some preferences updated = supersession test) + distractors; baselines **B0** no-memory, **B1** full-history, **B2** naive top-k RAG, **B3** ours; metrics recall accuracy, **staleness rate**, context-efficiency (accuracy @ 512/1k/2k token budgets). Writes JSON to `benchmark/results/`.
- `tests/` — the gate.

## Acceptance criteria — gate: `PYTHONPATH=src uv run --no-sync pytest -q tests/` (must pass, fully offline)
Tests MUST cover, at minimum:
1. **supersession** — writing a contradicting fact of the same subject/type retires the prior one (`superseded_by` set; retrieve no longer returns the stale value).
2. **budget packing** — `retrieve()` output never exceeds the configured token budget (assert on a case where candidates exceed it).
3. **ranking** — a relevant memory ranks above an injected distractor.
4. **scorer** — `score.py` computes recall + staleness correctly on a fixed fixture.

## Constraints
- **Do NOT delete, rename, skip, xfail, or weaken any existing test or assertion.**
- No live network in tests (mock `qwen.py`, in-memory Qdrant). No secrets in code; key only via env.
- Keep deps within the declared `pyproject.toml` set (add to `[project.dependencies]` only if unavoidable).
- Format changed Python with `black` + `isort` (line-length 100). Scope tightly; no unrelated refactors.
