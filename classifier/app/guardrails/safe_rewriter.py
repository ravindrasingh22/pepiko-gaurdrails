from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision


def repair_or_fallback(
    raw_answer: str,
    output_decision: dict[str, object],
    final_decision: GuardrailDecision,
    child_profile: ChildProfile,
) -> str:
    return (
        f"I can't help with that. Please talk to a trusted adult like your parent, "
        f"teacher, or caregiver so they can help safely."
    )
