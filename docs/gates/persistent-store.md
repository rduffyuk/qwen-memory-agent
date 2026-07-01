# Gate spec: persistent store (survive restart)

**Goal:** Make memories survive a server restart. Today `MemoryStore` keeps
everything in the in-process dicts `_records`/`_vectors` (Qdrant is a barely-read
mirror), so a restart wipes the store. Add an optional JSON-snapshot persistence:
save on every mutation, load on startup, rebuild the in-memory index from it.
Pure Python + stdlib; no new deps.

**Jira:** VW-1090 (use this key; do NOT create a new issue).
**Repo:** this one (`~/qwen-memory-agent`, current branch). Public MIT repo.

## Required Codex lane contract
Follow the local AGENTS.md rules supplied by the runner. Use the VW-1090 key. Do
NOT delete, rename, skip, xfail, or weaken any existing test/assertion — the ENTIRE
suite (incl. `tests/test_benchmark.py`, which locks the curve) must stay green. No
unrelated refactors. Preserve provenance/vault rules.

## Files in scope (modify ONLY these)
- `src/memory_agent/store.py`
- `src/memory_agent/api.py` (ONE line: read a persist path from env for the default store)
- `tests/test_persistence.py` (new)

**Do NOT** touch `engine.py`, `models.py`, `qwen.py`, `mcp_server.py`, `dream.py`,
`agent.py`, `benchmark/`.

## Design

### `store.py`
- `__init__(..., persist_path: str | None = None)`, stored as `self.persist_path`.
  Default `None` → behaviour is **exactly** as today (no file I/O). This is what keeps
  every existing test + the benchmark curve unchanged.
- On init, if `persist_path` is set AND the file exists and is non-empty: `self._load()`.
- `_snapshot()` → dict of the same shape as `MemoryEngine.export_json`:
  `{"version": 1, "records": [{"record": r.model_dump(mode="json"), "vector": v}, ...]}`
  built from `self._records` / `self._vectors`.
- `_save()` (called only when `persist_path`): write `_snapshot()` as JSON **atomically**
  — write to `persist_path + ".tmp"` then `os.replace(tmp, persist_path)` so a crash
  mid-write cannot corrupt the file. No-op if `persist_path is None`.
- `_load()`: read the JSON, and for each entry rebuild `self._records[id]` (via
  `MemoryRecord.model_validate`) and `self._vectors[id]`, then `_ensure_collection` and
  re-`client.upsert` every point so search works after restart. Tolerate a missing file
  (start empty). On a malformed file, raise a clear `ValueError` (do not silently drop data).
- Call `_save()` at the END of each mutating method: `upsert`, `delete`, `mark_superseded`.
  (Read methods never write.)

### `api.py`
- Where the DEFAULT store is built for the default engine, pass
  `persist_path=os.getenv("MEMORY_PERSIST_PATH") or None` so the live box can enable
  persistence via `.env` (e.g. `MEMORY_PERSIST_PATH=/root/qwen-memory-agent/memory.json`)
  with zero code change. `import os` already present. Change no route.

## Acceptance — gate: `PYTHONPATH=src uv run --no-sync pytest -q tests/` (FULL suite, must pass, FULLY OFFLINE)
Existing tests unchanged + NEW `tests/test_persistence.py`:
1. **Round-trip survives a new store instance:** with `persist_path=tmp/x.json`, write two
   records into store A; construct a SEPARATE store B with the same path → B's
   `list_records()` returns both, and a `search()` on B ranks them (vectors rehydrated).
2. **Mutation persists:** after a `mark_superseded` (or `delete`) on A, a fresh B reflects it
   (record superseded / gone).
3. **Default is pure in-memory:** with `persist_path=None`, no file is created and behaviour
   is unchanged (write + list works, nothing written to disk).
4. **Atomic write leaves no partial file / tolerates missing file:** constructing a store on a
   non-existent path starts empty (no error); after a write the real file exists and the
   `.tmp` file does not.
5. **Malformed file raises** a clear error (not a silent empty store).

## Constraints
- No new deps (stdlib `json` + `os` only). No secrets. Format with `black` (line-length 100,
  target py311) + `isort`. Scope tightly.
