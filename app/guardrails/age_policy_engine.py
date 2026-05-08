from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision


def apply(child_profile: ChildProfile, decision: GuardrailDecision) -> GuardrailDecision:
    if child_profile.age <= 10 and decision.risk_level in {"medium", "high"}:
        return decision.model_copy(update={"parent_visible": True})
    return decision
