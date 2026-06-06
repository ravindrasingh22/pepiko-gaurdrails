from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.model_service import DEFAULT_VALIDATOR_THRESHOLD, validate_response_with_score


router = APIRouter()


class ValidatorRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str | None = Field(default=None, min_length=1)
    age_group: str | None = Field(default=None, min_length=1)
    response_text: str | None = Field(default=None, min_length=1, max_length=8000)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    # Compatibility fields from the previous scaffold.
    answer: str | None = Field(default=None, min_length=1, max_length=8000)
    message: str | dict[str, Any] | None = Field(default=None)
    recent_context: list[str] = Field(default_factory=list)
    child_profile: dict[str, Any] = Field(default_factory=dict)
    choices: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_payload(self) -> "ValidatorRequest":
        if not (self.response_text or self.answer or self.choices or self.message):
            raise ValueError("response_text, answer, message, or chat completion choices are required")
        if not (self.age_group or self.child_profile.get("age_group")):
            raise ValueError("age_group or child_profile.age_group is required")
        return self

    def resolved_age_group(self) -> str:
        return str(self.age_group or self.child_profile.get("age_group") or "").strip()

    def resolved_response_text(self) -> str:
        if self.response_text or self.answer:
            return str(self.response_text or self.answer or "").strip()
        if isinstance(self.message, dict):
            return str(self.message.get("content", "")).strip()
        if isinstance(self.message, str):
            return self.message.strip()
        for choice in self.choices:
            message = choice.get("message") if isinstance(choice, dict) else None
            if isinstance(message, dict) and str(message.get("role", "")).strip() == "assistant":
                return str(message.get("content", "")).strip()
        return str(self.response_text or self.answer or "").strip()

    def is_lightweight_message_payload(self) -> bool:
        return bool(self.message and self.child_profile and not self.choices and not self.response_text and not self.answer)

    def is_chat_completion_payload(self) -> bool:
        return bool(self.choices and self.child_profile)


class ValidatorInput(BaseModel):
    session_id: str
    age_group: str
    response_text: str


class ValidatorModelInfo(BaseModel):
    backend: Literal["deberta_sequence_classifier", "lexicon_fallback"]
    model_path: str
    trained: bool
    threshold: float


class ValidatorScores(BaseModel):
    safe: float
    unsafe: float


class ValidatorRoute(BaseModel):
    action: Literal["allow", "fallback"]
    delivered_text: str
    fallback_text: str | None = None


class ValidatorUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ValidatorResponse(BaseModel):
    status: Literal["safe", "unsafe"]
    score: float
    label: Literal[0, 1]
    scores: ValidatorScores
    input: ValidatorInput
    model: ValidatorModelInfo
    usage: ValidatorUsage
    route: ValidatorRoute
    reasons: list[str] = Field(default_factory=list)


def _validation_label(status: str) -> str:
    return "Safe" if status == "safe" else "UnSafe"


def _chat_completion_response(
    payload: ValidatorRequest,
    validation_label: str,
    validation_score: float,
    validator_usage: dict[str, int],
) -> dict[str, Any]:
    output = payload.model_dump(exclude_none=True)
    output["response_validation"] = validation_label
    output["validation_score"] = validation_score
    output["validator_usage"] = validator_usage
    return output


def _lightweight_response(validation_label: str, validation_score: float, validator_usage: dict[str, int]) -> dict[str, Any]:
    return {
        "response_validation": validation_label,
        "validation_score": validation_score,
        "validator_usage": validator_usage,
    }


@router.post("/guardrail/validate", response_model=None)
async def validate_guardrail(payload: ValidatorRequest):
    result = validate_response_with_score(
        age_group=payload.resolved_age_group(),
        response_text=payload.resolved_response_text(),
        threshold=payload.threshold or DEFAULT_VALIDATOR_THRESHOLD,
    )
    if payload.is_lightweight_message_payload():
        return JSONResponse(content=_lightweight_response(_validation_label(result.status), result.score, result.usage))
    if payload.is_chat_completion_payload():
        return JSONResponse(
            content=_chat_completion_response(payload, _validation_label(result.status), result.score, result.usage)
        )
    return ValidatorResponse(
        status=result.status,
        score=result.score,
        label=result.label,
        scores=ValidatorScores(safe=result.safe_score, unsafe=result.unsafe_score),
        input=ValidatorInput(
            session_id=payload.session_id or "",
            age_group=result.age_group,
            response_text=result.response_text,
        ),
        model=ValidatorModelInfo(
            backend=result.backend,
            model_path=result.model_path,
            trained=result.trained,
            threshold=result.threshold,
        ),
        usage=ValidatorUsage(**result.usage),
        route=ValidatorRoute(
            action=result.action,
            delivered_text=result.delivered_text,
            fallback_text=result.fallback_text,
        ),
        reasons=result.reasons,
    )
