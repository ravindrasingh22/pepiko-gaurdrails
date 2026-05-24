from __future__ import annotations

import csv
from pathlib import Path


CSV_PATH = Path(__file__).resolve().parent / "curated" / "profinity-dictionary.csv"


def article_for(term: str) -> str:
    return "an" if term[:1].lower() in {"a", "e", "i", "o", "u"} else "a"


def direct_examples(term: str) -> list[str]:
    article = article_for(term)
    return [
        f"You're such {article} {term}.",
        f"Don't be {article} {term}.",
        f"Only {article} {term} would do that.",
        f"Wow, what {article} {term}.",
        f"Move, {term}.",
    ]


def main() -> int:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0].keys())

    for start in range(0, 100, 5):
        term = rows[start]["term"]
        examples = direct_examples(term)
        for offset, text in enumerate(examples):
            row = rows[start + offset]
            row["text"] = text
            row["g1"] = "GENERIC"
            row["g2"] = "['BULLYING']"

    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Rewrote first 100 rows in {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
