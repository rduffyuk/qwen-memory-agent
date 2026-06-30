# AGENTS.md — qwen-memory-agent

Fresh public repo (GitHub, **MIT**) for the Qwen Cloud Hackathon Track 1 entry.
**This is NOT the private Rootweaver platform** — do not import, reference, or paste anything from it.

## Hard rules
- **Zero secrets in code.** The DashScope API key lives ONLY in `.env` (gitignored). Read it via env vars (`DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`). Never hardcode, log, or print the key. Provide a `.env.example` with placeholder values only.
- **Mock-first / zero-spend tests.** Tests MUST NOT make live network calls to Qwen/DashScope. The Qwen client (`qwen.py`) must be injectable/mockable so the whole engine + MCP + scorer are testable offline. Use Qdrant local in-memory mode (`QdrantClient(location=":memory:")`) in tests — no server, no Docker.
- **Don't weaken tests.** Never delete, rename, skip, or `xfail` an existing test or assertion.
- **Scope discipline.** Implement only the gate spec. No unrelated refactors. Keep all runtime deps inside the already-declared `pyproject.toml` set; if you truly need another, add it to `[project.dependencies]`.
- **Format before finishing:** `black` + `isort` (configured in `pyproject.toml`, line-length 100).

## Layout
```
src/memory_agent/   api.py · mcp_server.py · engine.py · qwen.py · store.py · models.py
benchmark/          generate.py · baselines.py · run.py · score.py · results/
tests/              unit tests (the gate: `pytest -q tests/`)
deploy/             ecs_setup.md · docker-compose.yml
```

## Gate
`pytest -q tests/` must pass, fully offline. Tests cover at minimum:
1. supersession retires the prior fact of the same subject/type;
2. budget-packing never exceeds the configured token limit;
3. retrieve ranks a relevant memory above a distractor;
4. the scorer computes recall + staleness correctly on a fixture.
