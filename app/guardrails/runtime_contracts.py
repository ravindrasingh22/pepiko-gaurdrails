from __future__ import annotations

import hashlib
import re
from typing import Any

from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision
from training.slm_classifier.codebook import CodebookSpec, parse_codebook


CODEBOOK: CodebookSpec = parse_codebook()

G2_ALIAS_MAP = {
    "PD": "PERSONAL_DIRECTION",
    "UNSAFE_CONTENT": "UNSAFE_SEXUAL_CONTENT",
}

PROTECTED_GROUP_TERMS = ("religion", "muslim", "hindu", "christian", "jew", "black", "white", "girl", "boy", "women", "men", "group", "people")
NEGATIVE_LANGUAGE_TERMS = ("disgusting", "lazy", "bad", "stupid", "hate", "get rid of", "dont deserve", "don't deserve", "gross")
SLUR_MARKERS = ("slur",)


def _question_id(question: str, age_band: str, language: str) -> str:
    payload = f"{language}|{age_band}|{question.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def canonicalize_g2_ids(raw_g2: list[str]) -> list[str]:
    seen: set[str] = set()
    canonical: list[str] = []
    for item in raw_g2:
        mapped = G2_ALIAS_MAP.get(item, item)
        if mapped in CODEBOOK.g2_specs and mapped not in seen:
            canonical.append(mapped)
            seen.add(mapped)
    if not canonical:
        canonical = ["GENERIC_INTENT"]
    return canonical


def build_applies_when_flags(question: str, g1_id: str, g2_ids: list[str]) -> dict[str, bool]:
    lowered = question.lower()
    has_harmful_comparison = bool(
        re.search(r"\b(which|what)\b.*\b(better|best|worse|more true|less important)\b", lowered)
        or ("better than" in lowered)
    )
    has_loaded_premise = bool(
        re.search(r"\bwhy are all\b", lowered)
        or re.search(r"\bsince .* are\b", lowered)
        or re.search(r"\beveryone says .* (lazy|bad|stupid)\b", lowered)
    )
    has_negative_language = any(term in lowered for term in NEGATIVE_LANGUAGE_TERMS) or "HATE_GROUP" in g2_ids
    is_protected_group_target = has_negative_language and any(term in lowered for term in PROTECTED_GROUP_TERMS)
    includes_slurs = any(term in lowered for term in SLUR_MARKERS)
    has_blackmail_pattern = bool(re.search(r"\b(if i don't|if i do not).*(tell everyone|tell my parents|share my secret)\b", lowered))
    has_dependency_pattern = bool(re.search(r"\bonly (they|he|she) understand(s)? me\b", lowered))
    has_vuln_exploitation = "VULN_EXPLOIT" in g2_ids or has_blackmail_pattern or has_dependency_pattern
    return {
        "has_harmful_comparison": has_harmful_comparison,
        "has_loaded_premise": has_loaded_premise,
        "has_negative_language": has_negative_language,
        "is_protected_group_target": is_protected_group_target,
        "includes_slurs": includes_slurs,
        "has_vuln_exploitation": has_vuln_exploitation,
        "has_blackmail_pattern": has_blackmail_pattern,
        "has_dependency_pattern": has_dependency_pattern,
    }


def classifier_output_from_decision(question: str, child_profile: ChildProfile, decision: GuardrailDecision) -> dict[str, Any]:
    gates = decision.gates or decision.gate_values
    g1_id = str(gates.get("G1", "GENERIC"))
    raw_g2 = list(gates.get("G2_all", [gates.get("G2", "GENERIC_INTENT")]))
    g2_ids = canonicalize_g2_ids(raw_g2)
    age_band = child_profile.age_group
    flags = build_applies_when_flags(question, g1_id, g2_ids)
    return {
        "schema_version": "2.0.0",
        "question_id": _question_id(question, age_band, child_profile.language),
        "question": question,
        "language": child_profile.language,
        "age_band": age_band,
        "applies_when_flags": flags,
        "g1": {
            "id": g1_id,
            "reason": decision.g1_reason or decision.reason,
        },
        "g2": [
            {
                "id": g2_id,
                "reason": decision.g2_reasons.get(raw, decision.g2_reasons.get(g2_id, decision.reason))
                if decision.g2_reasons
                else decision.reason,
            }
            for raw, g2_id in zip(raw_g2, g2_ids, strict=False)
        ] or [{"id": "GENERIC_INTENT", "reason": decision.reason}],
    }


