# Gate spec: token + model usage observability

**Goal:** Capture real token usage + model per Qwen call (the API already returns
`response.usage` + `response.model` — we currently discard it) and surface it, so
the agent reports "how many tokens, which model". Maps Track-1 "efficient memory
handling" — real measured cost, not tiktoken estimates. Pure Python, no new deps.

**Jira:** VW-1090

**Files in scope (modify only these):**
- `src/memory_agent/qwen.py`
- `src/memory_agent/api.py`
- new `tests/test_usage.py`

**Do NOT** touch `engine.py`, `models.py`, `store.py`, `mcp_server.py`,
`agent.py`, `benchmark/`. **Do NOT** delete/rename/weaken any existing test or
assertion. Keep all current tests green. No unrelated refactors. The
`tiktoken` budget-packing in engine.py is unrelated — leave it.

## Design

1. `qwen.py`: add a usage accumulator on `QwenClient`.
   - Internal running tally; `usage_summary() -> dict` returns:
     `{"total_calls": int, "prompt_tokens": int, "completion_tokens": int,
       "total_tokens": int, "by_model": {model: {"calls","prompt_tokens",
       "completion_tokens","total_tokens"}}}`.
   - In `chat()` and `embed()`, after the response returns, read
     `getattr(response, "usage", None)` and `getattr(response, "model", <sent model>)`
     and record. Embedding `usage` has no `completion_tokens` → treat as 0.
   - **Defensive:** if the response has no `usage` (e.g. an injected fake without
     one), record nothing and do NOT crash. Existing behaviour/return values of
     `chat()`/`embed()` are unchanged.

2. `api.py`:
   - `LazyQwenClient` gains `usage_summary()` delegating to its wrapped
     `QwenClient` (return an all-zero summary before the first real call).
   - New route `GET /usage` → returns `engine.qwen.usage_summary()` if the client
     exposes it (`hasattr` guard), else an all-zero summary.
   - `ChatResponse` gains `usage: dict` = the **delta** for that request: snapshot
     `usage_summary()` totals before and after `MemoryAgent(...).run(...)`, return
     the difference (`prompt_tokens`, `completion_tokens`, `total_tokens`, `calls`).
     If the client has no `usage_summary`, return zeros.

## Acceptance criteria (gate: `PYTHONPATH=src uv run --no-sync pytest -q tests/` — ALL pass)

Use a fake OpenAI-compatible client (has `.chat.completions.create` /
`.embeddings.create` returning objects that carry `.usage` + `.model`) injected
into `QwenClient(client=fake)`:
1. After a chat call + an embed call, `usage_summary()` reports correct
   cumulative `total_calls`, `prompt_tokens`, `completion_tokens`,
   `total_tokens`, and a `by_model` split keyed by the returned model names.
2. A response lacking `usage` leaves totals unchanged and does not raise.
3. `GET /usage` on an app whose engine uses a usage-recording fake returns the
   cumulative summary; on a client without `usage_summary` returns all zeros.
4. `POST /chat` response includes `usage` whose `total_tokens` equals the tokens
   consumed during that request (before/after delta).
5. Existing `tests/test_api.py`, `tests/test_agent.py`, `tests/test_qwen*` (if
   any) and all other tests remain green.

## Codex lane contract
Follow the runner's AGENTS.md. Use Jira key VW-1090. Preserve every existing
test/assertion. Keep vault/provenance rules. No unrelated refactors. Commit only
the in-scope files.
