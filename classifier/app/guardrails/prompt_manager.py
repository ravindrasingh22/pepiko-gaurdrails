from __future__ import annotations

from typing import Any

from app.guardrails.runtime_contracts import (
    classifier_output_from_decision,
    gate_output_from_classifier,
    prompt_contract_payload,
    safety_envelope_from_runtime,
)
from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision
from training.slm_classifier.codebook import parse_codebook


CODEBOOK = parse_codebook()


RUNTIME_MODIFIER_RULES = {
    "clarification_required": "Ask exactly one safe clarification question before answering.",
    "empathetic_tone": "Use a warm, empathetic tone.",
    "emotional_support_required": "Acknowledge feelings briefly without acting like a therapist.",
    "escalate": "Include a trusted-adult help-seeking direction.",
    "flag_for_review": "Avoid endorsing the premise and keep the response conservative.",
    "needs_debiasing": "Correct or neutralize biased assumptions before answering.",
    "no_content_engagement": "Do not explain, describe, or provide details about the unsafe content.",
    "no_curiosity_invite": "Do not end with a curiosity or follow-up question.",
    "safeguarding_concern": "Prioritize the child's safety and point them toward a trusted adult.",
    "zero_engagement": "Do not engage with the unsafe request beyond a brief safety boundary.",
}


def _codebook_modifier_descriptions() -> dict[str, str]:
    descriptions: dict[str, str] = {}
    for tags in CODEBOOK.modifier_tags.values():
        for tag, spec in tags.items():
            descriptions[tag] = spec.description
    return descriptions


def _modifier_rules(modifiers: list[str]) -> str:
    codebook_rules = _codebook_modifier_descriptions()
    rules = [
        codebook_rules.get(modifier) or RUNTIME_MODIFIER_RULES.get(modifier) or modifier.replace("_", " ").capitalize() + "."
        for modifier in modifiers
    ]
    if not rules:
        return "Use standard safe-learning behavior: be accurate, calm, age-appropriate, and do not add unnecessary risk detail."
    return " ".join(rule.rstrip(".") + "." for rule in rules)


def _prompt_policy_instruction(envelope: dict[str, Any]) -> str:
    notes = [str(note).strip() for note in envelope.get("prompt_policy_notes", []) if str(note).strip()]
    if not notes:
        return "No additional prompt-policy notes are active."
    return "Follow these prompt-policy notes exactly: " + " ".join(note.rstrip(".") + "." for note in notes)


def build_safety_envelope(child_profile: ChildProfile, message: str, decision: GuardrailDecision) -> dict[str, Any]:
    classifier_output = classifier_output_from_decision(message, child_profile, decision)
    gate_output = gate_output_from_classifier(classifier_output)
    return safety_envelope_from_runtime(classifier_output, gate_output)


def _pick_template(envelope: dict[str, Any]) -> dict[str, str]:
    g4 = envelope["g4"]["action"]
    g3 = envelope["g3"]["severity"]
    modifiers = set(envelope["g3"]["modifiers"])
    g2 = {item["id"] for item in envelope["g2"]["active_lovs"]}
    if g4 == "BLOCK_HARD" and "DANGEROUS" in g2 and "no_content_engagement" in modifiers:
        return {
            "id": "HBT-01",
            "template": (
                "You are PikuAI, a child-safe learning assistant.\n"
                "The child is in age band {age_band}; use explanation depth {depth}, style {style}, and age-calibrated wording.\n"
                "Respond in 5 lines or less.\n"
                "Active safety rules: {modifier_rules}\n"
                "{prompt_policy_instruction}\n"
                "Do not explain the blocked topic.\n"
                "Do not ask a follow-up question.\n"
                "Context: {context}"
            ),
        }
    if g4 == "TRANSFORM_HOLD" and "AMBIGUOUS_RISK" in g2:
        return {
            "id": "HBT-02",
            "template": (
                "You are PikuAI, a child-safe learning assistant.\n"
                "The child is in age band {age_band}; use explanation depth {depth}, style {style}, and age-calibrated wording.\n"
                "Active safety rules: {modifier_rules}\n"
                "{prompt_policy_instruction}\n"
                "Ask exactly one safe clarification question.\n"
                "Do not answer before clarification.\n"
                "Context: {context}"
            ),
        }
    return {
        "id": "GENERIC_GATE_TEMPLATE",
        "template": (
            "You are PikuAI, a child-safe learning assistant.\n"
            "The child is in age band {age_band}; use explanation depth {depth}, style {style}, and age-calibrated wording.\n"
            "Respond in 5 lines or less.\n"
            "Active safety rules: {modifier_rules}\n"
            "{prompt_policy_instruction}\n"
            "Context: {context}"
        ),
    }


