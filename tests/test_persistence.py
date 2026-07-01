from __future__ import annotations

import json

import pytest

from memory_agent.models import MemoryRecord
from memory_agent.store import MemoryStore


def make_record(text: str, *, subject: str) -> MemoryRecord:
    return MemoryRecord(text=text, type="fact", subject=subject)


def test_persistent_store_round_trip_survives_new_instance(tmp_path) -> None:
    persist_path = tmp_path / "memory.json"
    coffee = make_record("Ryan prefers coffee in the morning.", subject="drink")
    python = make_record("Ryan writes Python tests.", subject="testing")
    store = MemoryStore(persist_path=str(persist_path))

    store.upsert(coffee, [1.0, 0.0])
    store.upsert(python, [0.0, 1.0])

    reloaded = MemoryStore(persist_path=str(persist_path))
    records = reloaded.list_records()
    results = reloaded.search([1.0, 0.0])

    assert {record.id for record in records} == {coffee.id, python.id}
    assert results
    assert results[0].record.id == coffee.id


def test_search_uses_qdrant_vector_index_not_python_vector_cache() -> None:
    store = MemoryStore(location=":memory:")
    coffee = make_record("Ryan prefers coffee in the morning.", subject="drink")
    store.upsert(coffee, [1.0, 0.0])

    store._vectors.clear()
    results = store.search([1.0, 0.0])

    assert results
    assert results[0].record.id == coffee.id
    assert results[0].cosine == pytest.approx(1.0)


def test_persistent_store_mutation_persists_to_fresh_instance(tmp_path) -> None:
    persist_path = tmp_path / "memory.json"
    old = make_record("Ryan prefers coffee in the morning.", subject="drink")
    new = make_record("Ryan prefers tea in the morning.", subject="drink")
    store = MemoryStore(persist_path=str(persist_path))
    store.upsert(old, [1.0, 0.0])
    store.upsert(new, [0.0, 1.0])

    store.mark_superseded(old.id, new.id)

    reloaded = MemoryStore(persist_path=str(persist_path))
    reloaded_old = reloaded.get(old.id)
    assert reloaded_old is not None
    assert reloaded_old.superseded_by == new.id
    assert [record.id for record in reloaded.list_records()] == [new.id]

    store.delete(new.id)
    deleted_reloaded = MemoryStore(persist_path=str(persist_path))

    assert deleted_reloaded.get(new.id) is None
    assert {record.id for record in deleted_reloaded.list_records(include_superseded=True)} == {
        old.id
    }


def test_default_store_is_pure_in_memory(tmp_path) -> None:
    persist_path = tmp_path / "memory.json"
    record = make_record("Ryan likes jazz while coding.", subject="music")
    store = MemoryStore(persist_path=None)

    store.upsert(record, [1.0])

    assert store.list_records() == [record]
    assert not persist_path.exists()


def test_persistent_store_tolerates_missing_path_and_writes_atomically(tmp_path) -> None:
    persist_path = tmp_path / "memory.json"

    store = MemoryStore(persist_path=str(persist_path))

    assert store.list_records() == []
    assert not persist_path.exists()

    record = make_record("Ryan writes offline tests.", subject="testing")
    store.upsert(record, [1.0])

    assert persist_path.exists()
    assert not persist_path.with_name(persist_path.name + ".tmp").exists()
    snapshot = json.loads(persist_path.read_text())
    assert snapshot["version"] == 1
    assert snapshot["records"][0]["record"]["id"] == record.id


def test_persistent_store_creates_missing_parent_directory(tmp_path) -> None:
    persist_path = tmp_path / "missing" / "nested" / "memory.json"
    store = MemoryStore(persist_path=str(persist_path))
    record = make_record("Ryan writes offline tests.", subject="testing")

    store.upsert(record, [1.0])

    assert persist_path.exists()
    assert MemoryStore(persist_path=str(persist_path)).get(record.id) == record


def test_persistent_store_malformed_file_raises_clear_error(tmp_path) -> None:
    persist_path = tmp_path / "memory.json"
    persist_path.write_text("{bad json")

    with pytest.raises(ValueError, match="memory snapshot"):
        MemoryStore(persist_path=str(persist_path))


def test_create_app_wires_persist_path_from_env(monkeypatch, tmp_path) -> None:
    # Pins the api env wiring: with MEMORY_PERSIST_PATH set, the default store must
    # use it (a mutation of `os.getenv(...) or None` to `... and None` always yields
    # None, silently disabling persistence on the live box, and otherwise untested).
    from memory_agent.api import create_app

    target = str(tmp_path / "box-memory.json")
    monkeypatch.setenv("MEMORY_PERSIST_PATH", target)
    app = create_app()
    assert app.state.engine.store.persist_path == target

    monkeypatch.delenv("MEMORY_PERSIST_PATH", raising=False)
    app_default = create_app()
    assert app_default.state.engine.store.persist_path is None
