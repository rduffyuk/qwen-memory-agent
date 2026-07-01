# Hackathon QA review — VW-1090

Date: 2026-07-01
Branch: `review/hackathon-harden`

## Ranked findings

### Critical — live demo crashed when persistence parent path did not exist

- Evidence: `src/memory_agent/store.py:185` writes snapshots on mutation. Live validation with `.env` set to `MEMORY_PERSIST_PATH=/root/qwen-memory-agent/memory.json` returned HTTP 500 on the first `/chat`; traceback failed in `_save()` before writing `memory.json.tmp`.
- Failing scenario: valid ECS-style persistence path, parent directory absent. First memory write crashes the demo instead of creating the snapshot path.
- Change: `_save()` now creates the parent directory before the atomic temp-file write (`src/memory_agent/store.py:185-194`). Added regression coverage for missing parents (`tests/test_persistence.py:100-108`).
- Residual note: unwritable paths still fail, correctly. For local live validation I overrode `MEMORY_PERSIST_PATH` to `/tmp/qwen-memory-agent-live-memory.json`; ECS docs now use `$PWD/memory.json` (`deploy/ecs_setup.md:39-43`).

### High — Qdrant was a write mirror, not the retrieval index

- Evidence: the submission claims Qdrant backing (`docs/SUBMISSION.md:57-60`, `README.md:35`), but pre-fix `MemoryStore.search()` ranked against the private Python `_vectors` dict. Clearing `_vectors` after a Qdrant upsert caused search to fail.
- Failing scenario: the vector index was rebuilt in Qdrant but not actually queried by retrieval, weakening the "Qdrant-backed" technical-depth claim.
- Change: `MemoryStore.search()` now queries Qdrant via `query_points()` and maps result ids back to typed records (`src/memory_agent/store.py:59-85`). Added a regression test that clears `_vectors` and still expects Qdrant search to work (`tests/test_persistence.py:33-43`).

### High — `/chat` accepted `token_budget` but did not enforce it

- Evidence: `ChatRequest.token_budget` existed, but pre-fix `api.chat()` did not pass it to `MemoryAgent`, and `MemoryAgent` only used a model-supplied tool argument.
- Failing scenario: a user sends `/chat {"token_budget": 1}`; if Qwen omits `token_budget` in its `recall` tool call, recall can use the engine default and exceed the route-level cap.
- Change: `api.chat()` now passes the request cap (`src/memory_agent/api.py:124-131`), and `MemoryAgent` uses the smaller of the request cap and any model-supplied recall budget (`src/memory_agent/agent.py:23-29`, `src/memory_agent/agent.py:98-123`). Added an API regression test where the tool omits the budget (`tests/test_api.py:99-107`).

### Medium — empty `/dream` spent a Qwen call for no possible proposal

- Evidence: pre-fix `DreamLoop.dream()` built a prompt even when `store.list_records()` was empty.
- Failing scenario: demo starts with an empty store and `/dream` burns live tokens, then validates all hallucinated ids away.
- Change: `DreamLoop.dream()` now returns `[]` before calling Qwen when there are no active records (`src/memory_agent/dream.py:39-42`). Added no-spend behavior coverage (`tests/test_dream.py:52-58`).

### Medium — docs contained stale/offline-hostile commands and ambiguous wording

- Evidence: README/submission/gate specs used bare `uv run pytest` or `uv run python -m benchmark.run`, which can false-fail offline. The dreaming loop was described as an "offline Qwen pass", ambiguous with zero-network/offline tests.
- Failing scenario: a judge or maintainer follows the docs on a machine without dependency sync/network and gets a false failure; "offline Qwen" can be read as no Qwen API usage.
- Change: docs now use `PYTHONPATH=src uv run --no-sync ...` for offline test/benchmark commands (`README.md:73-82`, `docs/SUBMISSION.md:87`). Dreaming wording is now "out-of-band Qwen pass" (`README.md:19`, `docs/SUBMISSION.md:47-50`). `.env.example` uses a non-secret placeholder and documents runtime knobs (`.env.example:1-8`).

## Claims-vs-code trace

