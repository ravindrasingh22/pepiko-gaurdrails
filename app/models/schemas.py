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
    final_policy_bucket: str
    final_response_mode: str
    llm_called: bool
    parent_visible: bool
    safe_to_show: bool
    final_answer: str
    prompt_contract: dict[str, Any] = Field(default_factory=dict)
    final_prompt: str = ""
    audit_log: list[AuditEvent]
    stage_outputs: dict[str, Any]


class ClassificationTestRequest(BaseModel):
    child_profile: ChildProfile
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)
    recent_context: list[str] = Field(default_factory=list)


class ClassificationTestResponse(BaseModel):
    decision: GuardrailDecision
    stage_outputs: dict[str, Any]


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
