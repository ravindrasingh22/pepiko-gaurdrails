from __future__ import annotations

from typing import Any

from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision


def _sentence(items: list[str]) -> str:
    cleaned = [item.strip().rstrip(".") for item in items if item.strip()]
    if not cleaned:
        return ""
    return ". ".join(item[:1].upper() + item[1:] if item else item for item in cleaned) + "."


def build_safety_envelope(child_profile: ChildProfile, message: str, decision: GuardrailDecision) -> dict[str, Any]:
    gates = decision.gates or decision.gate_values
    contract = decision.prompt_contract
    g2_all = list(gates.get("G2_all", [gates.get("G2", "GENERIC_INTENT")]))
    primary_g2 = str(gates.get("G2", "GENERIC_INTENT"))
    modifiers = list(contract.get("modifiers", []))
    return {
        "schema_version": "1.0.0",
        "question": {
            "text": message,
            "language": child_profile.language,
        },
        "user_context": {
            "age_band": child_profile.age_group,
            "age_settings": {
                "max_words": int(contract.get("max_words", 120)),
                "depth": str(contract.get("depth", "age_calibrated")),
                "style": str(contract.get("max_answer_style", "age-calibrated")),
                "tone": str(contract.get("tone", "age_calibrated")),
            },
        },
        "reason": decision.reason,
        "g1": {"id": str(gates.get("G1", "GENERIC"))},
        "g2": {"active_lovs": [{"id": item} for item in g2_all]},
        "g3": {
            "severity": str(gates.get("G3", "SV0")),
            "modifiers": modifiers,
            "source_g2": [primary_g2],
        },
        "g4": {
            "action": str(gates.get("G4", "ALLOW")),
        },
        "guidelines": {
            "active": list(decision.active_gls or decision.guideline_tags),
        },
        "prompt_policy_notes": list(contract.get("must_do", [])),
        "prompt_policy_blocks": list(contract.get("must_not_do", [])),
    }


def _pick_template(envelope: dict[str, Any]) -> dict[str, str]:
    g4 = envelope["g4"]["action"]
    g3 = envelope["g3"]["severity"]
    modifiers = set(envelope["g3"]["modifiers"])
    g2 = {item["id"] for item in envelope["g2"]["active_lovs"]}
    if g4 == "BLOCK_HARD" and "DANGEROUS" in g2 and "no_content_engagement" in modifiers:
        return {
            "id": "BLOCK_HARD_DANGEROUS",
            "template": (
                "[Age: {age_band} | G1: {g1} | G2: {g2} | G3: {g3} | {modifiers} | G4: {g4}]\n"
                "You are PikuAI, a child-safe learning assistant.\n"
                "Classifier reason: {reason}\n"
                "Broad content nature: {g1}\n"
                "Rules:\n"
                "- Respond in 5 lines or less.\n"
                "- Do not provide instructions or procedural details.\n"
                "- Follow all Must do and Must not do rules exactly.\n"
                "Question: \"{question}\""
            ),
        }
    if g4 == "ALLOW" and g3 == "SV0" and "NEUTRAL_FACT" in g2:
        return {
            "id": "ALLOW_NEUTRAL_FACT",
            "template": (
                "[Age: {age_band} | G1: {g1} | G2: {g2} | G3: {g3} | {modifiers} | G4: {g4}]\n"
                "You are PikuAI, a child-safe learning assistant.\n"
                "Classifier reason: {reason}\n"
                "Broad content nature: {g1}\n"
                "Rules:\n"
                "- Respond in 5 lines or less.\n"
                "- Explain clearly in at most {max_words} words.\n"
                "- Match depth {depth}, style {style}, and tone {tone}.\n"
                "- Follow all Must do and Must not do rules exactly.\n"
                "Question: \"{question}\""
            ),
        }
    if g4 == "TRANSFORM_HOLD":
        return {
            "id": "TRANSFORM_HOLD_AMBIGUOUS",
            "template": (
                "[Age: {age_band} | G1: {g1} | G2: {g2} | G3: {g3} | {modifiers} | G4: {g4}]\n"
                "You are PikuAI, a child-safe learning assistant.\n"
                "Classifier reason: {reason}\n"
                "Broad content nature: {g1}\n"
                "Rules:\n"
                "- Ask exactly one safe clarification question.\n"
                "- Do not answer before clarification.\n"
                "- Follow all Must do and Must not do rules exactly.\n"
                "Question: \"{question}\""
            ),
        }
    return {
        "id": "GENERIC_GATE_TEMPLATE",
        "template": (
            "[Age: {age_band} | G1: {g1} | G2: {g2} | G3: {g3} | {modifiers} | G4: {g4}]\n"
            "You are PikuAI, a child-safe learning assistant.\n"
            "Classifier reason: {reason}\n"
            "Broad content nature: {g1}\n"
            "Rules:\n"
            "- Respond in 5 lines or less.\n"
            "- Follow all Must do and Must not do rules exactly.\n"
            "Question: \"{question}\""
        ),
    }


def _apply_prompt_rules(envelope: dict[str, Any], rendered: str) -> str:
    modifiers = set(envelope["g3"]["modifiers"])
    if "no_curiosity_invite" in modifiers and "?" in rendered.splitlines()[-1]:
        rendered = rendered.rstrip("?")
    return rendered


def _checklist(envelope: dict[str, Any], rendered: str) -> dict[str, Any]:
    modifiers = set(envelope["g3"]["modifiers"])
    checks = {
        "CHK-01": "[Age:" in rendered,
        "CHK-02": all(token in rendered for token in ["G1:", "G2:", "G3:", "G4:"]),
        "CHK-03": "5 lines or less" in rendered or "at most" in rendered,
        "CHK-04": ("Ask exactly one safe clarification question" in rendered) if "clarification_required" in modifiers else True,
        "CHK-05": ("Do not provide instructions or procedural details." in rendered or "Avoid any engagement with the blocked topic" in rendered) if "no_content_engagement" in modifiers else True,
        "CHK-06": ("Ask a follow-up question" not in rendered) if "no_curiosity_invite" in modifiers else True,
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
        reason=envelope["reason"],
        max_words=envelope["user_context"]["age_settings"]["max_words"],
        depth=envelope["user_context"]["age_settings"]["depth"],
        style=envelope["user_context"]["age_settings"]["style"],
        tone=envelope["user_context"]["age_settings"]["tone"],
        question=message,
    )
    must_do = decision.prompt_contract.get("must_do", [])
    must_not_do = decision.prompt_contract.get("must_not_do", [])
    if must_do:
        rendered += "\nMust do: " + _sentence(list(must_do))
    if must_not_do:
        rendered += "\nMust not do: " + _sentence(list(must_not_do))
    rendered = _apply_prompt_rules(envelope, rendered)
    checklist = _checklist(envelope, rendered)
    return {
        "safety_envelope": envelope,
        "template_id": template["id"],
        "checklist": checklist,
        "prompt": rendered,
    }
