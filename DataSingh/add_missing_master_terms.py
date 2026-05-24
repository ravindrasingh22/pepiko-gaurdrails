from __future__ import annotations

import csv
from pathlib import Path


CSV_PATH = Path(__file__).resolve().parent / "master-terms.csv"

MISSING_TERMS = [
    ("assmunch", "insult"),
    ("big black cock", "sexual"),
    ("bloody", "vulgarity"),
    ("blowjob", "sexual"),
    ("brainfuck", "vulgarity"),
    ("chicken shit", "insult"),
    ("ching chong", "slur: ethnicity/race"),
    ("clusterfuck", "vulgarity"),
    ("coonass", "slur: ethnicity/race"),
    ("cornhole", "sexual"),
    ("cox-zucker machine", "other"),
    ("cracker", "slur: ethnicity/race"),
    ("damnation", "expletive"),
    ("dumbass", "insult"),
    ("enshittification", "vulgarity"),
    ("feck", "vulgarity"),
    ("list of films that most frequently use the word fuck", "other"),
    ("fuck her right in the pussy", "sexual"),
    ("fuck joe biden", "other"),
    ("fuck, marry, kill", "other"),
    ("fuckery", "vulgarity"),
    ("gay", "slur: lgbtq"),
    ("grab 'em by the pussy", "sexual"),
    ("healslut", "sexual"),
    ("hell", "expletive"),
    ("hori", "slur: ethnicity/race"),
    ("if you see kay", "other"),
    ("jesus fucking christ", "expletive"),
    ("use of nigger in proper names", "other"),
    ("niggerhead", "slur: ethnicity/race"),
    ("pajeet", "slur: ethnicity/race"),
    ("polaco", "slur: ethnicity/race"),
    ("poof", "slur: lgbtq"),
    ("poofter", "slur: lgbtq"),
    ("prick", "insult"),
    ("queer", "slur: lgbtq"),
    ("ratfucking", "vulgarity"),
    ("russian warship, go fuck yourself", "vulgarity"),
    ("serving cunt", "sexual"),
    ("shit happens", "expletive"),
    ("shithouse", "vulgarity"),
    ("shitposting", "vulgarity"),
    ("shitter", "vulgarity"),
    ("shut the fuck up", "vulgarity"),
    ("shut the hell up", "expletive"),
    ("son of a bitch", "vulgarity"),
    ("taking the piss", "vulgarity"),
    ("unclefucker", "sexual"),
]


def main() -> int:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0].keys())

    seen = {row["term"].strip().lower() for row in rows}
    for term, category in MISSING_TERMS:
        if term in seen:
            continue
        rows.append(
            {
                "term": term,
                "category": category,
                "data_curated": "",
            }
        )
        seen.add(term)

    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Added missing terms to {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
