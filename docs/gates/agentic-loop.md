# Gate spec — agentic memory loop + Qwen hardening (VW-1090)

**Jira:** VW-1090 (use this key; do not create a new issue).
**Repo:** this one (`~/qwen-memory-agent`, branch `main`). Fresh MIT public repo — import nothing proprietary.
**Why:** judges reward "sophisticated use of QwenCloud APIs (MCP integrations)" + "error handling". Today `/chat` always retrieves — make the agent itself decide, via Qwen function-calling, when to remember/recall/forget. Keep everything offline-testable (zero Qwen spend).

## Goal
Add a Qwen function-calling **agent loop** so the model autonomously invokes the memory tools, and harden the Qwen client with bounded retry/backoff. Wire `/chat` to the loop.

## Files in scope
- `src/memory_agent/qwen.py` — add tool-calling + resilience, keep it mockable:
  - `chat(messages, tools=None, model=None)` returns a normalized object/dataclass `ChatTurn{content: str | None, tool_calls: list[ToolCall]}` where `ToolCall{id, name, arguments: dict}` (parse the OpenAI-compatible `message.tool_calls`). Existing `chat()` callers that pass no tools must still get plain text (keep a `.content` path or a back-compat wrapper) — **do not break existing tests**.
  - `embed()` unchanged.
  - Wrap network calls in bounded retry: configurable `max_retries` (default 3) + exponential backoff with a configurable `backoff_base` (default small; tests pass `backoff_base=0` to avoid sleeping). Retry only transient errors (connection/timeout/rate-limit); never retry on auth errors. Never log the API key.
- `src/memory_agent/agent.py` (new) — `MemoryAgent(engine, *, max_iters=4)`:
  - `run(user_message, *, session_id=None) -> AgentResult{answer: str, tool_calls_made: list[str], memories: list[dict]}`.
  - Builds tool specs for `remember` / `recall` / `forget` (JSON-schema args mirroring the MCP tools), calls `engine.qwen.chat(messages, tools=...)`, executes each returned tool_call against the engine (remember→engine.write, recall→engine.retrieve, forget→engine.forget), appends tool results to the message list, and loops until the model returns a final answer with no tool_calls OR `max_iters` is hit (then return best-effort answer). Record each tool name invoked.
- `src/memory_agent/api.py` — `/chat` uses `MemoryAgent(engine).run(...)`; response includes `answer`, `tool_calls_made`, `memories`. Keep `/health`.
- `tests/test_agent.py` (new) + update `tests/test_api.py` if signature changes.

## Acceptance — gate: `uv run pytest -q tests/` (must pass, FULLY OFFLINE)
New tests MUST cover (with a scripted FakeQwen that returns tool_calls then a final answer — no network):
1. agent executes a model-requested `recall` then returns the model's final answer; `tool_calls_made` includes "recall".
2. agent executes a model-requested `remember` and the fact is persisted (engine.store has it afterward).
3. `max_iters` cap: a FakeQwen that ALWAYS returns a tool_call terminates and returns a best-effort answer (no infinite loop).
4. retry: a FakeQwen client that raises a transient error twice then succeeds is retried (assert final success, `backoff_base=0`); an auth-type error is NOT retried.
5. existing `/chat` still returns an answer + memories (update the smoke test to the new shape).

## Constraints
- **Do NOT delete, rename, skip, xfail, or weaken any existing test or assertion.** All current tests must still pass.
- No live network in tests; mock the Qwen client. No secrets in code; key via env only.
- Keep deps within the declared `pyproject.toml` set. Format with `black` + `isort` (line-length 100). Scope tightly; no unrelated refactors.
