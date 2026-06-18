from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator

from app.model_service import DEFAULT_CHAT_MODEL, generate_chat_response
from app.text_normalization_service import normalize_child_message
from app.validator_client import validate_assistant_response

router = APIRouter()


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=256, ge=1, le=1024)
    validate_response: bool = False

    session_id: str = Field(min_length=1)
    child_profile: dict[str, Any] = Field(default_factory=dict)

    # Backward-compatible legacy fields
    message: str | None = Field(default=None, min_length=1, max_length=4000)
    recent_context: list[str] = Field(default_factory=list)
    system_prompt: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _validate_messages(self) -> "ChatRequest":
        if self.messages:
            return self
        if self.message:
            return self
        raise ValueError("either messages or message is required")


class ChatChoiceMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class ChatChoice(BaseModel):
    index: int
    message: ChatChoiceMessage
    finish_reason: str


class ChatUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ValidatorUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class TextNormalizationRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    system_prompt: str | None = Field(default=None, min_length=1)
    session_id: str = Field(min_length=1)
    child_profile: dict[str, Any] = Field(default_factory=dict)
    recent_context: list[str] = Field(default_factory=list)
    input_mode: Literal["text", "voice"] | None = None
    model: str | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    max_tokens: int = Field(default=256, ge=1, le=512)


class TextNormalizationUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class TextNormalizationResponse(BaseModel):
    session_id: str
    child_profile: dict[str, Any]
    raw_message: str
    preprocessed_message: str
    normalized_message: str
    repairs: list[str]
    model: str
    usage: TextNormalizationUsage


class ChatResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: ChatUsage
    session_id: str
    child_profile: dict[str, Any]
    response_validation: Literal["Safe", "UnSafe"] | None = None
    validation_score: float | None = None
    validator_usage: ValidatorUsage | None = None
    validator_error: str | None = None


def _messages_from_legacy(payload: ChatRequest) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if payload.system_prompt:
        messages.append({"role": "system", "content": payload.system_prompt})
    for item in payload.recent_context:
        text = str(item).strip()
        if text:
            messages.append({"role": "user", "content": text})
    if payload.message:
        messages.append({"role": "user", "content": payload.message})
    return messages


@router.post("/guardrail/text-normalization", response_model=TextNormalizationResponse)
async def text_normalization(payload: TextNormalizationRequest) -> TextNormalizationResponse:
    result = normalize_child_message(
        raw_message=payload.message,
        child_profile=dict(payload.child_profile),
        recent_context=list(payload.recent_context),
        input_mode=payload.input_mode,
        system_prompt=payload.system_prompt,
        model_name=payload.model,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )
    usage = result.get("usage", {})
    return TextNormalizationResponse(
        session_id=payload.session_id,
        child_profile=dict(payload.child_profile),
        raw_message=str(result.get("raw_message", payload.message)),
        preprocessed_message=str(result.get("preprocessed_message", payload.message)),
        normalized_message=str(result.get("normalized_message", payload.message)),
        repairs=[str(item) for item in result.get("repairs", [])],
        model=str(result.get("model_name", payload.model or DEFAULT_CHAT_MODEL)),
        usage=TextNormalizationUsage(
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            total_tokens=int(usage.get("total_tokens", 0)),
        ),
    )


@router.post("/guardrail/chat", response_model=ChatResponse)
async def chat_guardrail(payload: ChatRequest) -> ChatResponse:
    messages = [item.model_dump() for item in payload.messages] if payload.messages else _messages_from_legacy(payload)
    generation = generate_chat_response(
        messages=messages,
        max_new_tokens=payload.max_tokens,
        temperature=payload.temperature,
        model_name=payload.model,
    )
    usage = generation.get("usage", {})
    answer = str(generation.get("answer", ""))
    validation = (
        validate_assistant_response(
            content=answer,
            child_profile=dict(payload.child_profile),
        )
        if payload.validate_response
        else {}
    )
    return ChatResponse(
        id=f"chatcmpl-{uuid.uuid4().hex}",
        created=int(time.time()),
        model=str(generation.get("model_name", payload.model or DEFAULT_CHAT_MODEL)),
        choices=[
            ChatChoice(
                index=0,
                message=ChatChoiceMessage(content=answer),
                finish_reason="stop",
            )
        ],
        usage=ChatUsage(
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            total_tokens=int(usage.get("total_tokens", 0)),
        ),
        session_id=payload.session_id,
        child_profile=dict(payload.child_profile),
        response_validation=validation.get("response_validation"),
        validation_score=float(validation["validation_score"]) if "validation_score" in validation else None,
        validator_usage=ValidatorUsage(**dict(validation["validator_usage"])) if "validator_usage" in validation else None,
        validator_error=validation.get("validator_error"),
    )
