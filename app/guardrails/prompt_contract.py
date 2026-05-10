from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision


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
    contract = decision.prompt_contract
    generated = str(contract.get("generated_prompt", "")).strip()
    if generated:
        return generated

    gates = decision.gates or decision.gate_values
    modifier_segment = _modifier_segment(contract)
    return (
        f"[Age: {child_profile.age_group} | "
        f"G1: {gates.get('G1', 'GENERIC')} | "
        f"G2: {gates.get('G2', 'GENERIC_INTENT')} | "
        f"G3: {gates.get('G3', 'SV0')}{modifier_segment} | "
        f"G4: {gates.get('G4', 'ALLOW')}] "
        f"You are PikuAI, a child-safe learning assistant. "
        f"Respond safely and age-appropriately in 5 lines or less. "
        f"Question: {message}"
    )
