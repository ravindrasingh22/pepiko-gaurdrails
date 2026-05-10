from app.guardrails.age_policy_engine import apply
from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision


def test_age_policy_marks_parent_visible() -> None:
    profile = ChildProfile(age=9, age_group="9-10", language="en")
    decision = GuardrailDecision(
        policy_bucket="soft_block",
        safety_category="secrecy_from_parent",
        response_mode="redirect",
        risk_level="medium",
        parent_visible=False,
    )
    result = apply(profile, decision)
    assert result.parent_visible is True
