from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MASTER_PATH = ROOT / "master-terms.csv"
EXAMPLE_PATH = ROOT / "curated" / "example-terms.csv"


TARGET_TERMS = {
    "oh nah",
    "nah bro",
    "bro is wild",
    "bro thought",
    "bro really said",
    "say less",
    "real",
    "it is giving",
    "giving",
    "understood the assignment",
    "mewing",
    "mog",
    "mogged",
    "fanum tax",
    "goofy",
    "goofy ahh",
    "goofy ahh kid",
    "wildin",
    "wilding",
    "crash out",
    "crashing out",
    "corny",
    "cheugy",
    "cheug",
    "sassy",
    "zesty",
    "feral",
    "ick",
    "the ick",
    "hard launch",
    "soft block",
    "hard block",
    "unadd",
    "unfriend me then",
    "blocked and reported",
    "caught in 4k",
    "in 4k",
    "clock it",
    "clocked",
    "you thought you ate",
    "who asked",
    "be so serious",
    "bffr right now",
    "cry about it",
    "stay mad",
    "mad for what",
    "you wish",
    "rent free",
    "not the",
    "side eye",
    "bombastic side eye",
    "criminal offensive side eye",
    "period",
    "periodt",
    "as you should",
    "delusionship",
    "friendzoned",
    "down bad",
    "caught feelings",
    "main feed",
    "finsta",
    "spam account",
    "face reveal",
    "feet pics",
    "thirsty",
    "thirsting",
    "devious lick",
    "lick",
    "opp pack",
    "on sight",
    "run the fade",
    "catch these hands",
    "swing first",
    "snatched",
    "ate and left no crumbs",
    "serving",
    "serve",
    "girl math",
    "boy math",
    "girl dinner",
    "npc energy",
    "villain arc",
    "glazing",
    "meatriding",
    "meat riding",
    "cooked beyond repair",
    "deep fried",
    "fried",
    "bop",
    "ran through",
    "for the streets",
    "chat is this real",
    "chat am i cooked",
    "ts pmo",
    "ts",
    "pmo",
    "stfu",
    "gtfo",
    "oml",
    "omg",
    "frfr",
    "deadass",
    "type shi",
    "type shit",
    "big yikes",
    "yikes",
    "nah fam",
    "fr tho",
    "not gonna hold you",
    "ion know",
    "ion care",
    "tf",
    "wtv",
    "whatever bro",
    "doing too much",
    "extra",
    "pick a struggle",
    "youre cooked",
    "you are cooked",
    "low taper fade",
    "huzz",
    "unc status",
    "unc",
    "auntie behavior",
    "fed",
    "snitch",
    "ops",
    "clout",
    "clout chaser",
}


STYLE_BANK = {
    "insult": [
        'At the lunch table somebody went, "{term}? Yeah, that is exactly what he is."',
        'In the group chat one kid replied, "{term}, just log off already."',
        'The hallway argument ended with, "Be quiet, {term}."',
        'In the script-style exchange, one friend mutters, "{term}," and walks away.',
        'A caption under the video read, "Whole comment section acting {term} today."',
    ],
    "vulgarity": [
        'A kid looked at the broken project and said, "{term}, we have to start over."',
        'In the bus seat behind me, somebody whispered, "{term}, my phone died again."',
        'The group chat lit up with, "{term}, not right before the deadline."',
        'In a movie-scene kind of beat, he drops his bag and goes, "{term}."',
        'The caption just said, "{term}, this day is cursed."',
    ],
    "sexual": [
        'The DM got weird fast when someone typed, "{term}," and waited for a reply.',
        'At the back of the room they were giggling over a message that said, "{term}."',
        'The comment section got shut down after one account posted, "{term}."',
        'In a messy group chat, somebody said, "Why are they talking about {term} again?"',
        'The line in the script-style argument was, "You really just said {term} out loud?"',
    ],
    "violence": [
        'Outside class somebody said, "{term}, then," like they wanted a fight after school.',
        'The boys in the group chat were typing, "{term} if he keeps talking."',
        'A voice note ended with, "{term}, I am not joking."',
        'In the movie-style hallway scene, one kid snaps, "{term}," and steps forward.',
        'At recess the rumor going around was, "He said {term} the second he sees him."',
    ],
    "dangerous": [
        'In the chat somebody bragged, "That was a full {term} and nobody caught us."',
        'At lunch they kept replaying the story like, "Bro tried a {term} at school."',
        'The line that got everyone staring was, "{term} was not even worth getting caught for."',
        'In a movie-script kind of voice, he says, "One more {term} and we are suspended."',
        'A message in the thread said, "Do not make this another {term} situation."',
    ],
    "other": [
        'In the group chat somebody typed, "{term}," and five people answered at once.',
        'At the lunch table one friend said, "{term}," and everybody knew what she meant.',
        'The caption under the selfie was just, "{term}," with three laughing emojis.',
        'In a movie-scene kind of exchange, one kid leans over and goes, "{term}."',
        'Walking out of class, I heard someone say, "{term}," like the whole thing was obvious.',
    ],
}


def style_examples(category: str) -> list[str]:
    if category == "insult":
        return STYLE_BANK["insult"]
    if category == "vulgarity":
        return STYLE_BANK["vulgarity"]
    if category == "sexual":
        return STYLE_BANK["sexual"]
    if category == "violence":
        return STYLE_BANK["violence"]
    if category == "dangerous":
        return STYLE_BANK["dangerous"]
    return STYLE_BANK["other"]


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
        if term not in TARGET_TERMS:
            continue
        for template in style_examples(category):
            example = template.format(term=term)
            key = (term, example)
            if key in existing_pairs:
                continue
            existing_pairs.add(key)
            appended_rows.append({"term": term, "example": example})

    with EXAMPLE_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["term", "example"])
        writer.writeheader()
        writer.writerows(existing_rows + appended_rows)

    print(f"Added {len(appended_rows)} richer Gen Z examples to {EXAMPLE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
