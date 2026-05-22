from typing import Any

from pydantic import BaseModel, Field


class GLSignal(BaseModel):
    name: str
    triggered: bool
    confidence: float
    emits: dict[str, bool | str] = Field(default_factory=dict)


class GuardrailDecision(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    g1_reason: str = ""
    g2_reasons: dict[str, str] = Field(default_factory=dict)
    gl_signals: dict[str, GLSignal] = Field(default_factory=dict)
    active_gls: list[str] = Field(default_factory=list)
    gates: dict[str, Any] = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)
    policy_bucket: str
    safety_category: str
    response_mode: str
    risk_level: str
    parent_visible: bool
    confidence: float = 1.0
    is_terminal: bool = False
    guideline_tags: list[str] = Field(default_factory=list)
    signals: dict[str, bool | str] = Field(default_factory=dict)
    gate_values: dict[str, Any] = Field(default_factory=dict)
    prompt_contract: dict[str, Any] = Field(default_factory=dict)
    classifier_metadata: dict[str, Any] = Field(default_factory=dict)
