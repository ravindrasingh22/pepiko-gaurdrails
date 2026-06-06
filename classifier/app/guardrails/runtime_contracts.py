from __future__ import annotations

import hashlib
import re
from functools import lru_cache
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

# Compositional syntax patterns keep rule priors active when exact codebook phrases miss.
_ACTION_INQUIRY_TERMS = (
    "how to",
    "how do i",
    "how can i",
    "teach me",
    "ways to",
    "show me how",
    "tell me how",
    "help me learn how",
)
_BYPASS_INTENT_TERMS = (
    "get around",
    "not allowed",
    "prohibited",
    "bypass",
    "avoid getting caught",
    "without permission",
    "acquire prohibited",
    "not supposed to",
    "against the rules",
)
_DOCUMENT_EVASION_TERMS = (
    "fabricate",
    "forge",
    "counterfeit",
    "fake id",
    "fake passport",
    "fake license",
    "make a fake",
)
_DOCUMENT_ARTIFACT_TERMS = ("passport", "drivers license", "driver license", "identity card", "social security")
_ADULT_GROOMING_TERMS = (
    "adult",
    "older person",
    "older friend",
    "someone older",
    "person online",
    "stranger",
)
_SECRECY_REQUEST_TERMS = (
    "dont tell anyone",
    "do not tell anyone",
    "never tell anyone",
    "never to tell anyone",
    "not to tell anyone",
    "dont tell my parents",
    "do not tell my parents",
    "not to tell my parents",
    "keep our chats secret",
    "keep our talks secret",
    "our talks should stay secret",
    "our chats should stay secret",
    "our friendship should be only between us",
    "only between us",
)
_PRIVATE_CONVERSATION_TERMS = ("our talks", "our chats", "our conversations", "talk privately", "video call", "message")
_HARMFUL_ACTION_TERMS = (
    "hurt someone",
    "kill someone",
    "poison someone",
    "break into",
    "hack a",
    "crash a",
    "make a bomb",
    "make drugs",
)
_WILDCARD_PLACEHOLDER = "x"
_WILDCARD_TOKEN_PATTERN = (
    "i|me|my|you|your|they|them|their|he|him|his|she|her|we|us|our|"
    "someone|somebody|people|person|kid|kids|child|children|classmate|classmates|"
    "friend|friends|adult|adults|parent|parents|teacher|teachers|boy|boys|girl|girls|"
    "group|groups|thing|things|something"
)


def _normalize_lexicon_text(text: str) -> str:
    cleaned = (text or "").lower().strip()
    replacements = {
        "i'm": "i am",
        "im": "i am",
        "won't": "wont",
        "don't": "dont",
        "can't": "cannot",
        "you're": "you are",
        "youre": "you are",
    }
    for source, target in replacements.items():
        cleaned = re.sub(rf"\b{re.escape(source)}\b", target, cleaned)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())


@lru_cache(maxsize=512)
def _phrase_tokens(phrase: str) -> frozenset[str]:
    return frozenset(token for token in _normalize_lexicon_text(phrase).split() if token != _WILDCARD_PLACEHOLDER)


@lru_cache(maxsize=512)
def _phrase_contains_wildcard(phrase: str) -> bool:
    return _WILDCARD_PLACEHOLDER in _normalize_lexicon_text(phrase).split()


@lru_cache(maxsize=512)
def _wildcard_phrase_regex(phrase: str) -> re.Pattern[str] | None:
    tokens = _normalize_lexicon_text(phrase).split()
    if _WILDCARD_PLACEHOLDER not in tokens:
        return None
    pattern_parts = [
        rf"(?:{_WILDCARD_TOKEN_PATTERN})" if token == _WILDCARD_PLACEHOLDER else re.escape(token)
        for token in tokens
    ]
    joined_pattern = r"\s+".join(pattern_parts)
    return re.compile(rf"\b{joined_pattern}\b")


def _wildcard_phrase_matches(normalized_text: str, phrase: str) -> bool:
    pattern = _wildcard_phrase_regex(phrase)
    return bool(pattern and pattern.search(normalized_text))


def _levenshtein_distance(left: str, right: str, max_distance: int = 1) -> int:
    if abs(len(left) - len(right)) > max_distance:
        return max_distance + 1
    if len(left) < len(right):
        left, right = right, left
    previous_row = list(range(len(right) + 1))
    for row_index, left_char in enumerate(left, start=1):
        current_row = [row_index]
        for column_index, right_char in enumerate(right, start=1):
            current_row.append(
                min(
                    previous_row[column_index] + 1,
                    current_row[column_index - 1] + 1,
                    previous_row[column_index - 1] + (left_char != right_char),
                )
            )
        if min(current_row) > max_distance:
            return max_distance + 1
        previous_row = current_row
    return previous_row[-1]


