from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision


def retrieve_if_allowed(message: str, child_profile: ChildProfile, decision: GuardrailDecision) -> list[dict[str, object]]:
    if not bool(decision.decision.get("allow_rag", False)):
        return []
    return [
        {
            "chunk_id": "demo-safe-001",
            "topic": "general_learning",
            "age_min": max(child_profile.age - 2, 3),
            "age_max": child_profile.age + 2,
            "detail_level": "simple",
            "safety_tags": ["safe_learning"],
            "source_trust": "curated",
            "allowed": True,
            "content": "Use short, age-appropriate educational guidance.",
        }
    ]
