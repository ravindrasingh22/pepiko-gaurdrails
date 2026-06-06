from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field


router = APIRouter()


class ValidatorRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1)
    recent_context: list[str] = Field(default_factory=list)
    child_profile: dict[str, Any] = Field(default_factory=dict)


class ValidatorResponse(BaseModel):
    status: str
    service: str
    endpoint: str
    message: str
    input_echo: dict[str, Any]


@router.post("/guardrail/validate", response_model=ValidatorResponse)
async def validate_guardrail(payload: ValidatorRequest) -> ValidatorResponse:
    return ValidatorResponse(
        status="scaffolded",
        service="validator",
        endpoint="/api/v1/guardrail/validate",
        message="Validator service scaffold created. Runtime validation logic should be implemented here independently.",
        input_echo={
            "session_id": payload.session_id,
            "message": payload.message,
            "answer": payload.answer,
            "recent_context": payload.recent_context,
            "child_profile": payload.child_profile,
        },
    )
