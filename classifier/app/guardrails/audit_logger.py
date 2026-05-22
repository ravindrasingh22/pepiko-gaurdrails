import logging
from typing import Any

from app.models.audit_event import AuditEvent

LOGGER = logging.getLogger("pikuai.guardrails")


def log(stage_logs: list[AuditEvent], trace_id: str, stage: str, detail: dict[str, Any], direction: str = "event") -> None:
    event = AuditEvent(trace_id=trace_id, stage=stage, direction=direction, detail=detail)
    stage_logs.append(event)
    LOGGER.info("%s %s %s %s", trace_id, stage, direction, detail)
