from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    text: str
    type: str
    subject: str
    salience: float = Field(default=0.5, ge=0.0, le=1.0)
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str | None = None
    superseded_by: str | None = None
