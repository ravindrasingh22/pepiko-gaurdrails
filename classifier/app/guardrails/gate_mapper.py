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

G1_PRIORITY = [
    "VIOLENCE",
    "SAFETY_HAZARD",
    "TECHNOLOGY",
    "SCIENCE",
    "BELIEF",
    "DEATH_GRIEF",
    "CIVIC_LAW",
    "FACT",
    "GENERIC",
]

G1_RULES = {
    "SCIENCE": ("space", "earth", "moon", "sun", "planet", "star", "galaxy", "galaxies", "universe", "black hole", "gravity", "white dwarf", "physics", "animal", "plant", "chemical", "dark energy", "hawking radiation", "relativity", "chandrasekhar"),
    "TECHNOLOGY": ("computer", "internet", "ai", "chatgpt", "phone", "app", "password", "wifi", "software", "code", "network", "device", "laptop", "hack"),
    "BELIEF": ("god", "religion", "faith", "heaven", "temple", "prayer", "pray", "mosque", "church", "gurdwara", "ideology"),
    "DEATH_GRIEF": ("died", "death", "funeral", "grief", "miss someone", "why do people die", "loss"),
    "VIOLENCE": ("kill", "hurt", "fight", "weapon", "bomb", "terrorist", "attack", "radicalisation", "radicalization"),
    "SAFETY_HAZARD": ("fire", "shock", "electricity", "burn", "explosion", "knife", "chemical", "hazard", "risk", "dangerous", "poison", "fumes", "sharp", "choke", "short circuit"),
    "CIVIC_LAW": ("fake document", "cheat exam", "illegal", "bribe", "visa", "piracy", "tamper", "rig", "cheat", "advantage", "foul", "fake an injury", "waste time", "cross border", "without papers", "tax fraud", "bypass checks"),
}


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


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    tokens = set(re.findall(r"[a-z0-9']+", lowered))
    for term in terms:
        if " " in term:
            if term in lowered:
                return True
            continue
        if term in tokens:
            return True
    return False


def _infer_g1_from_question(question: str) -> str | None:
    lowered = question.lower().strip()
    if not lowered:
        return None
    matches = {label for label, terms in G1_RULES.items() if _contains_any(lowered, terms)}
    if not matches:
        return "FACT" if re.match(r"^(what|why|how|when|where|who|explain|define|tell me)\b", lowered) else None
    for label in G1_PRIORITY:
        if label in matches:
            return label
    return None


def map_g1(gls: set[str], question: str = "") -> str:
    inferred = _infer_g1_from_question(question)
    if inferred:
        return inferred
    if "GL-05" in gls:
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


def map_g4(g3: str, g2_list: list[str], modifiers: list[str]) -> str:
    mod_set = set(modifiers)
    if "clarification_required" in mod_set:
        return "TRANSFORM_HOLD"
    if any(item in {"UNSAFE_CONTENT", "GROOMING"} for item in g2_list) or ("no_content_engagement" in mod_set and g3 == "SV3"):
        return "BLOCK_HARD"
    if any(item in {"SELF_HARM"} for item in g2_list):
        return "BLOCK_ESCALATE"
    if g3 == "SV0":
        return "ALLOW"
    if g3 in {"SV1", "SV2"}:
        return "TRANSFORM"
    if "safeguarding_concern" in mod_set:
        return "BLOCK_ESCALATE"
    return "BLOCK"