def _severity_rank(severity: str) -> int:
    match = re.match(r"SV(\d+)", severity or "SV0")
    return int(match.group(1)) if match else 0


def compute_g3(g2_ids: list[str]) -> dict[str, Any]:
    severity = "SV0"
    modifiers: set[str] = set()
    for g2_id in g2_ids:
        spec = CODEBOOK.g2_specs.get(g2_id)
        if not spec:
            continue
        if _severity_rank(spec.severity_floor) > _severity_rank(severity):
            severity = spec.severity_floor
        modifiers.update(spec.modifiers)
    return {
        "severity": severity,
        "modifiers": sorted(modifiers),
        "source_g2": g2_ids,
    }


def _base_g4(severity: str, modifiers: list[str]) -> dict[str, str]:
    mods = set(modifiers)
    if "clarification_required" in mods:
        return {"action": "TRANSFORM_HOLD", "ending": "safe_disambiguation_question", "style": "Neutral"}
    if {"zero_engagement", "no_curiosity_invite", "no_content_engagement"}.issubset(mods):
        return {"action": "BLOCK_HARD", "ending": "(none)", "style": "None / Minimal"}
    if severity == "SV0":
        return {"action": "ALLOW", "ending": "curiosity_invite", "style": "Neutral, age-calibrated"}
    if severity == "SV1":
        ending = "(none)" if "no_curiosity_invite" in mods else "curiosity_invite"
        return {"action": "TRANSFORM", "ending": ending, "style": "Neutral, balanced"}
    if severity == "SV2":
        if {"escalate", "empathetic_tone"}.issubset(mods):
            return {"action": "TRANSFORM_ESCALATE", "ending": "curiosity_invite", "style": "Empathetic"}
        if {"empathetic_tone", "emotional_support_required"}.issubset(mods):
            return {"action": "TRANSFORM", "ending": "curiosity_invite", "style": "Empathetic, warm"}
        return {"action": "TRANSFORM", "ending": "curiosity_invite", "style": "Neutral, balanced"}
    if severity == "SV3":
        if {"escalate", "empathetic_tone", "no_curiosity_invite"}.issubset(mods):
            return {"action": "BLOCK_ESCALATE", "ending": "(none)", "style": "Empathetic"}
        if {"empathetic_tone", "no_curiosity_invite"}.issubset(mods):
            return {"action": "BLOCK", "ending": "(none)", "style": "Empathetic"}
        return {"action": "BLOCK", "ending": "neutral_alternate_question", "style": "Neutral"}
    return {"action": "TRANSFORM", "ending": "curiosity_invite", "style": "Neutral, balanced"}


def _g1_allowed(allowed: list[str], g1_id: str) -> bool:
    return not allowed or "Any (esp. BELIEF" in ",".join(allowed) or "Any" in allowed or g1_id in allowed


def _g2_allowed(allowed: list[str], g2_ids: list[str]) -> bool:
    if not allowed:
        return True
    allowed_set = {item.split(" ", 1)[0] for item in allowed}
    return any(g2 in allowed_set for g2 in g2_ids)


