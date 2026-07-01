# Gate spec: typed retrieval — type-aware weighting + retrieval-time supersession veto

**Goal:** Add a *second, independent self-correcting layer* to retrieval: (1) a
canonical memory-type taxonomy with type-aware ranking weight, and (2) a
retrieval-time "one-active-per-(subject,type), keep-newest" veto that catches
stale contradictions the write-time supersession path misses. Maps Track-1
"recall the most critical memories under limited context" + "increasingly
accurate decisions across sessions". Pure Python, no new deps.

**Jira:** VW-1090 (use this key; do NOT create a new issue).
**Repo:** this one (`~/qwen-memory-agent`, current branch). Public MIT repo — import nothing proprietary.

## Why (design rationale — keep this intent)
`MemoryEngine.write()` retires a prior record only when a *new* fact is written
through the engine for the same `(subject, type)`. Records that enter via
`import_json()` call `store.upsert` directly and **bypass** that supersession —
so two contradicting active records for the same `(subject, type)` can coexist
after an import. The retrieval-time veto is an independent re-check of that
invariant: it is one layer catching another layer's miss, not a duplicate knob.
Separately, cosine similarity alone treats a durable `preference` and a throwaway
`episodic` note as equal; the type prior lets a high-value type win ties.

## Files in scope (modify ONLY these)
- `src/memory_agent/engine.py`
- `src/memory_agent/mcp_server.py` (only the `memory.recall` tool signature — optional `prefer_type`)
- `tests/test_typed_retrieval.py` (new)

**Do NOT** touch `benchmark/`, `models.py`, `store.py`, `api.py`, `qwen.py`,
`agent.py`. **Do NOT** delete, rename, skip, xfail, or weaken any existing test
or assertion. Keep the ENTIRE current suite green.

## Design

### 1. Type taxonomy + type-aware weighting (`engine.py`)
- Module constants:
  ```python
  TYPE_PRIORS = {
      "identity": 1.0,
      "preference": 1.0,
      "decision": 1.0,
      "fact": 0.8,
      "episodic": 0.5,
      "chore": 0.3,
  }
  DEFAULT_TYPE_PRIOR = 0.7
  ```
- Module-level `type_prior(record: MemoryRecord) -> float` returning
  `TYPE_PRIORS.get(record.type, DEFAULT_TYPE_PRIOR)`.
- Add a `delta: float = 0.10` constructor kwarg (4th ranking coefficient),
  stored as `self.delta`. Extend `_hybrid_score` to
  `α·cosine + β·recency + γ·effective_salience + δ·type_prior(record)`.
  Keep α/β/γ defaults and existing kwargs unchanged. (All existing tests use a
  single type — `preference` — and distinct subjects, so this term must not
  reorder them; verify by running the suite.)

### 2. Retrieval-time supersession/recency veto (`engine.py`)
- In `retrieve()`, AFTER ranking and BEFORE token-budget packing, apply a veto:
  walk the ranked candidates in score order and, for each `(subject, type)` key,
  keep only the record with the newest `ts`; drop any older sibling as stale.
  Concretely: if two candidates share `(subject, type)`, the one with the smaller
  `ts` is removed from the retrieval set (even if its score is higher). Ties on
  `ts` (equal timestamps) keep the higher-ranked one — do not drop both.
- This runs on the already-active candidate set (superseded records are already
  excluded by the store). It is defense-in-depth for the import path.

### 3. Optional query type biasing
- `retrieve(query, *, token_budget=None, limit=50, prefer_type=None)`: when
  `prefer_type` is a non-None string, add a fixed bonus (e.g. `self.delta`) to the
  score of records whose `type == prefer_type`, so a caller can bias toward a
  type. Default `None` = unchanged behaviour.
- Thread `prefer_type` through `mcp_server.py`'s `memory.recall` tool as an
  optional arg defaulting to `None`.

## Acceptance — gate: `PYTHONPATH=src uv run --no-sync pytest -q tests/` (FULL suite, must pass, FULLY OFFLINE)
New `tests/test_typed_retrieval.py` MUST cover (with a deterministic fake embedder
returning equal vectors where a cosine tie is needed — no network):
1. **Type prior breaks a cosine tie:** two records with identical embeddings but
   different types (`preference` vs `episodic`) → the `preference` ranks first in
   `retrieve()`.
2. **`type_prior` default:** an unknown/uncatalogued type returns
   `DEFAULT_TYPE_PRIOR` exactly, and a known type returns its `TYPE_PRIORS` value
   (assert at least `preference == 1.0` and `chore == 0.3`). (Kills mutants on the
   prior constants.)
3. **Retrieval veto drops the stale same-`(subject,type)` sibling that
   supersession missed:** build an engine, then insert TWO active records for the
   same `(subject, type)` with different text and different `ts` **via
   `engine.import_json(...)`** (the path that bypasses write-time supersession),
   the newer `ts` carrying the current value. `retrieve()` returns ONLY the newer
   record's text; the older value is absent.
4. **Veto keeps distinct subjects:** two active records, same type, DIFFERENT
   subject → both survive retrieval (veto must key on `(subject, type)`, not type
   alone).
5. **`prefer_type` biasing:** with two equal-cosine records of different types,
   passing `prefer_type=<the-lower-prior-type>` promotes that record to first.

## Constraints
- **Do NOT delete, rename, skip, xfail, or weaken any existing test or assertion.**
  The full suite (including `tests/test_benchmark.py`, which locks the B3
  recall/staleness numbers) must stay green — if the veto or δ term changes any
  benchmark number, the design is wrong; fix the code, never the locked test.
- No live network in tests; no secrets in code. Keep deps within the declared
  `pyproject.toml` set. Format with `black` + `isort` (line-length 100). Scope
  tightly — no unrelated refactors.
- Follow the local AGENTS.md rules supplied by the runner; use the VW-1090 key;
  preserve provenance/vault rules.
