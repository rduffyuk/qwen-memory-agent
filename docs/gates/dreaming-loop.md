# Gate spec: dreaming loop — offline memory consolidation (propose → approve)

**Goal:** Add a Qwen-driven *dreaming loop* that reviews the active memory set and
**proposes** consolidations (merge redundant memories / forget stale ones /
adjust salience), then applies ONLY the proposals a human approves. Maps Track-1
"autonomously accumulate experience" + "timely forgetting of outdated
information" while staying human-in-the-loop. Pure Python, no new deps.

**Jira:** VW-1090 (use this key; do NOT create a new issue).
**Repo:** this one (`~/qwen-memory-agent`, current branch). Public MIT repo — import nothing proprietary.

## Why (design rationale — keep this intent)
Consolidation must be **two-phase and non-autonomous**: `dream()` returns
proposals and mutates NOTHING; a separate `apply(proposals, approved_ids)` mutates
only approved proposals. The model references memories by `id`; LLMs hallucinate
ids, so `dream()` MUST validate every proposal against the live record set and
DROP any proposal that references an unknown id — the loop refuses to act on its
own hallucinations. Token usage is recorded automatically because `dream()` goes
through `engine.qwen.chat()`.

## Files in scope (create/modify ONLY these)
- `src/memory_agent/dream.py` (new — all the logic)
- `src/memory_agent/api.py` (ADD two routes only; do NOT change existing routes/behaviour)
- `src/memory_agent/mcp_server.py` (ADD two tools only; do NOT change existing tools)
- `tests/test_dream.py` (new)

**Do NOT** touch `engine.py`, `qwen.py`, `models.py`, `store.py`, `agent.py`,
`benchmark/`. **Do NOT** delete, rename, skip, xfail, or weaken any existing test
or assertion. Keep the ENTIRE current suite green.

## Design

### `src/memory_agent/dream.py`
```python
@dataclass(frozen=True)
class DreamProposal:
    id: str                       # uuid4, generated at parse time (approval handle)
    kind: str                     # "merge" | "forget" | "resalience"
    target_ids: list[str]         # existing record ids the proposal acts on
    rationale: str
    merged_text: str | None = None    # required for "merge"
    subject: str | None = None        # for "merge" (new consolidated record)
    type: str | None = None           # for "merge"
    new_salience: float | None = None # for "merge" + "resalience"

@dataclass(frozen=True)
class DreamReport:
    applied: list[str]      # proposal ids applied
    merged: int
    forgotten: int
    resalienced: int
    skipped: int            # approved ids with no matching / invalid proposal
```

`class DreamLoop`:
- `__init__(self, engine: MemoryEngine, *, model: str | None = None)`.
- `dream(self) -> list[DreamProposal]`:
  1. Read active records via `engine.store.list_records()`.
  2. Build a compact digest (one line per record: `id · type · subject · sal · text`)
     and a system+user message asking the model to return a **JSON array** of
     proposal objects with keys `kind`, `target_ids`, `rationale`, and the
     kind-specific keys (`merged_text`/`subject`/`type`/`new_salience`).
  3. Call `engine.qwen.chat(messages, model=self.model)` (NO tools → returns a str).
  4. Parse robustly: strip a leading ```json / trailing ``` fence if present, then
     `json.loads`. If the payload is not a list, return `[]` (never raise on a
     malformed model reply).
  5. For each entry: assign a fresh `uuid4` id, coerce fields, and **validate** —
     drop the proposal if `kind` is unknown, if `target_ids` is empty, or if ANY
     `target_id` is not a currently-active record id. `merge` also requires
     non-empty `merged_text`. Return the surviving proposals.
  - **`dream()` MUST NOT mutate the store** (no write/forget/upsert).
- `apply(self, proposals: Sequence[DreamProposal], approved_ids: Iterable[str]) -> DreamReport`:
  - Apply ONLY proposals whose `id` is in `approved_ids`. Ignore approved ids with
    no matching proposal (count them in `skipped`).
  - `merge`: create the consolidated record via
    `engine.write(merged_text, type=type or "fact", subject=subject, salience=new_salience or 0.5)`,
    then `engine.forget(record_id=tid)` for each `target_id` still present. Count `merged += 1`.
  - `forget`: `engine.forget(record_id=tid)` for each `target_id`; count `forgotten += 1`.
  - `resalience`: for each `target_id`, look up its stored vector via
    `dict((r.id, v) for r, v in engine.store.export_records())`, then
    `engine.store.upsert(record.model_copy(update={"salience": new_salience}), vector)`.
    Count `resalienced += 1`. (No re-embed; do NOT touch `store` internals beyond
    the public `export_records` / `upsert`.)
  - Return the `DreamReport`.

### `src/memory_agent/api.py` (ADD only)
- `POST /dream` → `{"proposals": [<DreamProposal as dict, incl. id>]}` (calls `DreamLoop(resolved_engine).dream()`; serialise dataclasses to dicts).
- `POST /dream/apply` with body `{"proposals": [...], "approved_ids": [...]}` →
  the `DreamReport` as a dict. Rebuild `DreamProposal` objects from the posted dicts.
- Keep `/health`, `/usage`, `/chat`, `/memory/export`, `/memory/import` unchanged.

### `src/memory_agent/mcp_server.py` (ADD only)
- `memory.dream` (no args) → list of proposal dicts.
- `memory.dream_apply(proposals, approved_ids)` → report dict.
- Keep the existing five tools unchanged.

## Acceptance — gate: `PYTHONPATH=src uv run --no-sync pytest -q tests/` (FULL suite, must pass, FULLY OFFLINE)
New `tests/test_dream.py` (scripted FakeQwen whose `chat()` returns a JSON string —
no network) MUST cover:
1. **`dream()` parses proposals and does NOT mutate the store** — assert
   `engine.store.stats()` is identical before and after `dream()`.
2. **`dream()` drops a proposal that references an unknown record id** (hallucination
   guard): a scripted reply mixing one valid and one bogus-id proposal → only the
   valid one survives.
3. **`dream()` tolerates a ```json-fenced reply** and a non-list / malformed reply
   returns `[]` (no exception).
4. **`apply()` applies a merge only when approved** — approving the merge creates the
   consolidated record and retires the sources; a second (unapproved) proposal is NOT
   applied. Assert `DreamReport.merged == 1` and the merged text is retrievable while
   a source value is gone.
5. **`apply()` forget** deletes the target; **`apply()` resalience** changes the
   target's salience (assert the new value via `engine.store.get(id).salience`) and
   preserves its vector (retrievable afterwards).
6. **`apply()` counts an approved id with no matching proposal as `skipped`** (no crash).

## Constraints
- **Do NOT delete, rename, skip, xfail, or weaken any existing test or assertion.**
  The full suite (including `tests/test_benchmark.py`) must stay green.
- No live network in tests; no secrets in code. Keep deps within the declared
  `pyproject.toml` set. Format with `black` (line-length 100, target py311) + `isort`.
  Scope tightly — no unrelated refactors.
- Follow the local AGENTS.md rules supplied by the runner; use the VW-1090 key;
  preserve provenance/vault rules.
