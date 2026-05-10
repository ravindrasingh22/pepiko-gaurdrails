from __future__ import annotations

import re
from typing import Any

from app.models.guardrail_decision import GLSignal
from training.slm_classifier.codebook import parse_codebook


CODEBOOK = parse_codebook()
GUIDELINES = {
    label.gl_id: {
        "name": label.name,
        "emits": {emit: True for emit in label.emits if emit},
    }
    for label in CODEBOOK.labels
}
G2_SPECS = CODEBOOK.g2_specs
GL_TO_G2 = {
    "GL-02": "COMPARATIVE",
    "GL-03": "PD",
    "GL-04": "LP",
    "GL-05": "DANGEROUS",
    "GL-06": "EMOTIONAL",
    "GL-08": "HATE_GROUP",
    "GL-09": "NEUTRAL_FACT",
    "GL-10": "GROOMING",
    "GL-11": "UNSAFE_CONTENT",
    "GL-12": "COERCIVE_CONTROL",
    "GL-13": "VULN_EXPLOIT",
}
G2_PRIORITY = [
    "UNSAFE_CONTENT",
    "GROOMING",
    "COERCIVE_CONTROL",
    "VULN_EXPLOIT",
    "DANGEROUS",
    "HATE_GROUP",
    "PD",
    "LP",
    "COMPARATIVE",
    "EMOTIONAL",
    "NEUTRAL_FACT",
    "GENERIC_INTENT",
]
AGE_BANDS = CODEBOOK.age_bands
AGE_POLICY = {
    band: {
        "max_words": spec.max_words,
        "max_answer_style": spec.max_answer_style,
        "depth": spec.depth,
        "tone": spec.tone,
    }
    for band, spec in AGE_BANDS.items()
    if spec.max_words is not None and spec.depth
}


AGE_RANGES = [
    (5, 6, "5-6"),
    (7, 8, "7-8"),
    (9, 10, "9-10"),
    (11, 12, "11-12"),
    (13, 14, "13-14"),
    (15, 16, "15-16"),
    (17, 17, "17"),
]


def active_gls(gl_signals: dict[str, GLSignal]) -> set[str]:
    return {gl_id for gl_id, signal in gl_signals.items() if signal.triggered}


def age_band_from_age(age: int) -> str:
    for low, high, band in AGE_RANGES:
        if low <= age <= high:
            return band
    return "11-12"


def _lower_age_from_band(age_band: str) -> int | None:
    match = re.match(r"^\s*(\d{1,2})(?:-(\d{1,2}))?\s*$", age_band)
    if not match:
        return None
    return max(5, min(int(match.group(1)), 17))


def resolve_age_band(age: int, requested_age_band: str | None = None) -> str:
    if requested_age_band and requested_age_band in AGE_POLICY:
        return requested_age_band
    if requested_age_band:
        lower_age = _lower_age_from_band(requested_age_band)
        if lower_age is not None:
            return age_band_from_age(lower_age)
    return age_band_from_age(age)


def map_g1(gls: set[str]) -> str:
    if "GL-05" in gls or "GL-10" in gls or "GL-11" in gls or "GL-12" in gls or "GL-13" in gls:
        return "VIOLENCE"
    if "GL-06" in gls:
        return "DEATH_GRIEF"
    if "GL-09" in gls and not (gls & {"GL-02", "GL-03", "GL-04", "GL-08"}):
        return "FACT"
    if gls & {"GL-02", "GL-03", "GL-04", "GL-08"}:
        return "BELIEF"
    if "GL-07" in gls:
        return "SCIENCE"
    return "GENERIC"


def map_g2_list(gls: set[str]) -> list[str]:
    values = [g2 for gl_id, g2 in GL_TO_G2.items() if gl_id in gls]
    return values or ["GENERIC_INTENT"]


def map_g2_primary(g2_list: list[str]) -> str:
    for item in G2_PRIORITY:
        if item in g2_list:
            return item
    return "GENERIC_INTENT"


def map_g3(g2_list: list[str]) -> str:
    highest = "SV0"
    for g2 in g2_list:
        severity = G2_SPECS.get(g2).severity_floor if g2 in G2_SPECS else "SV2" if g2 == "GENERIC_INTENT" else "SV0"
        if severity > highest:
            highest = severity
    return highest


def g3_modifiers(g2_list: list[str]) -> list[str]:
    modifiers: list[str] = []
    for g2 in g2_list:
        spec = G2_SPECS.get(g2)
        if spec:
            modifiers.extend(spec.modifiers)
    return list(dict.fromkeys(modifiers))


def map_g4(g3: str) -> str:
    if g3 == "SV0":
        return "ALLOW"
    if g3 in {"SV1", "SV2"}:
        return "TRANSFORM"
    return "BLOCK"


