from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    text: str
    type: str
    subject: str
    salience: float = Field(default=0.5, ge=0.0, le=1.0)
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0
    session_id: str | None = None
    superseded_by: str | None = None
    source_model: str | None = None
    embed_model: str | None = None

    @model_validator(mode="before")
    @classmethod
    def default_last_accessed_to_ts(cls, data: object) -> object:
        if not isinstance(data, dict) or data.get("last_accessed") is not None:
            return data
        if data.get("ts") is None:
            now = datetime.now(timezone.utc)
            return {**data, "ts": now, "last_accessed": now}
        return {**data, "last_accessed": data["ts"]}
