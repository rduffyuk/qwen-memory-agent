from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointIdsList, PointStruct, VectorParams

from memory_agent.models import MemoryRecord


@dataclass(frozen=True)
class SearchResult:
    record: MemoryRecord
    cosine: float


class MemoryStore:
    def __init__(
        self,
        *,
        collection_name: str = "memory_agent",
        client: QdrantClient | None = None,
        location: str | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.client = client or QdrantClient(location=location or ":memory:")
        self._records: dict[str, MemoryRecord] = {}
        self._vectors: dict[str, list[float]] = {}
        self._vector_size: int | None = None

    def upsert(self, record: MemoryRecord, vector: list[float]) -> MemoryRecord:
        self._ensure_collection(len(vector))
        self._records[record.id] = record
        self._vectors[record.id] = vector
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=record.id,
                    vector=vector,
                    payload=record.model_dump(mode="json"),
                )
            ],
        )
        return record

    def search(
        self,
        vector: list[float],
        *,
        limit: int = 20,
        include_superseded: bool = False,
    ) -> list[SearchResult]:
        results: list[SearchResult] = []
        for record_id, record in self._records.items():
            if record.superseded_by and not include_superseded:
                continue
            stored_vector = self._vectors[record_id]
            results.append(SearchResult(record=record, cosine=_cosine(vector, stored_vector)))
        return sorted(results, key=lambda item: item.cosine, reverse=True)[:limit]

    def delete(self, record_id: str) -> bool:
        existed = record_id in self._records
        self._records.pop(record_id, None)
        self._vectors.pop(record_id, None)
        if existed:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=PointIdsList(points=[record_id]),
            )
        return existed

    def mark_superseded(self, record_id: str, superseded_by: str) -> MemoryRecord | None:
        record = self._records.get(record_id)
        if record is None:
            return None
        updated = record.model_copy(update={"superseded_by": superseded_by})
        self._records[record_id] = updated
        self.client.set_payload(
            collection_name=self.collection_name,
            payload={"superseded_by": superseded_by},
            points=[record_id],
        )
        return updated

    def get(self, record_id: str) -> MemoryRecord | None:
        return self._records.get(record_id)

    def list_records(self, *, include_superseded: bool = False) -> list[MemoryRecord]:
        records = list(self._records.values())
        if include_superseded:
            return records
        return [record for record in records if not record.superseded_by]

    def export_records(self) -> list[tuple[MemoryRecord, list[float]]]:
        return [(record, list(self._vectors[record.id])) for record in self._records.values()]

    def active_by_subject_type(self, subject: str, type: str) -> list[MemoryRecord]:
        return [
            record
            for record in self._records.values()
            if record.subject == subject and record.type == type and not record.superseded_by
        ]

    def stats(self) -> dict[str, int]:
        active = len(self.list_records())
        return {
            "total": len(self._records),
            "active": active,
            "superseded": len(self._records) - active,
        }

    def _ensure_collection(self, vector_size: int) -> None:
        if self._vector_size == vector_size:
            return
        if self._vector_size is not None and self._vector_size != vector_size:
            raise ValueError(
                f"collection vector size is {self._vector_size}, got vector with size {vector_size}"
            )
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
        self._vector_size = vector_size


def _cosine(left: list[float], right: list[float]) -> float:
    left_arr = np.array(left, dtype=float)
    right_arr = np.array(right, dtype=float)
    left_norm = np.linalg.norm(left_arr)
    right_norm = np.linalg.norm(right_arr)
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return float(np.dot(left_arr, right_arr) / (left_norm * right_norm))
