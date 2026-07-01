# Gate spec: graded memory decay + reinforce-on-recall

**Goal:** Replace binary-only forgetting with *graded, time-based decay* plus
*reinforce-on-recall*, so the engine forgets stale low-value memories over time
while keeping recalled/pinned ones. Maps Track-1 "timely forgetting of outdated
information" + "increasingly accurate across sessions". Pure Python, no new deps.

**Jira:** VW-1090

**Files in scope (modify only these):**
- `src/memory_agent/models.py`
- `src/memory_agent/engine.py`
- `src/memory_agent/store.py` (only if a getter is needed; prefer leaving as-is)
- `tests/test_engine.py`
- new `tests/test_decay.py`

**Do NOT** touch `benchmark/`, `api.py`, `mcp_server.py`, `qwen.py`. **Do NOT**
delete, rename, or weaken any existing test or assertion. Keep all current tests
green. No unrelated refactors.

## Design

1. `MemoryRecord` gains two fields:
   - `last_accessed: datetime` — default = `ts`.
   - `access_count: int = 0`.

2. Decay in `engine.py`:
   - Module constants: `DECAY_HALF_LIVES = {"fact": 30.0, "episodic": 7.0}`
     (days), `DEFAULT_HALF_LIFE_DAYS = 30.0`, `PINNED_TYPES = {"preference"}`.
   - `effective_salience(record) -> float`:
     - if `record.type in PINNED_TYPES`: return `record.salience` (no decay).
     - else `age_days = max((now - record.last_accessed).total_seconds()/86400, 0)`
       and `factor = 0.5 ** (age_days / half_life_for_type)`; return
       `record.salience * factor`.
   - `_hybrid_score` uses `effective_salience(record)` in the gamma term in place
     of raw `record.salience`. Recency term unchanged.

3. Reinforce-on-recall: in `retrieve()`, for each record that is **packed**
   (made the token budget), bump `access_count += 1` and set
   `last_accessed = now`, persisting via the store (use existing upsert/set
   path; re-embedding is NOT required — reuse stored vector). Reinforcement
   resets that record's decay clock.

4. Decay-based forget: extend `forget()` with `decayed_below: float | None = None`
   — when set, delete every record whose `effective_salience(record) <
   decayed_below`. Combine with existing ttl/salience/subject filters (OR
   semantics, consistent with current behaviour).

## Acceptance criteria (gate: `PYTHONPATH=src uv run --no-sync pytest -q tests/` — ALL pass)

1. A non-pinned (`type="fact"`) record aged past its half-life has strictly
   lower `effective_salience` than its raw `salience`; a `type="preference"`
   record of equal age/salience is unchanged (pinned).
2. Calling `retrieve()` on a query that packs a record increments its
   `access_count` and advances `last_accessed`; after reinforcement that
   record's `effective_salience` exceeds an equal un-recalled peer's.
3. `forget(decayed_below=<t>)` deletes a faded record and keeps a freshly
   reinforced one.
4. Existing `tests/test_engine.py` (write/retrieve/supersession/budget) and the
   committed `tests/test_benchmark.py` numbers remain green (decay must be
   backward-compatible: pinned preferences => no ranking change).

## Codex lane contract
Follow the runner's AGENTS.md. Use Jira key VW-1090. Preserve every existing
test/assertion. Keep vault/provenance rules. No unrelated refactors. Commit only
the in-scope files.