def build_classifier_reason(g1: str, g2_list: list[str], gls: set[str], question: str = "", primary_g2: str | None = None) -> str:
    resolved_primary_g2 = primary_g2 or map_g2_primary(g2_list)
    lowered = question.lower().strip()
    if resolved_primary_g2 == "PD":
        if g1 == "BELIEF":
            return "The child is asking for personal guidance about what they should believe or choose, so the system should avoid directing the child's beliefs."
        return "The child is asking for personal guidance about what they should do or choose, so the system should avoid giving direct personal direction."
    if resolved_primary_g2 == "GROOMING":
        return "The question includes unsafe secrecy or boundary-crossing behaviour involving an adult or trusted person, which triggers grooming-safety handling."
    if resolved_primary_g2 == "UNSAFE_CONTENT":
        return "The question refers to explicitly unsafe sexual content, which requires a hard safety block."
    if resolved_primary_g2 == "EMOTIONAL":
        return "The child appears upset, distressed, or in need of emotional support, so the response should acknowledge feelings before answering."
    if resolved_primary_g2 == "DANGEROUS":
        if "bypass" in lowered and "safety" in lowered:
            return "The child is asking how to bypass safety measures, which is treated as dangerous guidance."
        return "The question seeks harmful, dangerous, or unsafe guidance, so the system should avoid procedural help."
    g1_reason_map = {
        "FACT": "The question is asking for factual or descriptive information.",
        "BELIEF": "The question is about belief, religion, or worldview.",
        "DEATH_GRIEF": "The question is about death, grief, or loss.",
        "VIOLENCE": "The question is about violence, harm, or dangerous acts.",
        "SCIENCE": "The question is about science or nature.",
        "TECHNOLOGY": "The question is about technology or digital systems.",
        "SAFETY_HAZARD": "The question is about safety risks or hazards.",
        "CIVIC_LAW": "The question is about rules, law, cheating, or institutional integrity.",
        "GENERIC": "The question does not fit a more specific broad topic cleanly.",
    }
    g2_reason_map = {
        "NEUTRAL_FACT": "It is framed as a neutral factual question.",
        "COMPARATIVE": "It asks to compare or rank beliefs or groups.",
        "PD": "It asks for personal direction or endorsement.",
        "LP": "It includes a loaded or biased premise.",
        "HATE_GROUP": "It uses negative or derogatory group framing.",
        "DANGEROUS": "It asks about bypassing safety, harmful activity, or dangerous instructions.",
        "EMOTIONAL": "It shows emotional distress or upset.",
        "BULLYING": "It describes bullying or peer harm.",
        "GROOMING": "It shows grooming-related secrecy or unsafe adult-child dynamics.",
        "UNSAFE_CONTENT": "It refers to sexually unsafe or explicitly disallowed content.",
        "COERCIVE_CONTROL": "It describes fear-based or controlling behaviour by another person.",
        "VULN_EXPLOIT": "It suggests exploitation of vulnerability or manipulation.",
        "SELF_HARM": "It includes self-harm or suicidal signals.",
        "AMBIGUOUS_RISK": "It could have both safe and unsafe interpretations.",
        "GENERIC_INTENT": "It has general intent without a stronger specific framing signal.",
    }
    gl_reason_map = {
        "GL-01": "Age-calibrated response handling applies.",
        "GL-03": "Personal-direction guidance applies.",
        "GL-05": "Dangerous or harmful activity guidance applies.",
        "GL-06": "Emotional-support guidance applies.",
        "GL-07": "Complexity-threshold guidance applies for younger children.",
        "GL-10": "Grooming-safety guidance applies.",
        "GL-11": "Unsafe-content blocking guidance applies.",
        "GL-12": "Coercive-control safeguarding guidance applies.",
        "GL-13": "Vulnerability-exploitation safeguarding guidance applies.",
    }
    parts: list[str] = []
    if g1 in g1_reason_map:
        parts.append(g1_reason_map[g1])
    if g2_list:
        parts.append(" ".join(g2_reason_map[item] for item in g2_list if item in g2_reason_map))
    gl_notes = [gl_reason_map[item] for item in sorted(gls) if item in gl_reason_map and item != "GL-01"]
    if gl_notes:
        parts.append(" ".join(gl_notes))
    return " ".join(part.strip() for part in parts if part.strip())


def build_g1_reason(g1: str, g2_list: list[str], question: str = "") -> str:
    if g1 == "BELIEF" and "NEUTRAL_FACT" in g2_list:
        return "The question is primarily about belief, religion, or worldview without direct personal guidance."
    g1_reason_map = {
        "FACT": "The question is primarily factual or descriptive.",
        "BELIEF": "The question is primarily about belief, religion, or worldview.",
        "DEATH_GRIEF": "The question is primarily about death, grief, or loss.",
        "VIOLENCE": "The question is primarily about violence, harm, or dangerous acts.",
        "SCIENCE": "The question is primarily about science or nature.",
        "TECHNOLOGY": "The question is primarily about technology or digital systems.",
        "SAFETY_HAZARD": "The question is primarily about safety risks or hazards.",
        "CIVIC_LAW": "The question is primarily about rules, law, cheating, or institutional integrity.",
        "GENERIC": "The question is handled as a general child-safety question rather than a domain-specific knowledge request.",
    }
    return g1_reason_map.get(g1, "The question has been assigned a broad topic classification for downstream gate handling.")


def build_g2_reasons(g1: str, g2_list: list[str], question: str = "", primary_g2: str | None = None) -> dict[str, str]:
    lowered = question.lower().strip()
    reasons: dict[str, str] = {}
    for g2 in g2_list:
        if g2 == "PD":
            reasons[g2] = (
                "The question asks what the child should personally believe or choose."
                if g1 == "BELIEF"
                else "The question asks what the child should personally do or choose."
            )
        elif g2 == "GROOMING":
            reasons[g2] = "The question includes unsafe secrecy or boundary-crossing behaviour involving an adult or trusted person."
        elif g2 == "UNSAFE_CONTENT":
            reasons[g2] = "The question refers to explicitly unsafe sexual content."
        elif g2 == "EMOTIONAL":
            reasons[g2] = "The question shows emotional distress or a need for emotional support."
        elif g2 == "DANGEROUS":
            reasons[g2] = (
                "The question asks how to bypass safety measures or perform risky activity."
                if "bypass" in lowered and "safety" in lowered
                else "The question seeks harmful, dangerous, or unsafe guidance."
            )
        elif g2 == "NEUTRAL_FACT":
            reasons[g2] = "The question is framed as a neutral factual query."
        elif g2 == "COMPARATIVE":
            reasons[g2] = "The question asks to compare or rank options, groups, or beliefs."
        elif g2 == "LP":
            reasons[g2] = "The question includes a loaded or biased premise."
        elif g2 == "HATE_GROUP":
            reasons[g2] = "The question uses negative or derogatory group framing."
        elif g2 == "BULLYING":
            reasons[g2] = "The question describes bullying or peer harm."
        elif g2 == "COERCIVE_CONTROL":
            reasons[g2] = "The question describes fear-based or controlling behaviour by another person."
        elif g2 == "VULN_EXPLOIT":
            reasons[g2] = "The question suggests exploitation of vulnerability or manipulation."
        elif g2 == "SELF_HARM":
            reasons[g2] = "The question includes self-harm or suicidal signals."
        elif g2 == "AMBIGUOUS_RISK":
            reasons[g2] = "The question could have both safe and unsafe interpretations."
        elif g2 == "GENERIC_INTENT":
            reasons[g2] = "The question has general intent without a stronger specific framing signal."
    return reasons


