from app.guardrails.policy_loader import load_yaml_config
from app.models.guardrail_decision import GuardrailDecision


RULE_FILTER_CONFIG = load_yaml_config("rule_filters.yaml")
BLOCKLIST = {str(item).lower() for item in RULE_FILTER_CONFIG.get("blocked_terms", [])}
TERMINAL_DECISION = RULE_FILTER_CONFIG.get("terminal_decision", {})


def check(normalized: dict[str, object]) -> GuardrailDecision | None:
    text = str(normalized["text"]).lower()
    if any(term in text for term in BLOCKLIST):
        return GuardrailDecision(
            policy_bucket=str(TERMINAL_DECISION.get("policy_bucket", "hard_block")),
            safety_category=str(TERMINAL_DECISION.get("safety_category", "dangerous_instruction")),
            response_mode=str(TERMINAL_DECISION.get("response_mode", "trusted_adult")),
            risk_level=str(TERMINAL_DECISION.get("risk_level", "high")),
            parent_visible=bool(TERMINAL_DECISION.get("parent_visible", True)),
            confidence=float(TERMINAL_DECISION.get("confidence", 0.99)),
            is_terminal=True,
        )
    return None
