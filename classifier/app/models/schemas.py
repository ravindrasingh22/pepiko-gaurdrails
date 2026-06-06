from typing import Any

from pydantic import BaseModel, Field

from app.models.audit_event import AuditEvent
from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision


class GuardrailRunRequest(BaseModel):
    child_profile: ChildProfile
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)
    recent_context: list[str] = Field(default_factory=list)


class GuardrailRunResponse(BaseModel):
    question: str
    context: list[str] = Field(default_factory=list)
    age_band: str
    prompt: str


class ClassificationTestRequest(BaseModel):
    child_profile: ChildProfile
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)
    recent_context: list[str] = Field(default_factory=list)


class ClassificationTestResponse(BaseModel):
    input: dict[str, Any]
    classifier: dict[str, Any]
    g1: dict[str, Any]
    g2: dict[str, Any]
    active_flags: list[dict[str, Any]] = Field(default_factory=list)
    g3: dict[str, Any]
    g4: dict[str, Any]
    age_policy: dict[str, Any]
    modifier_tags: dict[str, Any]


class ClassificationPromptResponse(BaseModel):
    prompts: list[dict[str, str]]
    prompt_checklist: dict[str, Any]
    classifier_output: dict[str, Any]


class LLMTestRequest(BaseModel):
    child_profile: ChildProfile
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)
    recent_context: list[str] = Field(default_factory=list)


class LLMTestResponse(BaseModel):
    decision: GuardrailDecision
    model_name: str
    prompt: str
    rag_context: list[dict[str, Any]]
    raw_answer: str
    stage_outputs: dict[str, Any]


class ValidatorTestRequest(BaseModel):
    child_profile: ChildProfile
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)
    recent_context: list[str] = Field(default_factory=list)
    answer: str | None = None


class ValidatorTestResponse(BaseModel):
    decision: GuardrailDecision
    answer_checked: str
    validation: dict[str, Any]
    repaired_answer: str | None = None
    stage_outputs: dict[str, Any]
