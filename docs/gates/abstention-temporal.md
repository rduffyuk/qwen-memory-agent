# Gate spec: benchmark abstention + temporal capability cases

**Goal:** Extend the benchmark to cover two abilities the field (LongMemEval) treats
as table stakes but the current curve skips: **abstention** (decline when nothing
relevant is stored) and **temporal separation** (answer "now" vs "before" on
demand). Add the two small engine capabilities these require. Pure Python, offline,
zero Qwen spend.

**Jira:** VW-1090 (use this key; do NOT create a new issue).
**Repo:** this one (`~/qwen-memory-agent`, current branch). Public MIT repo.

## NON-NEGOTIABLE honesty + compatibility constraints
1. **The existing context-efficiency curve must stay byte-identical.** Do NOT change
   `synthetic_personas()`, `BUDGETS`, the `run()` `"baselines"` output section, or any
   number in it. `tests/test_benchmark.py`'s existing tests assert those exact values
   and structure and MUST stay green. Put ALL new work in a SEPARATE code path and a
   NEW top-level output key `"capabilities"`.
2. **Do NOT claim B3 beats B1 on historical recall.** B1 (full history) keeps every
   fact, so it CAN answer historical questions (at full token cost). The temporal
   metric below is a **B3 capability score** (present/past separation), not a race B1
   loses. Comment this rationale in the code.
3. Do NOT delete, rename, skip, xfail, or weaken any existing test or assertion.

## Files in scope (modify ONLY these)
- `src/memory_agent/engine.py`
- `benchmark/generate.py`
- `benchmark/score.py`
- `benchmark/run.py`
- `tests/test_benchmark.py` (ADD tests only)
- `tests/test_engine.py` (ADD tests only, for the two engine capabilities)

**Do NOT** touch `benchmark/baselines.py` signatures used by the curve,
`benchmark/plot.py`, `models.py`, `store.py`, `api.py`, `qwen.py`, `mcp_server.py`,
`dream.py`.

## Design

### 1. Engine capability: relevance floor (`engine.py`)
- `retrieve(self, query, *, token_budget=None, limit=50, prefer_type=None, min_relevance=0.0)`.
- After ranking and BEFORE the supersession veto, drop any candidate whose
  `result.cosine < min_relevance`. **Default `0.0` must not drop anything** (bag
  vectors give cosine ≥ 0), so every existing test AND the locked curve are unchanged.
- If all candidates are dropped, `retrieve` returns `[]` (the agent can then abstain).

### 2. Engine capability: historical recall (`engine.py`)
- `history(self, subject, *, type=None) -> list[MemoryRecord]`: return the
  **superseded** records (`superseded_by is not None`) for `subject` (optionally
  filtered by `type`), sorted by `ts` DESCENDING (most-recently-retired first).
  Read-only — no writes, no reinforce. Uses `store.list_records(include_superseded=True)`.

### 3. Benchmark capability cases (`benchmark/generate.py`)
Add `capability_cases() -> dict[str, list[dict]]` (SEPARATE from `synthetic_personas`):
- Reuse the same stored history as the persona (import it or inline the same
  `morning_drink` coffee→tea supersession + the other facts) so the store is realistic.
- `"abstention"`: one case asking about a subject with NO stored memory, whose query
  text shares **ZERO** words with `_VOCAB`/the stored memories (e.g. "What is today's
  weather forecast?" — note: must not contain "ryan", "prefer", etc., or the bag
  embedder gives it nonzero cosine). Fields: `id`, `query`, `must_not_contain`
  (the list of concrete stored answer tokens like coffee/tea/jazz/python/soda/ruby
  that would indicate a hallucinated answer).
- `"temporal"`: two linked cases on `morning_drink` — a `"present"` case
  (`query`="What does Ryan drink in the morning now?", `expected`="tea",
  `stale`=["coffee"]) and a `"past"` case (`query`="What did Ryan drink in the morning
  before he switched?", `subject`="morning_drink", `expected`="coffee").

### 4. Scoring (`benchmark/score.py`, ADD functions — do not change `score_predictions`)
- `score_abstention(predictions: Mapping[str,str], fixtures) -> {"abstention_accuracy": float}`:
  a case is correct iff the prediction contains NONE of its `must_not_contain` tokens
  (casefold). accuracy = correct / total (0.0 on empty).
- `score_temporal(present_pred: str, past_pred: str, present_fixture, past_fixture) -> {"temporal_accuracy": float}`:
  present correct iff `expected` present AND no `stale` token present; past correct iff
  `expected` present. accuracy = (present_correct + past_correct) / 2.

### 5. Wire into `run()` (`benchmark/run.py`)
- Keep the `"baselines"` curve loop and output EXACTLY as-is.
- Add a capability evaluation at a fixed reference budget (`64`), writing a NEW
  top-level key `"capabilities"`:
  ```json
  "capabilities": {
    "abstention": {"B1": {"abstention_accuracy": x}, "B2": {...}, "B3": {...}},
    "temporal":   {"B3": {"temporal_accuracy": x}}
  }
  ```
  - Abstention predictions: B1 = `b1_full_history`, B2 = `b2_naive_top_k`, B3 =
    the engine via `retrieve(query, token_budget=64, min_relevance=<small positive,
    e.g. 0.05>)` joined to text. (B0 optional.)
  - Temporal: B3 present = `retrieve(...)` joined; B3 past = `history("morning_drink")`
    joined. (Only B3 is scored for temporal — see honesty constraint #2.)
- `latest.json` stays a stable sorted dump.

## Acceptance — gate: `PYTHONPATH=src uv run --no-sync pytest -q tests/` (FULL suite, must pass, FULLY OFFLINE)
Existing tests unchanged + NEW tests:
- `test_engine.py`: (a) `retrieve(min_relevance=high)` returns `[]` for an
  unrelated/zero-overlap query while `min_relevance=0.0` (default) is unchanged;
  (b) `history(subject)` returns the superseded (`coffee`) record and NOT the active
  (`tea`) one, newest-retired-first.
- `test_benchmark.py`: (c) `run()` output has a `"capabilities"` key with
  `abstention` + `temporal`; (d) **B3 abstains** (`abstention_accuracy == 1.0`) while at
  least one naive baseline does NOT (`< 1.0`); (e) B3 `temporal_accuracy == 1.0`;
  (f) the existing `"baselines"` section is unchanged (all existing curve assertions
  still pass).

## Constraints
- No live network in tests; no secrets. Deps stay within `pyproject.toml`. Format with
  `black` (line-length 100, target py311) + `isort`. Scope tightly; no unrelated refactors.
- Follow the local AGENTS.md rules; use the VW-1090 key; preserve provenance/vault rules.
