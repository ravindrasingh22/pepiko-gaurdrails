from app.models.guardrail_decision import GuardrailDecision

BLOCKLIST = {"kill", "suicide", "bomb"}


def check(normalized: dict[str, object]) -> GuardrailDecision | None:
    text = str(normalized["text"]).lower()
    if any(term in text for term in BLOCKLIST):
        return GuardrailDecision(
            policy_bucket="hard_block",
            safety_category="dangerous_instruction",
            response_mode="trusted_adult",
            risk_level="high",
            parent_visible=True,
            confidence=0.99,
            is_terminal=True,
        )
    return None