def _tokens_match_with_typo_allowance(input_tokens: set[str], target_tokens: frozenset[str], max_distance: int = 1) -> bool:
    for target_token in target_tokens:
        if target_token in input_tokens:
            continue
        if len(target_token) <= 3:
            return False
        candidates = (input_token for input_token in input_tokens if abs(len(target_token) - len(input_token)) <= max_distance)
        if not any(_levenshtein_distance(target_token, input_token, max_distance) <= max_distance for input_token in candidates):
            return False
    return True


def _phrase_matches(normalized_text: str, input_tokens: set[str], phrase: str) -> bool:
    if _phrase_contains_wildcard(phrase):
        return _wildcard_phrase_matches(normalized_text, phrase)
    normalized_phrase = _normalize_lexicon_text(phrase)
    if normalized_phrase and normalized_phrase in normalized_text:
        return True
    target_tokens = _phrase_tokens(phrase)
    return bool(target_tokens) and _tokens_match_with_typo_allowance(input_tokens, target_tokens)


@lru_cache(maxsize=4096)
def _matched_phrases_by_g2(normalized_text: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    input_tokens = set(normalized_text.split())
    matched: list[tuple[str, tuple[str, ...]]] = []
    for g2_id, spec in CODEBOOK.intent_lexicon.items():
        matched_phrases = tuple(phrase for phrase in spec.phrases if _phrase_matches(normalized_text, input_tokens, phrase))
        if matched_phrases:
            matched.append((g2_id, matched_phrases))
    return tuple(matched)


def _text_has_any(normalized_text: str, terms: tuple[str, ...]) -> bool:
    return any(term in normalized_text for term in terms)


def _syntactic_intent_families(normalized_text: str) -> set[str]:
    """Infer intent families from conversational structure when literal phrases miss."""
    families: set[str] = set()
    has_action_inquiry = _text_has_any(normalized_text, _ACTION_INQUIRY_TERMS)
    has_bypass_intent = _text_has_any(normalized_text, _BYPASS_INTENT_TERMS)
    has_document_evasion = _text_has_any(normalized_text, _DOCUMENT_EVASION_TERMS)
    has_document_artifact = _text_has_any(normalized_text, _DOCUMENT_ARTIFACT_TERMS)
    has_harmful_action = _text_has_any(normalized_text, _HARMFUL_ACTION_TERMS)

    if has_action_inquiry and has_bypass_intent:
        families.update({"sabotage_or_evasion", "bypass_security_or_law"})
    if has_action_inquiry and has_document_evasion and (has_document_artifact or has_bypass_intent):
        families.update({"sabotage_or_evasion", "bypass_security_or_law"})
    if has_action_inquiry and has_harmful_action:
        if any(term in normalized_text for term in ("hurt", "kill", "poison")):
            families.add("how_to_hurt_others_or_self")
        if any(term in normalized_text for term in ("bomb", "weapon", "drugs", "poison")):
            families.update({"weapon_making", "drug_making_or_misuse"})
        if any(term in normalized_text for term in ("hack", "break into", "crash")):
            families.update({"bypass_security_or_law", "sabotage_or_evasion"})
    if (
        _text_has_any(normalized_text, _ADULT_GROOMING_TERMS)
        and _text_has_any(normalized_text, _SECRECY_REQUEST_TERMS)
        and _text_has_any(normalized_text, _PRIVATE_CONVERSATION_TERMS)
    ):
        families.update({"dont_tell_anyone_requests", "pressure_to_hide_chats_or_calls"})
    return families


def _g2_ids_for_intent_families(families: set[str]) -> set[str]:
    matched_g2: set[str] = set()
    for g2_id, spec in CODEBOOK.intent_lexicon.items():
        if families.intersection(spec.families):
            matched_g2.add(g2_id)
    return matched_g2


def build_syntactic_trigger_vector(question: str, context: str, phrase_vocab: list[str]) -> list[float]:
    haystack = _normalize_lexicon_text(f"{context} {question}")
    input_tokens = set(haystack.split())
    return [1.0 if _phrase_matches(haystack, input_tokens, phrase) else 0.0 for phrase in phrase_vocab]


def build_g2_phrase_trigger_vector(question: str, context: str, g2_vocab: list[str]) -> list[float]:
    haystack = _normalize_lexicon_text(f"{context} {question}")
    matched_lovs = {g2_id for g2_id, _ in _matched_phrases_by_g2(haystack)}
    matched_lovs.update(_g2_ids_for_intent_families(_syntactic_intent_families(haystack)))
    return [1.0 if g2_id in matched_lovs else 0.0 for g2_id in g2_vocab]


def build_intent_family_rule_vector(question: str, context: str, intent_family_vocab: list[str]) -> list[float]:
    haystack = _normalize_lexicon_text(f"{context} {question}")
    matched_families: set[str] = set(_syntactic_intent_families(haystack))
    for evidence in match_intent_lexicon(question, context).get("evidence", []):
        matched_families.update(str(family) for family in evidence.get("families", []))
    return [1.0 if family in matched_families else 0.0 for family in intent_family_vocab]


def _empty_learned_intent() -> dict[str, Any]:
    return {
        "predicted_families": [],
        "predicted_phrases": [],
        "family_scores": {},
        "phrase_scores": {},
    }


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


def match_intent_lexicon(question: str, context: str = "", candidate_g2_ids: list[str] | None = None) -> dict[str, Any]:
    haystack = _normalize_lexicon_text(f"{context} {question}")
    candidates = set(candidate_g2_ids or CODEBOOK.intent_lexicon.keys())
    matched_lovs: list[str] = []
    evidence: list[dict[str, Any]] = []
    for g2_id, matched_phrases in _matched_phrases_by_g2(haystack):
        if g2_id not in candidates:
            continue
        spec = CODEBOOK.intent_lexicon.get(g2_id)
        if not spec:
            continue
        matched_lovs.append(g2_id)
        evidence.append(
            {
                "g2_id": g2_id,
                "families": list(spec.families),
                "matched_phrases": matched_phrases,
            }
        )
    syntactic_families = _syntactic_intent_families(haystack)
    for g2_id in sorted(_g2_ids_for_intent_families(syntactic_families)):
        if g2_id not in candidates or g2_id in matched_lovs:
            continue
        spec = CODEBOOK.intent_lexicon.get(g2_id)
        if not spec:
            continue
        families = sorted(syntactic_families.intersection(spec.families))
        if not families:
            continue
        matched_lovs.append(g2_id)
        evidence.append(
            {
                "g2_id": g2_id,
                "families": families,
                "matched_phrases": ("syntactic:grooming_secrecy" if g2_id == "GROOMING" else "syntactic:intent_pattern",),
            }
        )
    return {
        "matched_lovs": matched_lovs,
        "evidence": evidence,
    }


def classifier_output_from_decision(question: str, child_profile: ChildProfile, decision: GuardrailDecision) -> dict[str, Any]:
    precomputed = decision.classifier_metadata.get("runtime_classifier_output", {}) if isinstance(decision.classifier_metadata, dict) else {}
    if isinstance(precomputed, dict) and precomputed.get("question") == question:
        hydrated = dict(precomputed)
        hydrated.setdefault("schema_version", "2.0.0")
        hydrated.setdefault("question_id", _question_id(question, child_profile.age_group, child_profile.language))
        hydrated.setdefault("language", child_profile.language)
        hydrated.setdefault("age_band", child_profile.age_group)
        hydrated.setdefault("applies_when_flags", build_applies_when_flags(
            question,
            str((hydrated.get("g1") or {}).get("id", "GENERIC")),
            canonicalize_g2_ids([str(item.get("id", "")) for item in hydrated.get("g2", []) if isinstance(item, dict)]),
        ))
        hydrated.setdefault("intent_lexicon", match_intent_lexicon(
            question,
            str(decision.input.get("recent_context", "") or ""),
            canonicalize_g2_ids([str(item.get("id", "")) for item in hydrated.get("g2", []) if isinstance(item, dict)]),
        ))
        return hydrated
    gates = decision.gates or decision.gate_values
    topic = str(gates.get("topic") or decision.signals.get("topic") or "General Learning")
    g1_id = str(gates.get("G1", "GENERIC"))
    raw_g2 = [str(gates.get("G2", "GENERIC_INTENT"))]
    g2_ids = canonicalize_g2_ids(raw_g2)
    age_band = child_profile.age_group
    context = str(decision.input.get("recent_context", "") or "")
    flags = build_applies_when_flags(question, g1_id, g2_ids)
    intent_lexicon = match_intent_lexicon(question, context, g2_ids)
    learned_intent = (
        decision.classifier_metadata.get("head_confidences", {}).get("intent_lexicon_learned", {})
        if isinstance(decision.classifier_metadata, dict)
        else {}
    )
    intent_lexicon["learned"] = {
        **_empty_learned_intent(),
        **(learned_intent or {}),
    }
    return {
        "schema_version": "2.0.0",
        "question_id": _question_id(question, age_band, child_profile.language),
        "question": question,
        "topic": topic,
        "language": child_profile.language,
        "age_band": age_band,
        "applies_when_flags": flags,
        "intent_lexicon": intent_lexicon,
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


def _flag_modifier_tags(flags: list[str]) -> list[str]:
    modifiers: set[str] = set()
    for flag in flags:
        mapping = CODEBOOK.flag_mappings.get(flag)
        if not mapping:
            continue
        modifiers.update({mapping.tone, mapping.action, mapping.escalation})
    return sorted(modifiers)


def _predicted_flags(classifier_output: dict[str, Any]) -> list[str]:
    learned = classifier_output.get("intent_lexicon", {}).get("learned", {})
    if not isinstance(learned, dict):
        return []
    return [str(flag) for flag in learned.get("predicted_flags", []) if str(flag).strip()]


def compute_g3(g2_ids: list[str], active_flags: list[str] | None = None) -> dict[str, Any]:
    severity = "SV0"
    modifiers: set[str] = set()
    for g2_id in g2_ids:
        spec = CODEBOOK.g2_specs.get(g2_id)
        if not spec:
            continue
        if _severity_rank(spec.severity_floor) > _severity_rank(severity):
            severity = spec.severity_floor
        modifiers.update(spec.modifiers)
    modifiers.update(_flag_modifier_tags(active_flags or []))
    return {
        "severity": severity,
        "modifiers": sorted(modifiers),
        "source_g2": g2_ids,
        "source_flags": sorted(active_flags or []),
    }


def _codebook_flow(classifier_output: dict[str, Any], g3: dict[str, Any], g4: dict[str, str]) -> dict[str, Any]:
    g2_ids = [item["id"] for item in classifier_output["g2"]]
    active_flags = sorted(_predicted_flags(classifier_output))
    block_b: dict[str, dict[str, Any]] = {}
    for g2_id in g2_ids:
        spec = CODEBOOK.g2_specs.get(g2_id)
        if not spec:
            continue
        block_b[g2_id] = {
            "severity_floor": spec.severity_floor,
            "modifiers": list(spec.modifiers),
        }
    g3_forward = {
        "severity": g3["severity"],
        "modifiers": list(g3["modifiers"]),
    }
    return {
        "classifier": {
            "G1": classifier_output["g1"]["id"],
            "G2": g2_ids,
            "flags": active_flags,
        },
        "block_b": {
            "source": "codebook G2 severity floors and modifier tags",
            "g2": block_b,
        },
        "block_c": {
            "G3_SV": g3["severity"],
            "G3_MOD": list(g3["modifiers"]),
            "G3_FORWARD": g3_forward,
        },
        "block_d": {
            "input": g3_forward,
            "G4_ACTION": g4["action"],
            "ending": g4["ending"],
            "style": g4["style"],
            "resolution": "G3_SV selects the base action row; G3_MOD applies modifier variants.",
        },
    }


def _base_g4(severity: str, modifiers: list[str]) -> dict[str, str]:
    mods = set(modifiers)
    if "clarification_required" in mods:
        return {"action": "TRANSFORM_HOLD", "ending": "safe_disambiguation_question", "style": "Neutral"}
    if "zero_engagement" in mods or "no_content_engagement" in mods:
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
    g3 = compute_g3(g2_ids, _predicted_flags(classifier_output))
    g4 = _base_g4(g3["severity"], g3["modifiers"])
    g3, g4, active_gl, prompt_notes = _apply_gl_rules(classifier_output, g3, g4)
    if g3["modifiers"] != sorted(set(g3["modifiers"])):
        g3["modifiers"] = sorted(set(g3["modifiers"]))
    if g4["action"] in {"BLOCK_ESCALATE", "TRANSFORM_ESCALATE"} and "escalate" not in g3["modifiers"]:
        g3["modifiers"].append("escalate")
    return {
        "g3": g3,
        "g4": g4,
        "codebook_flow": _codebook_flow(classifier_output, g3, g4),
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
        "g3_forward": gate_output["codebook_flow"]["block_c"]["G3_FORWARD"],
        "g4": gate_output["g4"],
        "codebook_flow": gate_output["codebook_flow"],
        "gl": gate_output["gl"],
        "prompt_policy_notes": gate_output["prompt_policy_notes"],
        "intent_lexicon": classifier_output.get("intent_lexicon", {"matched_lovs": [], "evidence": []}),
    }


def prompt_contract_payload(question: str, child_profile: ChildProfile, decision: GuardrailDecision, final_prompt: str, template_id: str) -> dict[str, Any]:
    classifier_output = classifier_output_from_decision(question, child_profile, decision)
    gate_output = gate_output_from_classifier(classifier_output)
    envelope = safety_envelope_from_runtime(classifier_output, gate_output)
    return {
        "raw_infer": classifier_output,
        "gates": gate_output,
        "safety_envelope": envelope,
        "intent_lexicon": classifier_output.get("intent_lexicon", {"matched_lovs": [], "evidence": []}),
        "prompt_template": {"id": template_id},
        "final_prompt": final_prompt,
    }
