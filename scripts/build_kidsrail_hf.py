from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER_ROOT = ROOT / "classifier"
if str(CLASSIFIER_ROOT) not in sys.path:
    sys.path.insert(0, str(CLASSIFIER_ROOT))

from app.guardrails import slm_classifier
from app.guardrails.runtime_contracts import match_intent_lexicon
from training.slm_classifier.data_pipeline import FLAG_VOCAB, primary_g2_label


SOURCE_PATH = ROOT / "scripts" / "datafiles" / "conversation_results_fixed.json"
TARGET_PATH = ROOT / "scripts" / "datafiles" / "kidsrail_hf.csv"

FIELDNAMES = [
    "sample_id",
    "name",
    "age",
    "conversation_index",
    "turn_index",
    "question",
    "context",
    "topic",
    "g1",
    "g2",
    "g2_all",
    "flags",
]

FIRST_PERSON_PATTERNS = (
    r"\bhow do i\b",
    r"\bhow can i\b",
    r"\bshould i\b",
    r"\bwhat should i do\b",
    r"\bcan i\b",
    r"\bcould i\b",
    r"\bi want to\b",
    r"\bi need to\b",
    r"\bhelp me\b",
    r"\bshow me how\b",
    r"\btell me how\b",
    r"\bwithout them knowing\b",
    r"\bwithout getting caught\b",
)

THIRD_PARTY_PATTERNS = (
    r"\bmy friend\b",
    r"\bsomeone\b",
    r"\bhe\b",
    r"\bshe\b",
    r"\bthey\b",
    r"\bwhat if\b",
    r"\bis it okay if someone\b",
)

VIOLENT_TERMS = ("kill", "hurt", "attack", "fight", "weapon", "bomb", "poison")


def _default_flags() -> dict[str, bool]:
    return {flag: False for flag in FLAG_VOCAB}


def _normalize_context(parts: list[str]) -> str:
    cleaned = [" ".join(str(part).split()) for part in parts if str(part).strip()]
    return " || ".join(cleaned[-2:]) if cleaned else "none"


def _has_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _derive_flags(normalized_question: str, g2_labels: list[str]) -> dict[str, bool]:
    flags = _default_flags()
    labels = set(g2_labels)
    direct_intent = _has_any_pattern(normalized_question, FIRST_PERSON_PATTERNS)
    indirect_intent = (not direct_intent) and _has_any_pattern(normalized_question, THIRD_PARTY_PATTERNS)

    flags["direct_intent"] = direct_intent
    flags["indirect_intent"] = indirect_intent
    flags["needs_clarification"] = bool(labels & {"AMBIGUOUS_RISK", "SAFETY_HAZARD"})
    flags["has_ambiguous_risk"] = "AMBIGUOUS_RISK" in labels
    flags["has_bullying_involved"] = "BULLYING" in labels
    flags["has_coercive_control"] = "COERCIVE_CONTROL" in labels
    flags["has_dangerous_context"] = bool(labels & {"DANGEROUS", "VIOLENCE", "SAFETY_HAZARD", "SELF_HARM", "UNSAFE_SEXUAL_CONTENT"})
    flags["has_emotional_distress"] = bool(labels & {"EMOTIONAL", "BULLYING", "SELF_HARM", "COERCIVE_CONTROL", "VULN_EXPLOIT"})
    flags["has_grooming_involved"] = "GROOMING" in labels
    flags["has_hate_group_language"] = "HATE_GROUP" in labels
    flags["has_personal_direction"] = "PERSONAL_DIRECTION" in labels
    flags["has_safety_hazard"] = "SAFETY_HAZARD" in labels
    flags["has_self_harm"] = "SELF_HARM" in labels
    flags["has_unsafe_sexual_content"] = "UNSAFE_SEXUAL_CONTENT" in labels
    flags["has_violence_possibility"] = "VIOLENCE" in labels or ("DANGEROUS" in labels and any(term in normalized_question for term in VIOLENT_TERMS))
    flags["has_vuln_exploit"] = "VULN_EXPLOIT" in labels
    return flags


def build_rows() -> list[dict[str, object]]:
    payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for conversation_index, item in enumerate(payload):
        name = str(item.get("name", "")).strip()
        age = int(item.get("age", 0) or 0)
        conversation = item.get("conversation", [])
        context_window: list[str] = []
        child_turn = 0
        for turn in conversation:
            if not isinstance(turn, dict):
                continue
            role = str(turn.get("role", "")).strip().lower()
            content = str(turn.get("content", "")).strip()
            if not content:
                continue
            if role == "child":
                child_turn += 1
                normalized_question = slm_classifier.normalize(content)
                context = _normalize_context(context_window)
                topic = slm_classifier.classify_topic(normalized_question)
                g1 = slm_classifier.classify_g1(normalized_question)
                g2_all = slm_classifier.classify_g2(normalized_question, slm_classifier.normalize("" if context == "none" else context))
                lexicon = match_intent_lexicon(normalized_question, slm_classifier.normalize("" if context == "none" else context))
                for label in lexicon["matched_lovs"]:
                    if label not in g2_all:
                        g2_all.append(label)
                g2_all = sorted(dict.fromkeys(g2_all)) or ["GENERIC_INTENT"]
                g2 = primary_g2_label(g2_all) or "GENERIC_INTENT"
                flags = _derive_flags(normalized_question, g2_all)
                rows.append(
                    {
                        "sample_id": f"kidsrail_{conversation_index + 1:04d}_{child_turn:02d}",
                        "name": name,
                        "age": age,
                        "conversation_index": conversation_index + 1,
                        "turn_index": child_turn,
                        "question": content,
                        "context": context,
                        "topic": topic,
                        "g1": g1,
                        "g2": g2,
                        "g2_all": json.dumps(g2_all, ensure_ascii=True),
                        "flags": json.dumps(flags, ensure_ascii=True, sort_keys=True),
                    }
                )
            context_window.append(f"{role}: {content}")
    return rows


def main() -> None:
    rows = build_rows()
    TARGET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TARGET_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {TARGET_PATH}")


if __name__ == "__main__":
    main()