def build_decision_from_g4(g4: str, g3: str, g2_list: list[str]) -> dict[str, Any]:
    risk_by_severity = {"SV0": "low", "SV1": "low", "SV2": "medium", "SV3": "high", "SV4": "critical"}
    if g4 == "BLOCK":
        return {
            "allow_llm": False,
            "allow_rag": False,
            "response_mode": "safe_refusal",
            "risk_level": risk_by_severity.get(g3, "high"),
            "parent_visible": any(item in {"GROOMING", "UNSAFE_CONTENT", "COERCIVE_CONTROL", "VULN_EXPLOIT"} for item in g2_list),
        }
    if g4 == "TRANSFORM":
        return {
            "allow_llm": True,
            "allow_rag": False,
            "response_mode": "guide_or_redirect" if any(item in {"PD", "EMOTIONAL", "DANGEROUS"} for item in g2_list) else "neutral_age_calibrated_explain",
            "risk_level": risk_by_severity.get(g3, "medium"),
            "parent_visible": False,
        }
    return {
        "allow_llm": True,
        "allow_rag": False,
        "response_mode": "neutral_age_calibrated_explain",
        "risk_level": "low",
        "parent_visible": False,
    }


def build_prompt_contract(g4: str, g3: str, g2_list: list[str], age_band: str) -> dict[str, Any]:
    age_cfg = AGE_POLICY[age_band]
    modifiers = g3_modifiers(g2_list)
    must_do: list[str] = []
    must_not_do: list[str] = []
    if g4 == "ALLOW":
        must_do.append("answer directly, neutrally, and age-appropriately")
    if g4 == "TRANSFORM":
        must_do.append("reframe or simplify the question for the child's age band")
        if "empathetic_tone" in modifiers:
            must_do.append("acknowledge feelings first")
        if "emotional_support_required" in modifiers:
            must_do.append("validate that it is okay to feel this way")
        if "redirect_preferred" in modifiers:
            must_do.append("suggest a safer alternative topic or activity")
        if "safeguarding_concern" in modifiers:
            must_do.append("append a trusted-adult prompt")
        if "no_curiosity_invite" not in modifiers and "clarification_required" not in modifiers:
            must_do.append("end with a curiosity invite")
        if "clarification_required" in modifiers:
            must_do.append("end with one safe clarifying question")
    if g4 == "BLOCK":
        if "no_reason_given" not in modifiers:
            must_do.append("refuse briefly and give a neutral alternate question")
        else:
            must_do.append("refuse briefly with zero engagement")
        if "safeguarding_concern" in modifiers:
            must_do.append("tell the child to talk to a trusted adult")
        if "empathetic_tone" in modifiers:
            must_do.append("use an empathetic tone")
        must_not_do.extend(["provide instructions", "provide materials", "provide steps"])
    for g2 in g2_list:
        if g2 == "COMPARATIVE":
            must_do.append("do not rank beliefs")
        if g2 == "PD":
            must_do.append("avoid telling the child what to believe or choose")
        if g2 == "LP":
            must_do.append("neutralize the loaded premise before answering")
        if g2 == "HATE_GROUP":
            must_do.append("do not reproduce derogatory framing")
        if g2 == "DANGEROUS":
            must_do.append("avoid procedural detail")
        if g2 == "GROOMING":
            must_do.append("treat secrecy with an adult as unsafe")
        if g2 == "UNSAFE_CONTENT":
            must_do.append("do not engage with explicit content")
    return {
        "age_band": age_band,
        "max_words": age_cfg["max_words"],
        "max_answer_style": age_cfg["max_answer_style"],
        "depth": age_cfg["depth"],
        "tone": "calm_child_safe_supportive" if g3 in {"SV3", "SV4"} else age_cfg["tone"],
        "must_do": list(dict.fromkeys(must_do)),
        "must_not_do": list(dict.fromkeys(must_not_do)),
        "modifiers": modifiers,
    }


def build_guardrail_decision(
    question: str,
    age_band: str,
    language: str,
    recent_context: str,
    gl_signals: dict[str, GLSignal],
) -> dict[str, Any]:
    gls = active_gls(gl_signals)
    g1 = map_g1(gls)
    g2_list = map_g2_list(gls)
    g2_primary = map_g2_primary(g2_list)
    g3 = map_g3(g2_list)
    g4 = map_g4(g3)
    return {
        "input": {"question": question, "age_band": age_band, "language": language, "recent_context": recent_context},
        "gl_signals": gl_signals,
        "active_gls": sorted(gls),
        "gates": {"G1": g1, "G2": g2_primary, "G2_all": g2_list, "G3": g3, "G4": g4},
        "decision": build_decision_from_g4(g4, g3, g2_list),
        "prompt_contract": build_prompt_contract(g4, g3, g2_list, age_band),
    }
