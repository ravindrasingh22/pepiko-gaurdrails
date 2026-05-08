from typing import Any

from app.models.audit_event import AuditEvent


def log(stage_logs: list[AuditEvent], stage: str, detail: dict[str, Any]) -> None:
    stage_logs.append(AuditEvent(stage=stage, detail=detail))
