# Gate spec: memory export / import (MEMORY.md artifact + JSON round-trip)

**Goal:** Give the store durable, portable persistence — export to a
human-readable `MEMORY.md`-style Markdown index AND a full-fidelity JSON
snapshot, and import the JSON back. Fixes "restart wipes memory" and provides a
visible demo artifact. Maps Track-1 "persistent memory". Pure Python, no deps.

**Jira:** VW-1090

**Files in scope (modify only these):**
- `src/memory_agent/store.py`
- `src/memory_agent/engine.py`
- `src/memory_agent/api.py`
- `src/memory_agent/mcp_server.py`
- new `tests/test_memory_io.py`

**Do NOT** touch `models.py`, `qwen.py`, `agent.py`, `benchmark/`. **Do NOT**
delete/rename/weaken any existing test/assertion. Keep all current tests green.
No unrelated refactors.

## Design

1. `store.py`: add `export_records() -> list[tuple[MemoryRecord, list[float]]]`
   returning every record (active AND superseded) with its stored vector.

2. `engine.py`:
   - `export_json() -> dict`: `{"version": 1, "records": [{"record": <record
     .model_dump(mode="json")>, "vector": [float,...]}, ...]}`. Include
     superseded records so supersession chains survive round-trip.
   - `import_json(data: dict) -> int`: for each entry, rebuild via
     `MemoryRecord.model_validate(entry["record"])` and
     `store.upsert(record, entry["vector"])` — **reuse the snapshot vector, do
     NOT re-embed** (import must work with no live Qwen client). Merge/upsert
     semantics (same id overwrites). Return count imported.
   - `export_markdown() -> str`: header line
     `# Memory export — {A} active, {S} superseded`, then one bullet per
     **active** record (superseded excluded), sorted by `salience` desc then
     `text`: `- [{type} · sal {salience:.2f} · used {access_count}] {text}`.

3. `api.py`: `GET /memory/export` -> `{"markdown": <str>, "json": <export_json>}`.
   `POST /memory/import` -> body is the export_json dict; calls `import_json`,
   returns `{"imported": <int>, "stats": <store.stats()>}`.

4. `mcp_server.py`: add `memory.export` (returns the same `{markdown, json}`) and
   `memory.import` (takes the json dict, returns `{"imported": int}`).

## Acceptance criteria (gate: `uv run pytest -q` — ALL pass)

1. Round-trip: write several memories (incl. a superseded pair via same
   subject/type), `export_json()`, `import_json()` into a **fresh** engine (new
   `MemoryStore(":memory:")`, and a Qwen fake that raises if `embed` is called) —
   the fresh engine reproduces identical record ids, the superseded marker, and
   `retrieve()` returns the same top record text. Proves no re-embed on import.
2. `export_markdown()` has exactly one bullet per active record, each containing
   its type, `sal`, `used`, and text; superseded records do NOT appear as bullets
   and the header counts them.
3. `GET /memory/export` returns both keys; `POST /memory/import` of that payload
   into a fresh app returns `imported` == active+superseded count and stats
   reflect it.
4. MCP `memory.export` / `memory.import` are registered and functional.
5. All existing tests remain green.

## Codex lane contract
Follow the runner's AGENTS.md. Use Jira key VW-1090. Preserve every existing
test/assertion. Keep vault/provenance rules. No unrelated refactors. Commit only
the in-scope files.