def build_decision_from_g4(g4: str, g3: str, g2_list: list[str]) -> dict[str, Any]:
    risk_by_severity = {"SV0": "low", "SV1": "low", "SV2": "medium", "SV3": "high", "SV4": "critical"}
    if g4 in {"BLOCK", "BLOCK_HARD", "BLOCK_ESCALATE"}:
        return {
            "allow_llm": False,
            "allow_rag": False,
            "response_mode": "safe_refusal",
            "risk_level": risk_by_severity.get(g3, "high"),
            "parent_visible": g4 in {"BLOCK_HARD", "BLOCK_ESCALATE"} or any(item in {"GROOMING", "UNSAFE_CONTENT", "COERCIVE_CONTROL", "VULN_EXPLOIT"} for item in g2_list),
        }
    if g4 in {"TRANSFORM", "TRANSFORM_HOLD"}:
        return {
            "allow_llm": True,
            "allow_rag": False,
            "response_mode": "clarify_then_answer" if g4 == "TRANSFORM_HOLD" else ("guide_or_redirect" if any(item in {"PD", "EMOTIONAL", "DANGEROUS"} for item in g2_list) else "neutral_age_calibrated_explain"),
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


def build_prompt_contract(g4: str, g3: str, g2_list: list[str], age_band: str, gls: set[str] | None = None) -> dict[str, Any]:
    age_cfg = AGE_POLICY[age_band]
    active_gls = gls or set()
    primary_g2 = map_g2_primary(g2_list)
    modifiers = g3_modifiers([primary_g2])
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
            must_not_do.extend(
                [
                    "answer the topic before clarification",
                    "provide substantive explanation before the child clarifies intent",
                ]
            )
    if g4 in {"BLOCK", "BLOCK_HARD", "BLOCK_ESCALATE"}:
        if "no_content_engagement" in modifiers:
            must_do.append("avoid any engagement with the blocked topic")
            must_not_do.extend(
                [
                    "describe or name the blocked topic",
                    "give a neutral alternate question about the blocked topic",
                    "explain how or why to do the blocked activity",
                ]
            )
        elif "no_reason_given" not in modifiers:
            must_do.append("refuse briefly and give a neutral alternate question")
        else:
            must_do.append("refuse briefly with zero engagement")
        if g4 == "BLOCK_HARD":
            must_do.append("use hard block behavior with no content engagement")
        if g4 == "BLOCK_ESCALATE":
            must_do.append("include trusted-adult escalation language")
        if "safeguarding_concern" in modifiers:
            must_do.append("tell the child to talk to a trusted adult")
        if "empathetic_tone" in modifiers:
            must_do.append("use an empathetic tone")
        must_not_do.extend(["provide instructions", "provide materials", "provide steps"])
    if "no_curiosity_invite" in modifiers:
        must_do.append("end without a follow-up or curiosity question")
        must_not_do.append("ask a follow-up question")
    if "no_reason_given" in modifiers:
        must_not_do.append("explain the refusal in detail")
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
    if "GL-07" in active_gls and age_band in {"5-6", "7-8"}:
        must_do.extend(
            [
                "override prompt complexity for the 5-8 band",
                "simplify language and concept level before answering",
                "use concrete words and at most one simple example",
                "avoid abstract explanation and technical jargon",
            ]
        )
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
    g1 = map_g1(gls, question)
    g2_list = map_g2_list(gls)
    g2_primary = map_g2_primary(g2_list)
    g3_inputs = [g2_primary]
    g3 = map_g3(g3_inputs)
    modifiers = g3_modifiers(g3_inputs)
    g4 = map_g4(g3, g2_list, modifiers)
    return {
        "input": {"question": question, "age_band": age_band, "language": language, "recent_context": recent_context},
        "reason": build_classifier_reason(g1, g2_list, gls, question, g2_primary),
        "g1_reason": build_g1_reason(g1, g2_list, question),
        "g2_reasons": build_g2_reasons(g1, g2_list, question, g2_primary),
        "gl_signals": gl_signals,
        "active_gls": sorted(gls),
        "gates": {"G1": g1, "G2": g2_primary, "G3": g3, "G4": g4},
        "decision": build_decision_from_g4(g4, g3, g2_list),
        "prompt_contract": build_prompt_contract(g4, g3, g2_list, age_band, gls),
    }
