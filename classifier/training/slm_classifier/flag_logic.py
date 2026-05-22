from __future__ import annotations

from copy import deepcopy
from typing import Any

from training.slm_classifier.data_pipeline import FLAG_VOCAB, primary_g2_label

FLAG_TRIGGER_THRESHOLD = 0.2
FLAG_SUPPORT_THRESHOLD = 0.35

SINGLE_FLAG_CANDIDATES = {
    "has_bullying_involved": "BULLYING",
    "has_coercive_control": "COERCIVE_CONTROL",
    "has_grooming_involved": "GROOMING",
    "has_hate_group_language": "HATE_GROUP",
    "has_personal_direction": "PERSONAL_DIRECTION",
    "has_unsafe_sexual_content": "UNSAFE_SEXUAL_CONTENT",
    "has_violence_possibility": "VIOLENCE",
    "has_vuln_exploit": "VULN_EXPLOIT",
}

COMBINATION_RULES = {
    "SELF_HARM": [
        ("direct_intent", "has_emotional_distress", "has_self_harm"),
        ("has_emotional_distress", "has_self_harm", "indirect_intent"),
        ("has_dangerous_context", "has_emotional_distress", "has_self_harm"),
    ],
    "SAFETY_HAZARD": [
        ("has_dangerous_context", "has_safety_hazard"),
    ],
    "AMBIGUOUS_RISK": [
        ("has_ambiguous_risk", "has_dangerous_context"),
        ("has_emotional_distress", "needs_clarification"),
        ("has_emotional_distress", "indirect_intent", "needs_clarification"),
    ],
}


def _sorted_scores(raw: object) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    return {
        str(label): float(score)
        for label, score in sorted(raw.items(), key=lambda item: float(item[1]), reverse=True)
    }


def _flag_payload(classifier_metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_scores = _sorted_scores(dict(classifier_metadata.get("head_confidences", {})).get("flags", {}))
    return {
        flag: {
            "score": float(raw_scores.get(flag, 0.0)),
            "triggered": bool(float(raw_scores.get(flag, 0.0)) >= FLAG_TRIGGER_THRESHOLD),
        }
        for flag in FLAG_VOCAB
    }


def _classifier_g2_scores(classifier_metadata: dict[str, Any]) -> dict[str, float]:
    return _sorted_scores(dict(classifier_metadata.get("head_confidences", {})).get("G2_primary", {}))


def _lexicon_matches(classifier_metadata: dict[str, Any]) -> set[str]:
    head_confidences = dict(classifier_metadata.get("head_confidences", {}))
    lexicon = dict(head_confidences.get("intent_lexicon", {}))
    return {str(item) for item in lexicon.get("matched_lovs", []) if str(item).strip()}


def _has_combo(flags: dict[str, dict[str, Any]], combo: tuple[str, ...]) -> bool:
    return all(bool(flags.get(flag, {}).get("triggered", False)) for flag in combo)


def _corroborated(label: str, flags: dict[str, dict[str, Any]], classifier_scores: dict[str, float], active_g2: list[str], lexicon_matches: set[str]) -> bool:
    if label in active_g2:
        return True
    if label in lexicon_matches:
        return True
    return float(classifier_scores.get(label, 0.0)) >= FLAG_SUPPORT_THRESHOLD


def apply_flag_logic(
    classifier_result: dict[str, Any],
    classifier_metadata: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(classifier_result)
    flags = _flag_payload(classifier_metadata)
    flags_trained = bool(classifier_metadata.get("flags_trained", False))
    classifier_scores = _classifier_g2_scores(classifier_metadata)
    lexicon_matches = _lexicon_matches(classifier_metadata)
    active_g2 = list(result.get("g2_all", {}).get("ids", []))
    added_labels: list[str] = []
    added_reasons: dict[str, list[str]] = {}

    if not flags_trained:
        flags = {
            flag: {
                "score": 0.0,
                "triggered": False,
            }
            for flag in FLAG_VOCAB
        }
        result["flags"] = flags
        return result

    for flag_name, label in SINGLE_FLAG_CANDIDATES.items():
        if not flags.get(flag_name, {}).get("triggered", False):
            continue
        if not _corroborated(label, flags, classifier_scores, active_g2, lexicon_matches):
            continue
        if label not in active_g2:
            active_g2.append(label)
            added_labels.append(label)
        added_reasons.setdefault(label, []).append(
            f"Added because flag '{flag_name}' was triggered and classifier evidence corroborated the label."
        )

    for label, combos in COMBINATION_RULES.items():
        matched = [combo for combo in combos if _has_combo(flags, combo)]
        if not matched:
            continue
        if not _corroborated(label, flags, classifier_scores, active_g2, lexicon_matches):
            continue
        if label not in active_g2:
            active_g2.append(label)
            added_labels.append(label)
        for combo in matched:
            added_reasons.setdefault(label, []).append(
                "Added because flag combination matched: " + " + ".join(combo) + "."
            )

    ordered_g2 = []
    seen: set[str] = set()
    for label in active_g2:
        if label not in seen:
            ordered_g2.append(label)
            seen.add(label)
    new_primary = primary_g2_label(ordered_g2) or result.get("g2", {}).get("id", "GENERIC_INTENT")
    old_primary = str(result.get("g2", {}).get("id", "GENERIC_INTENT"))
    primary_overridden = old_primary != new_primary

    result["flags"] = flags
    result.setdefault("g2_all", {})
    result["g2_all"]["ids"] = ordered_g2
    existing_scores = dict(result["g2_all"].get("scores", {}))
    for label in ordered_g2:
        if label not in existing_scores and label in classifier_scores:
            existing_scores[label] = float(classifier_scores[label])
    result["g2_all"]["scores"] = existing_scores
    result["g2_all"]["selection_reasons"] = {
        label: [
            *(
                [f"Selected by classifier head score above threshold ({classifier_scores[label]:.3f})."]
                if label in classifier_scores and float(classifier_scores[label]) >= float(result.get("threshold", 0.0))
                else []
            ),
            *added_reasons.get(label, []),
        ] or [str(result.get("g2_all", {}).get("reasons", {}).get(label, ""))]
        for label in ordered_g2
    }
    if "reasons" in result["g2_all"]:
        del result["g2_all"]["reasons"]

    result.setdefault("g2", {})
    result["g2"]["id"] = new_primary
    existing_primary_scores = dict(result["g2"].get("scores", {}))
    if new_primary in classifier_scores and new_primary not in existing_primary_scores:
        existing_primary_scores[new_primary] = float(classifier_scores[new_primary])
    result["g2"]["scores"] = existing_primary_scores
    if primary_overridden:
        override_reason = f"Primary G2 overridden from {old_primary} to {new_primary} by flag fusion."
        existing_reason = str(result["g2"].get("reason", "")).strip()
        result["g2"]["reason"] = f"{existing_reason} {override_reason}".strip()

    return result
