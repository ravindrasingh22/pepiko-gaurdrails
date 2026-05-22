from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision
from training.slm_classifier.codebook import parse_codebook


CODEBOOK = parse_codebook()


def _visibility_rules() -> tuple[int, set[str]]:
    settings = CODEBOOK.parent_visibility
    return settings.force_visible_if_age_lte, set(settings.risk_levels)


def apply(child_profile: ChildProfile, decision: GuardrailDecision) -> GuardrailDecision:
    age_threshold, visible_risks = _visibility_rules()
    if child_profile.age <= age_threshold and decision.risk_level in visible_risks:
        return decision.model_copy(update={"parent_visible": True})
    return decision
