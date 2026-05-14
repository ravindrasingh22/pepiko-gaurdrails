from typing import Any

from app.guardrails.gate_mapper import resolve_age_band


def normalize(context: dict[str, Any]) -> dict[str, Any]:
    raw_text = str(context["message"]).strip()
    child_profile = dict(context["child_profile"])
    age = int(child_profile.get("age", 10))
    requested_age_group = str(child_profile.get("age_group", "")).strip() or None
    resolved_age_band = resolve_age_band(age, requested_age_group)
    child_profile["age_group"] = resolved_age_band
    return {
        **context,
        "child_profile": child_profile,
        "raw_text": raw_text,
        "text": raw_text,
        "language_hint": str(context["child_profile"]["language"]).lower(),
        "resolved_age_band": resolved_age_band,
        "normalization_notes": [
            "resolved age band from numeric age",
        ],
    }