| Claim | Code | Test / validation |
|---|---|---|
| Agentic memory via Qwen function-calling (`README.md:12`, `docs/SUBMISSION.md:24-26`) | Agent loop/tool execution in `src/memory_agent/agent.py:23-78`; Qwen tool-call normalization in `src/memory_agent/qwen.py:66-86` | `tests/test_agent.py` covers recall, remember, forget, retry, session id; live DashScope follow-up called `recall` and answered "Your morning drink is tea." |
| Supersession-aware forgetting, exact + semantic (`README.md:13`, `docs/SUBMISSION.md:27-31`) | Write path embeds, exact subject/type retires prior, semantic same-type pass marks `superseded_by` in `src/memory_agent/engine.py:64-78`; store mutation in `src/memory_agent/store.py:99-110` | `tests/test_engine.py` covers exact, semantic, same-type only, threshold, default threshold; live export showed coffee `superseded_by` the tea record |
| Graded decay + reinforce-on-recall (`README.md:14`, `docs/SUBMISSION.md:32-34`) | Reinforcement in `src/memory_agent/engine.py:220-229`; half-life decay in `src/memory_agent/engine.py:232-241` | `tests/test_decay.py` covers pinned preferences, half-life math, reinforcement, decayed forget |
| Typed retrieval (`README.md:15`, `docs/SUBMISSION.md:35-38`) | Hybrid score and type prior in `src/memory_agent/engine.py:196-205`; one-active-per-subject/type veto in `src/memory_agent/engine.py:207-218` | `tests/test_typed_retrieval.py` covers type prior ties, imported stale sibling veto, distinct subjects, default delta, `prefer_type` |
| Budget-constrained recall (`README.md:16`, `docs/SUBMISSION.md:39-41`) | Pack loop in `src/memory_agent/engine.py:80-109`; route/agent cap propagation in `src/memory_agent/api.py:124-131` and `src/memory_agent/agent.py:98-123` | `tests/test_engine.py` budget test plus new `/chat` cap regression (`tests/test_api.py:99-107`) |
| Portable memory export/import (`README.md:17`, `docs/SUBMISSION.md:42-43`) | JSON/Markdown export/import in `src/memory_agent/engine.py:148-189`; HTTP routes in `src/memory_agent/api.py:136-146`; MCP tools in `src/memory_agent/mcp_server.py:62-73` | `tests/test_memory_io.py` covers JSON vector preservation, no re-embedding, Markdown active-only export, HTTP and MCP import/export |
| Persistent across restarts (`README.md:18`, `docs/SUBMISSION.md:44-46`) | Atomic save/load in `src/memory_agent/store.py:173-214`; env wiring in `src/memory_agent/api.py:108-111` | `tests/test_persistence.py`; offline Uvicorn survival restarted a server against the same snapshot and recovered the tea memory |
| Dreaming loop validates live ids (`README.md:19`, `docs/SUBMISSION.md:47-50`) | Proposal parse/validation in `src/memory_agent/dream.py:39-81`; apply revalidates against current record ids in `src/memory_agent/dream.py:83-105`; HTTP/MCP surfaces in `src/memory_agent/api.py:148-157`, `src/memory_agent/mcp_server.py:75-85` | `tests/test_dream.py` covers hallucinated ids dropped, no mutation during dream, approved-only apply, MCP/HTTP dream tools, empty-store no-spend |
| Token/model observability (`README.md:20`, `docs/SUBMISSION.md:51-52`) | Usage accumulation in `src/memory_agent/qwen.py:98-139`; `/usage` and per-chat delta in `src/memory_agent/api.py:120-134` | `tests/test_usage.py`; live `/usage` moved from 0 to 10 calls / 3604 total tokens, models `qwen-plus` and `text-embedding-v3` |
| Reproducible benchmark (`README.md:21`, `docs/SUBMISSION.md:77-98`) | Offline `KeywordQwen` in `benchmark/run.py:54-65`; shared packing in `benchmark/baselines.py:21-36`; scorer in `benchmark/score.py:7-29` | `PYTHONPATH=src uv run --no-sync python -m benchmark.run` reproduced the published table exactly; `tests/test_benchmark.py` and `tests/test_score.py` pass |
| Eight FastMCP tools (`docs/SUBMISSION.md:53-54`) | `memory.remember`, `memory.recall`, `memory.forget`, `memory.stats`, `memory.export`, `memory.import`, `memory.dream`, `memory.dream_apply` in `src/memory_agent/mcp_server.py:15-85` | Runtime `fastmcp.Client.list_tools()` returned exactly 8 tools |
| Qwen Cloud/DashScope vectors use text embedding (`docs/SUBMISSION.md:59-60`) | `DEFAULT_EMBED_MODEL = "text-embedding-v3"` and `client.embeddings.create(...)` in `src/memory_agent/qwen.py:13-15`, `src/memory_agent/qwen.py:88-96` | `tests/test_usage.py` asserts embedding model usage; live `/usage` included `text-embedding-v3` |

