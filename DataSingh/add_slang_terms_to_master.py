from __future__ import annotations

import csv
from pathlib import Path


CSV_PATH = Path(__file__).resolve().parent / "master-terms.csv"

NEW_TERMS = [
    ("no cap", "other"),
    ("cap", "other"),
    ("fr", "other"),
    ("for real", "other"),
    ("lowkey", "other"),
    ("highkey", "other"),
    ("bet", "other"),
    ("slay", "other"),
    ("ate", "other"),
    ("left no crumbs", "other"),
    ("fire", "other"),
    ("lit", "other"),
    ("mid", "other"),
    ("sus", "other"),
    ("vibe", "other"),
    ("mood", "other"),
    ("tea", "other"),
    ("spill", "other"),
    ("main character", "other"),
    ("npc", "insult"),
    ("rizz", "other"),
    ("w", "other"),
    ("l", "other"),
    ("big w", "other"),
    ("take the l", "other"),
    ("glow up", "other"),
    ("flex", "other"),
    ("cringe", "insult"),
    ("based", "other"),
    ("valid", "other"),
    ("delulu", "insult"),
    ("touch grass", "insult"),
    ("ratio", "other"),
    ("cooked", "other"),
    ("locked in", "other"),
    ("brain rot", "other"),
    ("skibidi", "other"),
    ("sigma", "other"),
    ("alpha", "other"),
    ("beta", "insult"),
    ("aura points", "other"),
    ("6-7", "other"),
    ("six seven", "other"),
    ("chat", "other"),
    ("pookie", "other"),
    ("bestie", "other"),
    ("bro", "other"),
    ("bruh", "other"),
    ("girlie", "other"),
    ("squad", "other"),
    ("gang", "other"),
    ("fam", "other"),
    ("opp", "insult"),
    ("beef", "other"),
    ("drama", "other"),
    ("shade", "insult"),
    ("roast", "insult"),
    ("clap back", "other"),
    ("salty", "insult"),
    ("pressed", "insult"),
    ("ghosted", "other"),
    ("left on read", "other"),
    ("dry texting", "other"),
    ("soft launch", "other"),
    ("ship", "other"),
    ("crush", "other"),
    ("situationship", "other"),
    ("red flag", "other"),
    ("green flag", "other"),
    ("toxic", "insult"),
    ("gaslight", "other"),
    ("gatekeep", "other"),
    ("cancel", "other"),
    ("expose", "other"),
    ("receipts", "other"),
    ("screenshot it", "other"),
    ("dox", "other"),
    ("doxx", "other"),
    ("alt account", "other"),
    ("burner", "other"),
    ("dm", "other"),
    ("slide into dms", "other"),
    ("asl", "other"),
    ("don't tell", "other"),
    ("private snap", "other"),
    ("link up", "other"),
    ("sneaky link", "sexual"),
    ("plug", "other"),
    ("zaza", "other"),
    ("cart", "other"),
    ("vape", "other"),
    ("faded", "other"),
    ("kms", "other"),
    ("kys", "other"),
    ("i'm done", "other"),
    ("can't anymore", "other"),
    ("ugly", "insult"),
    ("chopped", "insult"),
    ("choppleganger", "insult"),
    ("gyatt", "sexual"),
    ("gyat", "sexual"),
    ("thirst trap", "sexual"),
    ("body count", "sexual"),
    ("smash", "sexual"),
    ("send pics", "sexual"),
    ("rate me", "other"),
    ("pick me", "insult"),
    ("karen", "insult"),
    ("simp", "insult"),
    ("stan", "other"),
    ("bffr", "other"),
    ("iykyk", "other"),
    ("tbh", "other"),
    ("ngl", "other"),
    ("afaik", "other"),
    ("idk", "other"),
    ("rn", "other"),
    ("smh", "other"),
    ("imo", "other"),
    ("imho", "other"),
    ("fomo", "other"),
    ("yolo", "other"),
    ("af", "vulgarity"),
    ("wtf", "vulgarity"),
]


def main() -> int:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0].keys())

    seen = {row["term"].strip().lower() for row in rows}
    added = 0
    for term, category in NEW_TERMS:
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
        added += 1

    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Added {added} new slang terms to {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
