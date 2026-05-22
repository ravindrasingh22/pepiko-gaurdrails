from app.models.guardrail_decision import GuardrailDecision


def select(decision: GuardrailDecision) -> str:
    if decision.response_mode in {"neutral_age_calibrated_explain", "guide_or_redirect", "neutralize_group_language"}:
        return "meta-llama/Llama-3.2-1B-Instruct"
    if decision.response_mode == "safe_refusal":
        return "safety-fallback"
    return "safety-fallback"