def _apply_gl_rules(
    classifier_output: dict[str, Any],
    g3: dict[str, Any],
    g4: dict[str, str],
) -> tuple[dict[str, Any], dict[str, str], list[str], list[str]]:
    flags = classifier_output["applies_when_flags"]
    g1_id = classifier_output["g1"]["id"]
    g2_ids = [item["id"] for item in classifier_output["g2"]]
    active_gl: list[str] = []
    prompt_notes: list[str] = []
    modifiers = set(g3["modifiers"])

    def activate(gl_id: str, notes: list[str]) -> None:
        if gl_id not in active_gl:
            active_gl.append(gl_id)
        prompt_notes.extend(notes)

    if flags["has_harmful_comparison"] and any(g2 in {"DANGEROUS", "VIOLENCE", "SELF_HARM", "HATE_GROUP", "UNSAFE_SEXUAL_CONTENT", "GROOMING"} for g2 in g2_ids):
        modifiers.add("no_curiosity_invite")
        if g1_id == "BELIEF":
            g4.update({"action": "TRANSFORM", "ending": "(none)", "style": "Neutral, balanced"})
        else:
            g4.update({"action": "BLOCK", "ending": "(none)", "style": "Neutral"})
        activate("GL-C1", [
            "Do not choose or rank harmful options.",
            "Do not describe harmful options comparatively.",
        ])

    if flags["has_loaded_premise"] and g1_id in {"BELIEF", "GENERIC", "FACT", "VIOLENCE"}:
        modifiers.add("needs_debiasing")
        activate("GL-L1", [
            "Correct or neutralize the biased premise before any allowed answer.",
            "Do not treat the biased premise as true.",
        ])

    if flags["has_negative_language"] and (g1_id in {"BELIEF", "GENERIC", "FACT", "VIOLENCE", "DEATH_GRIEF"}):
        if flags["is_protected_group_target"]:
            modifiers.add("flag_for_review")
        activate("GL-N1", [
            "Do not repeat abusive language in the model's own voice.",
            "Do not endorse the abusive framing.",
        ])

    if flags["has_vuln_exploitation"] and (flags["has_blackmail_pattern"] or flags["has_dependency_pattern"]) and "VULN_EXPLOIT" in g2_ids:
        modifiers.update({"escalate", "safeguarding_concern"})
        if "GROOMING" in g2_ids or "UNSAFE_SEXUAL_CONTENT" in g2_ids:
            g4.update({"action": "BLOCK_HARD", "ending": "(none)", "style": "None / Minimal"})
        else:
            g4.update({"action": "BLOCK_ESCALATE", "ending": "(none)", "style": "Empathetic"})
        activate("GL-V1", [
            "Acknowledge the child's feelings without blame.",
            "Append a trusted-adult prompt where allowed by the gate path.",
        ])

    g3["modifiers"] = sorted(modifiers)
    return g3, g4, active_gl, prompt_notes


def gate_output_from_classifier(classifier_output: dict[str, Any]) -> dict[str, Any]:
    g2_ids = [item["id"] for item in classifier_output["g2"]]
    g3 = compute_g3(g2_ids)
    g4 = _base_g4(g3["severity"], g3["modifiers"])
    g3, g4, active_gl, prompt_notes = _apply_gl_rules(classifier_output, g3, g4)
    if g3["modifiers"] != sorted(set(g3["modifiers"])):
        g3["modifiers"] = sorted(set(g3["modifiers"]))
    if g4["action"] in {"BLOCK_ESCALATE", "TRANSFORM_ESCALATE"} and "escalate" not in g3["modifiers"]:
        g3["modifiers"].append("escalate")
    return {
        "g3": g3,
        "g4": g4,
        "gl": {"active": active_gl},
        "prompt_policy_notes": prompt_notes,
    }


def safety_envelope_from_runtime(classifier_output: dict[str, Any], gate_output: dict[str, Any]) -> dict[str, Any]:
    age_band = classifier_output["age_band"]
    age_settings = CODEBOOK.age_bands[age_band]
    return {
        "schema_version": "2.0.0",
        "question": {
            "id": classifier_output["question_id"],
            "text": classifier_output["question"],
            "language": classifier_output["language"],
        },
        "applies_when_flags": classifier_output["applies_when_flags"],
        "user_context": {
            "age_band": age_band,
            "age_settings": {
                "max_words": age_settings.max_words,
                "depth": age_settings.depth,
                "style": age_settings.max_answer_style,
            },
        },
        "g1": {"id": classifier_output["g1"]["id"]},
        "g2": {"active_lovs": [{"id": item["id"]} for item in classifier_output["g2"]]},
        "g3": gate_output["g3"],
        "g4": gate_output["g4"],
        "gl": gate_output["gl"],
        "prompt_policy_notes": gate_output["prompt_policy_notes"],
    }


def prompt_contract_payload(question: str, child_profile: ChildProfile, decision: GuardrailDecision, final_prompt: str, template_id: str) -> dict[str, Any]:
    classifier_output = classifier_output_from_decision(question, child_profile, decision)
    gate_output = gate_output_from_classifier(classifier_output)
    envelope = safety_envelope_from_runtime(classifier_output, gate_output)
    return {
        "raw_infer": classifier_output,
        "gates": gate_output,
        "safety_envelope": envelope,
        "prompt_template": {"id": template_id},
        "final_prompt": final_prompt,
    }
