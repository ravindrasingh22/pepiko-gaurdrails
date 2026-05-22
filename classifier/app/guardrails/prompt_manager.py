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
                "[Age: {age_band} | G1: {g1} | G2: {g2} | G3: {g3} | {modifiers} | G4: {g4}]\n"
                "You are PikuAI, a child-safe learning assistant.\n"
                "Respond in 5 lines or less.\n"
                "Do not explain the blocked topic.\n"
                "Do not ask a follow-up question.\n"
                "Question: \"{question}\""
            ),
        }
    if g4 == "TRANSFORM_HOLD" and "AMBIGUOUS_RISK" in g2:
        return {
            "id": "HBT-02",
            "template": (
                "[Age: {age_band} | G1: {g1} | G2: {g2} | G3: {g3} | {modifiers} | G4: {g4}]\n"
                "You are PikuAI, a child-safe learning assistant.\n"
                "Ask exactly one safe clarification question.\n"
                "Do not answer before clarification.\n"
                "Question: \"{question}\""
            ),
        }
    return {
        "id": "GENERIC_GATE_TEMPLATE",
        "template": (
            "[Age: {age_band} | G1: {g1} | G2: {g2} | G3: {g3} | {modifiers} | G4: {g4}]\n"
            "You are PikuAI, a child-safe learning assistant.\n"
            "Respond in 5 lines or less.\n"
            "Match explanation depth {depth}, style {style}, and age calibration.\n"
            "Follow all prompt-policy notes exactly.\n"
            "Question: \"{question}\""
        ),
    }


def _apply_prompt_rules(envelope: dict[str, Any], rendered: str) -> str:
    modifiers = set(envelope["g3"]["modifiers"])
    if "no_curiosity_invite" in modifiers and rendered.rstrip().endswith("?"):
        rendered = rendered.rstrip().rstrip("?")
    return rendered


def _checklist(envelope: dict[str, Any], rendered: str) -> dict[str, Any]:
    modifiers = set(envelope["g3"]["modifiers"])
    checks = {
        "CHK-01": "[Age:" in rendered,
        "CHK-02": all(token in rendered for token in ["G1:", "G2:", "G3:", "G4:"]),
        "CHK-03": "5 lines or less" in rendered or "exactly one safe clarification question" in rendered,
        "CHK-04": ("Ask exactly one safe clarification question." in rendered) if "clarification_required" in modifiers else True,
        "CHK-05": ("Do not explain the blocked topic." in rendered) if "no_content_engagement" in modifiers else True,
        "CHK-06": (not rendered.rstrip().endswith("?")) if "no_curiosity_invite" in modifiers else True,
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
        g4=envelope["g4"]["action"],
        depth=envelope["user_context"]["age_settings"]["depth"],
        style=envelope["user_context"]["age_settings"]["style"],
        question=message,
    )
    notes = envelope.get("prompt_policy_notes", [])
    if notes:
        rendered += "\nPrompt-policy notes: " + " ".join(notes)
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
