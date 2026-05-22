from app.guardrails import slm_classifier
from app.models.guardrail_decision import GuardrailDecision


def classify(normalized: dict[str, object]) -> GuardrailDecision:
    return slm_classifier.classify(normalized)
