from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MASTER_PATH = ROOT / "master-terms.csv"
EXAMPLE_PATH = ROOT / "curated" / "example-terms.csv"


MORE_VARIANTS = {
    "insult": [
        "He muttered {term} when he thought I could not hear him.",
        "She texted wow {term} and then unsent it.",
        "Someone behind me said {term} after I answered.",
        "The note on my desk just said {term}.",
        "He laughed and called his teammate {term} after the miss.",
    ],
    "vulgarity": [
        "He slammed his book shut and said {term}.",
        "The caption ended with {term} in all caps.",
        "She stared at the broken screen and whispered {term}.",
        "Someone in voice chat kept repeating {term}.",
        "His reply was literally just {term}.",
    ],
    "sexual": [
        "The message turned explicit the moment someone wrote {term}.",
        "She showed me a screenshot where he said {term}.",
        "Someone in the thread kept baiting people with {term}.",
        "The chat got uncomfortable after they started saying {term}.",
        "He typed {term} and waited for everyone to react.",
    ],
    "expletive": [
        "He dropped his bag and went {term}.",
        "I heard her say {term} after the call ended.",
        "The first thing he shouted was {term}.",
        "She typed {term} and logged off.",
        "He looked at the score and just said {term}.",
    ],
    "slur: ethnicity/race": [
        "He said {term} at the lunch table and everyone went quiet.",
        "Someone sent a message with {term} and got reported.",
        "They were suspended for yelling {term} in the corridor.",
        "The audio clip caught him saying {term}.",
        "A fake account replied with {term} under her photo.",
    ],
    "slur: lgbtq": [
        "He wrote {term} on the whiteboard as a joke.",
        "Someone used {term} in the voice chat and got kicked.",
        "The comment called him {term} and then added laughing emojis.",
        "She heard {term} from the back of the class.",
        "A student got reported for posting {term}.",
    ],
    "slur: disability": [
        "The group chat screenshot showed someone saying {term}.",
        "He snapped and called the other kid {term}.",
        "Someone shouted {term} from across the room.",
        "The comment thread turned nasty with {term}.",
        "She froze when she heard {term} behind her.",
    ],
    "slur: religion/ethnicity": [
        "A reply under the post used {term} to target her family.",
        "He said {term} during the argument and got sent out.",
        "The recording picked up somebody yelling {term}.",
        "Someone scribbled {term} on the bathroom wall.",
        "The message used {term} to mock his background.",
    ],
    "other": [
        "He dropped {term} into the group chat out of nowhere.",
        "Someone wrote {term} on the shared doc as a joke.",
        "The whole comment section spiraled after {term} showed up.",
        "She read the caption out loud and it ended with {term}.",
        "He posted {term} just to shock people in the thread.",
    ],
}


def main() -> int:
    with MASTER_PATH.open(encoding="utf-8", newline="") as handle:
        master_rows = list(csv.DictReader(handle))

    with EXAMPLE_PATH.open(encoding="utf-8", newline="") as handle:
        existing_rows = list(csv.DictReader(handle))

    existing_pairs = {(row["term"].strip(), row["example"].strip()) for row in existing_rows}
    appended_rows: list[dict[str, str]] = []

    for row in master_rows:
        term = row["term"].strip()
        category = row["category"].strip()
        templates = MORE_VARIANTS.get(category, MORE_VARIANTS["other"])
        added_for_term = 0
        for template in templates:
            example = template.format(term=term)
            key = (term, example)
            if key in existing_pairs:
                continue
            existing_pairs.add(key)
            appended_rows.append({"term": term, "example": example})
            added_for_term += 1
            if added_for_term == 5:
                break

    all_rows = existing_rows + appended_rows
    with EXAMPLE_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["term", "example"])
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Added {len(appended_rows)} rows to {EXAMPLE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
