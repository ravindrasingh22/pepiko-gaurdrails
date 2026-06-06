from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator

from app.model_service import DEFAULT_CHAT_MODEL, generate_chat_response

router = APIRouter()


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=256, ge=1, le=1024)

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


class ChatResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: ChatUsage
    session_id: str


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
    return ChatResponse(
        id=f"chatcmpl-{uuid.uuid4().hex}",
        created=int(time.time()),
        model=str(generation.get("model_name", payload.model or DEFAULT_CHAT_MODEL)),
        choices=[
            ChatChoice(
                index=0,
                message=ChatChoiceMessage(content=str(generation.get("answer", ""))),
                finish_reason="stop",
            )
        ],
        usage=ChatUsage(
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            total_tokens=int(usage.get("total_tokens", 0)),
        ),
        session_id=payload.session_id,
    )
