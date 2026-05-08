from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision


def _sentence(items: list[str]) -> str:
    cleaned = [item.strip().rstrip(".") for item in items if item.strip()]
    if not cleaned:
        return ""
    return ". ".join(item[:1].upper() + item[1:] if item else item for item in cleaned) + "."


def build(
    child_profile: ChildProfile,
    message: str,
    decision: GuardrailDecision,
    rag_context: list[dict[str, object]],
) -> str:
    gates = decision.gates or decision.gate_values
    contract = decision.prompt_contract
    must_do = _sentence(list(contract.get("must_do", [])))
    must_not_do_items = list(contract.get("must_not_do", []))
    caution = ""
    if must_not_do_items:
        caution = " Do not " + "; do not ".join(item.strip().rstrip(".") for item in must_not_do_items if item.strip()) + "."
    return (
        f"You are a PikuAI assistant. "
        f"You are answering for a {child_profile.age_group} year old child. "
        f"G1: {gates.get('G1', 'GENERIC')} | G2: {gates.get('G2', 'GENERIC_INTENT')} | "
        f"G3: {gates.get('G3', 'SV0')} | G4: {gates.get('G4', 'ALLOW')}. "
        f"{must_do}{caution} "
        f"Question: {message}"
    )
