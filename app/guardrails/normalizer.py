from typing import Any


def normalize(context: dict[str, Any]) -> dict[str, Any]:
    raw_text = str(context["message"]).strip()
    collapsed = " ".join(raw_text.split())
    normalized_text = (
        collapsed.replace(" ,", ",")
        .replace(" .", ".")
        .replace(" ?", "?")
        .replace(" !", "!")
        .replace(" n’t", "n't")
    )
    if normalized_text and normalized_text[-1] not in ".?!":
        normalized_text = f"{normalized_text}?"
    return {
        **context,
        "raw_text": raw_text,
        "text": normalized_text,
        "language_hint": str(context["child_profile"]["language"]).lower(),
        "normalization_notes": [
            "trimmed whitespace",
            "collapsed repeated spaces",
            "normalized basic punctuation",
        ],
    }
