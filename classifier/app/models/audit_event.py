from typing import Any

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    trace_id: str
    stage: str
    direction: str = "event"
    detail: dict[str, Any] = Field(default_factory=dict)
