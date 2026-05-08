from typing import Any

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    stage: str
    detail: dict[str, Any] = Field(default_factory=dict)
