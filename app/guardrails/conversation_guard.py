from app.models.guardrail_decision import GuardrailDecision


def check(session_id: str, decision: GuardrailDecision, context: dict[str, object]) -> GuardrailDecision:
    recent = " ".join(context.get("recent_context", []))
    if recent and decision.safety_category == "secrecy_from_parent":
        return decision.model_copy(update={"confidence": max(decision.confidence, 0.9)})
    return decision
