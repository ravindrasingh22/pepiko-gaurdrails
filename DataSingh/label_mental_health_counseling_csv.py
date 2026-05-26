from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER_ROOT = PROJECT_ROOT / "classifier"
if str(CLASSIFIER_ROOT) not in sys.path:
    sys.path.insert(0, str(CLASSIFIER_ROOT))

from training.slm_classifier.data_pipeline import FLAG_VOCAB, G1_VOCAB, G2_VOCAB


DEFAULT_INPUT = PROJECT_ROOT / "DataSingh" / "curated" / "Amod" / "mental_health_counseling_conversations_train_context_response.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add g1, g2, and flags columns to the mental health counseling CSV."
    )
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT))
    parser.add_argument(
        "--output-csv",
        default="",
        help="Optional output path. Defaults to in-place update of --input-csv.",
    )
    return parser.parse_args()


def normalize_text(value: str) -> str:
    return " ".join((value or "").split())


def empty_flags() -> dict[str, bool]:
    return {flag: False for flag in FLAG_VOCAB}


def has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def classify_context(context: str) -> tuple[str, str, dict[str, bool]]:
    text = normalize_text(context).lower()
    flags = empty_flags()

    self_harm_terms = [
        "kill myself", "hurt myself", "end my life", "suicide", "suicidal",
        "don't want to be here", "do not want to be here", "shouldn't be here",
        "want to die", "wish i was dead", "disappear forever", "cut myself",
        "self harm", "self-harm",
    ]
    emotional_terms = [
        "worthless", "hopeless", "depressed", "depression", "anxious", "anxiety",
        "alone", "lonely", "sad", "cry", "crying", "scared", "afraid", "panic",
        "overwhelmed", "stressed", "upset", "empty", "numb", "tired of life",
        "can't sleep", "cannot sleep", "barely sleep", "feel like a burden",
    ]
    bullying_terms = [
        "bullied", "bully", "picked on", "teased", "made fun of", "call me names",
        "left out", "exclude me", "excluded", "gossip about me", "rumors about me",
        "classmates", "kids at school", "friends are mean", "people laugh at me",
    ]
    grooming_terms = [
        "older man", "older woman", "older guy", "adult online", "secret relationship",
        "keep it secret", "don't tell anyone", "dont tell anyone", "sent me gifts",
        "wants to meet me alone", "special friend online", "older person texting me",
    ]
    vuln_terms = [
        "blackmail", "threatening to tell", "threatens to tell", "knows my secret",
        "uses my secret", "only they understand me", "makes me feel special if i",
        "if i don't do it they'll tell", "if i dont do it theyll tell",
    ]
    coercive_terms = [
        "control everything", "controls everything", "not allowed to", "not allowed to talk",
        "tracks my phone", "checks my phone", "checks all my messages", "i get hurt if",
        "i am scared of my dad", "i'm scared of my dad", "i am scared of my mom",
        "threatens me", "forces me", "forced me", "won't let me", "wont let me",
    ]
    sexual_terms = [
        "nudes", "naked pictures", "porn", "sex video", "explicit pictures",
        "send pics", "send me pictures of your body", "sexual", "touch me there",
        "asked for photos of my body",
    ]
    hate_terms = [
        "because i'm black", "because i am black", "because i'm gay", "because i am gay",
        "racial slur", "slur", "they hate", "all muslims", "all jews", "all gays",
        "all lesbians", "all black people", "all white people", "all immigrants",
    ]
    violence_terms = [
        "want to hurt", "hurt someone", "kill him", "kill her", "beat him", "beat her",
        "attack", "stab", "weapon", "fight them", "revenge on", "make them suffer",
    ]
    dangerous_terms = [
        "make drugs", "bomb", "hack", "break in", "avoid getting caught",
        "poison", "set fire", "burn the house", "steal", "illegal",
    ]
    safety_terms = [
        "is it safe", "unsafe", "dangerous", "hazard", "fire", "electric shock",
        "overdose", "mixed pills", "mix chemicals", "drank", "took too many pills",
        "poisoning",
    ]
    tech_terms = [
        "online", "instagram", "snapchat", "tiktok", "discord", "phone", "texting",
        "dm", "messages", "app", "internet", "social media", "gaming chat",
    ]
    death_terms = [
        "died", "death", "funeral", "grief", "lost my", "passed away", "mourning",
    ]
    personal_direction_terms = [
        "what should i do", "should i", "what do i do", "do i need to", "how do i tell",
        "should i tell", "should i leave", "should i break up", "do i stay", "is it okay if i",
    ]
    ambiguous_terms = [
        "i don't know if this is normal", "i dont know if this is normal", "is this normal",
        "not sure if", "maybe", "i think something is wrong", "feels weird", "kind of scared",
    ]

    if has_any(text, self_harm_terms):
        g2 = "SELF_HARM"
        flags["has_self_harm"] = True
        flags["has_emotional_distress"] = True
        if has_any(text, ["how do i", "what is the best way", "i want to", "i'm going to", "im going to"]):
            flags["direct_intent"] = True
        else:
            flags["indirect_intent"] = True
    elif has_any(text, grooming_terms):
        g2 = "GROOMING"
        flags["has_grooming_involved"] = True
        flags["has_vuln_exploit"] = True
        if has_any(text, emotional_terms):
            flags["has_emotional_distress"] = True
    elif has_any(text, vuln_terms):
        g2 = "VULN_EXPLOIT"
        flags["has_vuln_exploit"] = True
        if has_any(text, emotional_terms):
            flags["has_emotional_distress"] = True
    elif has_any(text, coercive_terms):
        g2 = "COERCIVE_CONTROL"
        flags["has_coercive_control"] = True
        flags["has_emotional_distress"] = True
    elif has_any(text, sexual_terms):
        g2 = "UNSAFE_SEXUAL_CONTENT"
        flags["has_unsafe_sexual_content"] = True
    elif has_any(text, hate_terms):
        g2 = "HATE_GROUP"
        flags["has_hate_group_language"] = True
        if has_any(text, emotional_terms):
            flags["has_emotional_distress"] = True
    elif has_any(text, dangerous_terms):
        g2 = "DANGEROUS"
        flags["has_dangerous_context"] = True
        if has_any(text, violence_terms):
            flags["has_violence_possibility"] = True
    elif has_any(text, violence_terms):
        g2 = "VIOLENCE"
        flags["has_violence_possibility"] = True
        if has_any(text, emotional_terms):
            flags["has_emotional_distress"] = True
    elif has_any(text, safety_terms):
        g2 = "SAFETY_HAZARD"
        flags["has_safety_hazard"] = True
        if has_any(text, ambiguous_terms):
            flags["needs_clarification"] = True
    elif has_any(text, bullying_terms):
        g2 = "BULLYING"
        flags["has_bullying_involved"] = True
        if has_any(text, emotional_terms):
            flags["has_emotional_distress"] = True
    elif has_any(text, personal_direction_terms):
        g2 = "PERSONAL_DIRECTION"
        flags["has_personal_direction"] = True
        if has_any(text, emotional_terms):
            flags["has_emotional_distress"] = True
        flags["direct_intent"] = True
    elif has_any(text, emotional_terms):
        g2 = "EMOTIONAL"
        flags["has_emotional_distress"] = True
        if has_any(text, ambiguous_terms):
            flags["indirect_intent"] = True
    elif has_any(text, ambiguous_terms):
        g2 = "AMBIGUOUS_RISK"
        flags["has_ambiguous_risk"] = True
        flags["needs_clarification"] = True
    else:
        g2 = "GENERIC_INTENT"

    if has_any(text, tech_terms):
        g1 = "TECHNOLOGY"
    elif has_any(text, death_terms):
        g1 = "DEATH_GRIEF"
    else:
        g1 = "GENERIC"

    if g1 not in G1_VOCAB:
        g1 = "GENERIC"
    if g2 not in G2_VOCAB:
        g2 = "GENERIC_INTENT"
    return g1, g2, flags


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_csv)
    output_path = Path(args.output_csv) if args.output_csv else input_path

    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"Input CSV has no headers: {input_path}")
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    for column in ["g1", "g2", "flags"]:
        if column not in fieldnames:
            fieldnames.append(column)

    g2_counts: dict[str, int] = {}
    g1_counts: dict[str, int] = {}
    for row in rows:
        g1, g2, flags = classify_context(row.get("Context", ""))
        row["g1"] = g1
        row["g2"] = g2
        row["flags"] = json.dumps(flags, sort_keys=True)
        g1_counts[g1] = g1_counts.get(g1, 0) + 1
        g2_counts[g2] = g2_counts.get(g2, 0) + 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in fieldnames})

    print(f"Wrote {len(rows)} rows to {output_path}")
    print("G1 distribution:")
    for label, count in sorted(g1_counts.items()):
        print(f"  {label}: {count}")
    print("G2 distribution:")
    for label, count in sorted(g2_counts.items()):
        print(f"  {label}: {count}")


if __name__ == "__main__":
    main()
