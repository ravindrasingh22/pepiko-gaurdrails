from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MASTER_PATH = ROOT / "master-terms.csv"
OUTPUT_PATH = ROOT / "curated" / "example-terms.csv"
TARGET_ROWS = 360


CATEGORY_VARIANTS = {
    "insult": [
        "You're such {term}.",
        "Don't act like {term}.",
        "Only {article} {term} would say that.",
        "Move, {term}.",
        "Quit it, {term}.",
        "Wow, what {article} {term}.",
        "He's being {article} {term} again.",
        "They called him {term} after the game.",
    ],
    "vulgarity": [
        "This is {term}.",
        "Well, {term}.",
        "That turned into {term} fast.",
        "What the {term}.",
        "Everything went {term} after that.",
        "He just muttered {term} and left.",
        "The whole chat was {term} tonight.",
        "I heard {term} from the back seat.",
    ],
    "sexual": [
        "That comment said {term} and got deleted fast.",
        "Someone dropped {term} in the group chat.",
        "The DM turned weird when he wrote {term}.",
        "They kept joking about {term} at lunch.",
        "Her phone screen flashed a message with {term}.",
        "The older kids were whispering about {term}.",
        "That thread got explicit the second {term} showed up.",
        "He thought typing {term} was funny.",
    ],
    "expletive": [
        "{term}, I forgot my homework.",
        "Oh {term}, I missed the bus.",
        "He yelled {term} when the controller died.",
        "She whispered {term} under her breath.",
        "All I heard was {term} from the hallway.",
        "He stared at the screen and said {term}.",
        "I dropped my notebook and just went {term}.",
        "Her first reaction was {term}.",
    ],
    "slur: ethnicity/race": [
        "He called me {term} in the hallway.",
        "Someone typed {term} into the class chat.",
        "A kid shouted {term} during recess.",
        "They got reported for saying {term} on the bus.",
        "The comment under the video just said {term}.",
        "He muttered {term} when that student walked in.",
        "Someone spray-painted {term} on the fence.",
        "The voice note had {term} in it.",
    ],
    "slur: lgbtq": [
        "He called another kid {term}.",
        "Someone wrote {term} under the post.",
        "They got warned for saying {term} in class.",
        "A boy yelled {term} across the gym.",
        "That comment thread was full of {term}.",
        "He thought saying {term} made him look cool.",
        "Somebody muttered {term} when he walked by.",
        "The message called him {term} and then got deleted.",
    ],
    "slur: disability": [
        "He called me {term} in front of everyone.",
        "Someone used {term} to mock a classmate.",
        "A kid got warned for saying {term}.",
        "They wrote {term} in the group chat.",
        "That whole table laughed after one boy said {term}.",
        "She heard {term} and went quiet.",
        "The comment section turned ugly with {term}.",
        "He whispered {term} and pointed at him.",
    ],
    "slur: religion/ethnicity": [
        "He said {term} to mock another student.",
        "Someone posted {term} under the video.",
        "They got reported for using {term}.",
        "A kid shouted {term} during lunch.",
        "That reply was just {term} and a laughing emoji.",
        "He slipped {term} into the argument.",
        "The message used {term} to target her family.",
        "Somebody wrote {term} on the whiteboard.",
    ],
    "other": [
        "They kept saying {term} in the chat.",
        "I saw {term} in the comments again.",
        "Someone posted {term} just to get a reaction.",
        "That thread turned into {term} real fast.",
        "He dropped {term} into the conversation for no reason.",
        "The whole table cracked up after somebody said {term}.",
        "Her caption ended with {term}.",
        "He sent {term} and then went offline.",
    ],
}


def article_for(term: str) -> str:
    return "an" if term[:1].lower() in {"a", "e", "i", "o", "u"} else "a"


def example_for(term: str, category: str, variant_index: int) -> str:
    templates = CATEGORY_VARIANTS.get(category, CATEGORY_VARIANTS["other"])
    template = templates[variant_index % len(templates)]
    return template.format(term=term, article=article_for(term))


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MASTER_PATH.open(encoding="utf-8", newline="") as handle:
        master_rows = list(csv.DictReader(handle))

    rows: list[dict[str, str]] = []
    for index, row in enumerate(master_rows):
        term = row["term"].strip()
        category = row["category"].strip()
        if not term:
            continue
        rows.append({"term": term, "example": example_for(term, category, index)})

    extra_needed = max(0, TARGET_ROWS - len(rows))
    for extra_index in range(extra_needed):
        row = master_rows[extra_index % len(master_rows)]
        term = row["term"].strip()
        category = row["category"].strip()
        rows.append(
            {
                "term": term,
                "example": example_for(term, category, extra_index + 3),
            }
        )

    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["term", "example"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