No claimed feature remains unwired after this pass. The ECS deploy-proof and demo video remain manual, and `docs/SUBMISSION.md:111-119` correctly leaves them unchecked.

## Benchmark integrity

Command run:

```bash
PYTHONPATH=src uv run --no-sync python -m benchmark.run
```

Published table reproduced exactly:

- B1: 8 `0.00 / 0.50`, 16 `0.00 / 0.50`, 32 `1.00 / 0.50`, 64 `1.00 / 0.50`
- B2: 8 `0.50 / 0.00`, 16 `1.00 / 0.00`, 32 `1.00 / 0.50`, 64 `1.00 / 0.50`
- B3: 8/16/32/64 all `1.00 / 0.00`

Determinism / zero-spend: benchmark uses `KeywordQwen` (`benchmark/run.py:54-65`) and does not instantiate `QwenClient`; it only writes `benchmark/results/latest.json` (ignored by git).

Baseline sanity: B1 and B2 share the same `_pack()` budget accounting as B3's engine packing (`benchmark/baselines.py:21-36`). B1 chronological dumping and B2 keyword overlap are plausible naive baselines, not direct strawmen. Residual risk: the benchmark is intentionally small (one persona), so it proves the supersession/context-efficiency thesis but not broad real-world recall robustness.

## Over-mock hunt

- Semantic supersession exercises real `MemoryEngine.write()` and `MemoryStore.mark_superseded()` with deterministic vectors, not stubbed retire logic.
- Typed retrieval imports real records/vectors and runs real `MemoryEngine.retrieve()`, including hybrid scoring and stale-sibling veto.
- Decay tests call real `effective_salience()`, `retrieve()`, reinforcement, and `forget(decayed_below=...)`.
- Persistence tests use real `MemoryStore` with `QdrantClient(location=":memory:")`; added coverage proves search now uses Qdrant, not a mocked vector cache.
- Default-path coverage exists for `SUPERSEDE_THRESHOLD` (`tests/test_api.py:110-116`, plus engine default tests) and `MEMORY_PERSIST_PATH` (`tests/test_persistence.py:119-128`).

## Demo survival

Offline mocked-Qwen Uvicorn run passed:

- empty store export showed `0 active, 0 superseded`
- `/dream` on zero memories returned `{"proposals": []}` without increasing Qwen call count
- coffee -> tea `/chat` sequence retired coffee and recalled tea
- `/usage`, `/memory/export`, `/dream`, and `/dream/apply` all worked
- restart against the same snapshot recovered the tea memory
- semantic boundary cosine `0.748` retired the old record when `SUPERSEDE_THRESHOLD=0.74`

Live DashScope run passed after overriding the local Mac validation path to a writable `/tmp` snapshot:

- `/chat` "Remember I prefer coffee..." called `remember`
- `/chat` "Actually I prefer tea now..." called `remember`, answered tea, and export showed coffee superseded by tea
- fresh-session `/chat` "What is my morning drink?" called `recall`, returned the persisted tea memory, and answered tea
- `/usage` total moved from 0 to 10 calls / 3604 tokens; models included `qwen-plus` and `text-embedding-v3`
- `/dream` returned one valid `resalience` proposal
- server was killed after validation; port 8000 was clear

## Lose-nothing sweep

- `.env` is ignored; `.env.example` contains placeholders only (`.env.example:1-8`).
- No tracked secret was found in the repo scan. The live API key was not printed.
- Docs now use offline-safe commands and exact `text-embedding-v3` wording.
- `src/memory_agent/qwen.py` is the Alibaba/DashScope API file via OpenAI-compatible `base_url` and embedding/chat calls (`src/memory_agent/qwen.py:13-96`).
