from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision
from app.guardrails import prompt_manager


def _sentence(items: list[str]) -> str:
    cleaned = [item.strip().rstrip(".") for item in items if item.strip()]
    if not cleaned:
        return ""
    return ". ".join(item[:1].upper() + item[1:] if item else item for item in cleaned) + "."


def _modifier_segment(contract: dict[str, object]) -> str:
    modifiers = [item for item in contract.get("modifiers", []) if item and item != "(none)"]
    if not modifiers:
        return ""
    return " | " + ", ".join(modifiers)


def build(
    child_profile: ChildProfile,
    message: str,
    decision: GuardrailDecision,
    rag_context: list[dict[str, object]],
) -> str:
    rendered = prompt_manager.render_prompt(child_profile, message, decision)
    decision.prompt_contract["safety_envelope"] = rendered["safety_envelope"]
    decision.prompt_contract["template_id"] = rendered["template_id"]
    decision.prompt_contract["checklist"] = rendered["checklist"]
    return str(rendered["prompt"])