def _apply_prompt_rules(envelope: dict[str, Any], rendered: str) -> str:
    modifiers = set(envelope["g3"]["modifiers"])
    if "no_curiosity_invite" in modifiers and rendered.rstrip().endswith("?"):
        rendered = rendered.rstrip().rstrip("?")
    return rendered


def _format_g3_forward(envelope: dict[str, Any]) -> str:
    g3_forward = envelope["g3_forward"]
    modifiers = g3_forward["modifiers"]
    modifier_text = ", ".join(modifiers) if modifiers else "none"
    return f"{g3_forward['severity']} + {{{modifier_text}}}"


def _checklist(envelope: dict[str, Any], rendered: str) -> dict[str, Any]:
    modifiers = set(envelope["g3"]["modifiers"])
    checks = {
        "CHK-01": "You are PikuAI, a child-safe learning assistant." in rendered,
        "CHK-02": all(token not in rendered for token in ["[Age:", "G1:", "G2:", "G3:", "G4:", "Codebook flow:"]),
        "CHK-03": "5 lines or less" in rendered or "exactly one safe clarification question" in rendered,
        "CHK-04": ("Ask exactly one safe clarification question." in rendered) if "clarification_required" in modifiers else True,
        "CHK-05": ("Do not explain the blocked topic." in rendered) if "no_content_engagement" in modifiers else True,
        "CHK-06": (not rendered.rstrip().endswith("?")) if "no_curiosity_invite" in modifiers else True,
        "CHK-07": f"The child is in age band {envelope['user_context']['age_band']}" in rendered,
        "CHK-08": "Active safety rules:" in rendered,
        "CHK-09": "Question:" not in rendered,
    }
    return {"passed": all(checks.values()), "checks": checks}


def render_prompt(child_profile: ChildProfile, message: str, decision: GuardrailDecision) -> dict[str, Any]:
    envelope = build_safety_envelope(child_profile, message, decision)
    template = _pick_template(envelope)
    g2_values = [item["id"] for item in envelope["g2"]["active_lovs"]]
    rendered = template["template"].format(
        age_band=envelope["user_context"]["age_band"],
        g1=envelope["g1"]["id"],
        g2=";".join(g2_values),
        g3=envelope["g3"]["severity"],
        modifiers=", ".join(envelope["g3"]["modifiers"]) if envelope["g3"]["modifiers"] else "none",
        g3_forward=_format_g3_forward(envelope),
        g4=envelope["g4"]["action"],
        depth=envelope["user_context"]["age_settings"]["depth"],
        style=envelope["user_context"]["age_settings"]["style"],
        modifier_rules=_modifier_rules(envelope["g3"]["modifiers"]),
        prompt_policy_instruction=_prompt_policy_instruction(envelope),
        context=str(decision.input.get("recent_context") or "none"),
    )
    rendered = _apply_prompt_rules(envelope, rendered)
    checklist = _checklist(envelope, rendered)
    payload = prompt_contract_payload(message, child_profile, decision, rendered, template["id"])
    payload["prompt_template"] = {
        "id": template["id"],
        "template": template["template"],
    }
    return {
        "safety_envelope": envelope,
        "template_id": template["id"],
        "checklist": checklist,
        "prompt": rendered,
        "prompt_contract_payload": payload,
    }
