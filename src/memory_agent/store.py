from __future__ import annotations

import json
import os
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
        persist_path: str | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.client = client or QdrantClient(location=location or ":memory:")
        self.persist_path = persist_path
        self._records: dict[str, MemoryRecord] = {}
        self._vectors: dict[str, list[float]] = {}
        self._vector_size: int | None = None
        if (
            self.persist_path
            and os.path.exists(self.persist_path)
            and os.path.getsize(self.persist_path)
        ):
            self._load()

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
        self._save()
        return record

    def search(
        self,
        vector: list[float],
        *,
        limit: int = 20,
        include_superseded: bool = False,
    ) -> list[SearchResult]:
        if not self._records or self._vector_size is None:
            return []

        results: list[SearchResult] = []
        query_limit = max(limit, len(self._records))
        points = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=query_limit,
        ).points
        for point in points:
            record = self._records.get(str(point.id))
            if record is None:
                continue
            if record.superseded_by and not include_superseded:
                continue
            results.append(SearchResult(record=record, cosine=float(point.score)))
            if len(results) >= limit:
                break
        return results

    def delete(self, record_id: str) -> bool:
        existed = record_id in self._records
        self._records.pop(record_id, None)
        self._vectors.pop(record_id, None)
        if existed:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=PointIdsList(points=[record_id]),
            )
        self._save()
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
        self._save()
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

    def most_similar_active(
        self,
        vector: list[float],
        *,
        type: str,
        exclude_id: str,
        min_cosine: float,
    ) -> MemoryRecord | None:
        best_record: MemoryRecord | None = None
        best_cosine = min_cosine
        for record_id, record in self._records.items():
            if record_id == exclude_id or record.type != type or record.superseded_by is not None:
                continue
            cosine = _cosine(vector, self._vectors[record_id])
            if cosine >= best_cosine:
                best_record = record
                best_cosine = cosine
        return best_record

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

    def _snapshot(self) -> dict[str, object]:
        return {
            "version": 1,
            "records": [
                {
                    "record": record.model_dump(mode="json"),
                    "vector": self._vectors[record.id],
                }
                for record in self._records.values()
            ],
        }

    def _save(self) -> None:
        if self.persist_path is None:
            return
        parent = os.path.dirname(self.persist_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp_path = self.persist_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as file:
            json.dump(self._snapshot(), file)
        os.replace(tmp_path, self.persist_path)

    def _load(self) -> None:
        if self.persist_path is None or not os.path.exists(self.persist_path):
            return
        try:
            with open(self.persist_path, encoding="utf-8") as file:
                data = json.load(file)
            entries = data["records"]
            if not isinstance(entries, list):
                raise ValueError("records must be a list")
            for entry in entries:
                record = MemoryRecord.model_validate(entry["record"])
                vector = list(entry["vector"])
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
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"failed to load memory snapshot from {self.persist_path}") from exc


def _cosine(left: list[float], right: list[float]) -> float:
    left_arr = np.array(left, dtype=float)
    right_arr = np.array(right, dtype=float)
    left_norm = np.linalg.norm(left_arr)
    right_norm = np.linalg.norm(right_arr)
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return float(np.dot(left_arr, right_arr) / (left_norm * right_norm))
