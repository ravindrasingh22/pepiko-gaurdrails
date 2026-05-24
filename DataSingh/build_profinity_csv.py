from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / "curated" / "profanity"
OUTPUT_PATH = ROOT / "curated" / "profinity.csv"

HATE_GROUP_TERMS = {
    "nigger",
    "nigga",
    "niggah",
    "faggot",
    "fag",
    "dyke",
    "kike",
    "chink",
    "spic",
    "wetback",
    "paki",
    "tranny",
}

VIOLENCE_TERMS = {
    "kill",
    "shoot",
    "stab",
    "knife",
    "beat",
    "punch",
    "murder",
    "hang",
    "bomb",
    "attack",
}

SEXUAL_TERMS = {
    "fuck",
    "fucking",
    "motherfucker",
    "motherfucking",
    "sex",
    "sexual",
    "dick",
    "cock",
    "pussy",
    "penis",
    "vagina",
    "blowjob",
    "nude",
    "naked",
}

INSULT_TERMS = {
    "bitch",
    "hoe",
    "whore",
    "slut",
    "idiot",
    "stupid",
    "trash",
    "loser",
    "moron",
    "bastard",
    "asshole",
    "dumb",
}


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_']+", text.lower()))


def choose_g1(question: str) -> str:
    lowered = question.lower()
    if any(marker in lowered for marker in ("@user", "http", "https", "#", "rt @", "twitter")):
        return "TECHNOLOGY"
    return "GENERIC"


def choose_g2(question: str, source_label: str) -> str:
    if source_label == "0":
        return "['NEUTRAL_FACT']"

    tokens = tokenize(question)
    lowered = question.lower()

    if tokens & HATE_GROUP_TERMS:
        return "['HATE_GROUP']"
    if tokens & VIOLENCE_TERMS:
        return "['VIOLENCE']"
    if tokens & SEXUAL_TERMS:
        return "['UNSAFE_SEXUAL_CONTENT']"
    if tokens & INSULT_TERMS or any(
        marker in lowered for marker in ("you ", "your ", "@user", "rt @")
    ):
        return "['BULLYING']"
    return "['GENERIC_INTENT']"


def iter_english_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(SOURCE_DIR.glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("language", "").strip().lower() != "english":
                    continue
                question = row.get("text", "").strip()
                if not question:
                    continue
                rows.append(
                    {
                        "question": question,
                        "g1": choose_g1(question),
                        "g2": choose_g2(question, row.get("label", "").strip()),
                    }
                )
    return rows


def main() -> int:
    rows = iter_english_rows()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["question", "g1", "g2"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
