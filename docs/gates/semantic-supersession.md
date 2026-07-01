# Gate spec: semantic supersession (similarity-based forgetting)

**Goal:** Retire a prior memory when a new fact is *vector-similar* to it, not only
when the `(subject, type)` strings match exactly. Fixes the live-agent gap where
Qwen assigns different `subject`s to equivalent facts (e.g. "morning beverage
preference" vs "morning beverage"), leaving stale records active. Pure Python +
existing embeddings; no new deps.

**Jira:** VW-1090 (use this key; do NOT create a new issue).
**Repo:** this one (`~/qwen-memory-agent`, branch `main`). Public MIT repo.

## Required Codex lane contract
Follow the local AGENTS.md rules supplied by the runner. Use the VW-1090 key.
Do NOT delete, rename, skip, xfail, or weaken any existing test or assertion —
the ENTIRE current suite (incl. `tests/test_benchmark.py`, which locks the
context-efficiency curve) must stay green. No unrelated refactors. Preserve
provenance/vault rules.

## Files in scope (modify ONLY these)
- `src/memory_agent/engine.py`
- `src/memory_agent/store.py` (add ONE read-only similarity helper)
- `src/memory_agent/api.py` (ONE line: read the threshold from env for the default engine)
- `tests/test_engine.py` (ADD tests only)

**Do NOT** touch `benchmark/`, `models.py`, `qwen.py`, `mcp_server.py`, `dream.py`,
`agent.py`.

## Design

### 1. Store helper (`store.py`)
- `most_similar_active(self, vector, *, type, exclude_id, min_cosine) -> MemoryRecord | None`:
  among **active** records (`superseded_by is None`) with matching `type`, excluding
  `exclude_id`, return the one with the highest `_cosine(vector, stored_vector)` **iff**
  that cosine `>= min_cosine`; else `None`. Read-only (reuses the module `_cosine`).

### 2. Engine (`engine.py`)
- Constructor gains `supersede_threshold: float = 0.9`, stored as `self.supersede_threshold`.
- In `write()`, AFTER embedding the new record and AFTER the existing exact
  `active_by_subject_type` supersession loop, add a semantic pass:
  - `match = self.store.most_similar_active(vector, type=record.type,
    exclude_id=record.id, min_cosine=self.supersede_threshold)`
  - if `match` is not None AND `match.superseded_by is None` (not already retired this
    write) AND `match.id != record.id`: `self.store.mark_superseded(match.id, record.id)`.
  - Retire at most ONE record via this pass (the single most similar). The exact-match
    loop still runs first and is unchanged.
- Order matters: embed, then exact supersession, then upsert the new record, then the
  semantic pass — OR keep the current embed→exact→upsert and run the semantic pass on
  the already-stored vectors. Ensure the new record is upserted before the semantic
  pass so `most_similar_active` can `exclude_id=record.id`. Keep the return value =
  the upserted new record.

### 3. API (`api.py`)
- Where the DEFAULT engine is built (`MemoryEngine(qwen=LazyQwenClient(), store=MemoryStore())`),
  pass `supersede_threshold=float(os.getenv("SUPERSEDE_THRESHOLD", "0.9"))` so the live
  box can be tuned via `.env` without a code change. Import `os` if needed. Do not change
  any route.

## Acceptance — gate: `uv run pytest -q` (FULL suite, must pass, FULLY OFFLINE)
Existing tests unchanged + NEW tests in `tests/test_engine.py` (use a fake embedder that
returns caller-controlled vectors so cosines are deterministic):
1. **Different-subject paraphrase is retired:** write A (subject "s1"), then B (subject
   "s2", DIFFERENT string) whose vector has cosine ≥ threshold to A → A is
   `superseded_by == B.id` even though subjects differ.
2. **Distinct low-similarity fact is NOT retired:** write A, then C (orthogonal vector,
   cosine 0) → A stays active (`superseded_by is None`), both retrievable.
3. **Type guard:** write A (type "fact"), then D with an identical/high-cosine vector but
   type "preference" → A is NOT retired (semantic pass is same-type only).
4. **Threshold is honoured:** with a low `supersede_threshold` a moderate-cosine pair
   retires; with a high threshold the same pair does not (pins the constant, not just its sign).
5. The existing supersession test (exact subject+type coffee→tea) and the retrieve/ranking
   tests still pass.

## Constraints
- No live network in tests; no secrets. Deps stay within `pyproject.toml`. Format with
  `black` (line-length 100, target py311) + `isort`. Scope tightly.
