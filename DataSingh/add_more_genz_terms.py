from __future__ import annotations

import csv
from pathlib import Path


CSV_PATH = Path(__file__).resolve().parent / "master-terms.csv"

MORE_GENZ_TERMS = [
    ("oh nah", "other"),
    ("nah bro", "other"),
    ("bro is wild", "other"),
    ("bro thought", "other"),
    ("bro really said", "other"),
    ("say less", "other"),
    ("real", "other"),
    ("it is giving", "other"),
    ("giving", "other"),
    ("understood the assignment", "other"),
    ("mewing", "other"),
    ("mog", "insult"),
    ("mogged", "insult"),
    ("fanum tax", "other"),
    ("goofy", "insult"),
    ("goofy ahh", "insult"),
    ("goofy ahh kid", "insult"),
    ("wildin", "other"),
    ("wilding", "other"),
    ("crash out", "other"),
    ("crashing out", "other"),
    ("corny", "insult"),
    ("cheugy", "insult"),
    ("cheug", "insult"),
    ("sassy", "other"),
    ("zesty", "insult"),
    ("feral", "other"),
    ("ick", "other"),
    ("the ick", "other"),
    ("hard launch", "other"),
    ("soft block", "other"),
    ("hard block", "other"),
    ("unadd", "other"),
    ("unfriend me then", "other"),
    ("blocked and reported", "other"),
    ("caught in 4k", "other"),
    ("in 4k", "other"),
    ("clock it", "other"),
    ("clocked", "other"),
    ("you thought you ate", "insult"),
    ("who asked", "insult"),
    ("be so serious", "other"),
    ("bffr right now", "other"),
    ("cry about it", "insult"),
    ("stay mad", "insult"),
    ("mad for what", "insult"),
    ("you wish", "insult"),
    ("rent free", "insult"),
    ("not the", "other"),
    ("side eye", "insult"),
    ("bombastic side eye", "insult"),
    ("criminal offensive side eye", "insult"),
    ("period", "other"),
    ("periodt", "other"),
    ("as you should", "other"),
    ("delusionship", "other"),
    ("friendzoned", "other"),
    ("down bad", "other"),
    ("caught feelings", "other"),
    ("main feed", "other"),
    ("finsta", "other"),
    ("spam account", "other"),
    ("face reveal", "other"),
    ("feet pics", "sexual"),
    ("thirsty", "sexual"),
    ("thirsting", "sexual"),
    ("devious lick", "dangerous"),
    ("lick", "dangerous"),
    ("opp pack", "violence"),
    ("on sight", "violence"),
    ("run the fade", "violence"),
    ("catch these hands", "violence"),
    ("swing first", "violence"),
    ("snatched", "other"),
    ("ate and left no crumbs", "other"),
    ("serving", "other"),
    ("serve", "other"),
    ("girl math", "other"),
    ("boy math", "other"),
    ("girl dinner", "other"),
    ("npc energy", "insult"),
    ("villain arc", "other"),
    ("glazing", "insult"),
    ("meatriding", "insult"),
    ("meat riding", "insult"),
    ("cooked beyond repair", "other"),
    ("deep fried", "other"),
    ("fried", "other"),
    ("bop", "sexual"),
    ("ran through", "sexual"),
    ("for the streets", "sexual"),
    ("chat is this real", "other"),
    ("chat am i cooked", "other"),
    ("ts pmo", "insult"),
    ("ts", "other"),
    ("pmo", "other"),
    ("stfu", "vulgarity"),
    ("gtfo", "vulgarity"),
    ("oml", "other"),
    ("omg", "other"),
    ("frfr", "other"),
    ("deadass", "vulgarity"),
    ("type shi", "other"),
    ("type shit", "vulgarity"),
    ("big yikes", "insult"),
    ("yikes", "insult"),
    ("nah fam", "other"),
    ("fr tho", "other"),
    ("not gonna hold you", "other"),
    ("ion know", "other"),
    ("ion care", "insult"),
    ("tf", "vulgarity"),
    ("wtv", "other"),
    ("whatever bro", "insult"),
    ("doing too much", "insult"),
    ("extra", "insult"),
    ("pick a struggle", "insult"),
    ("youre cooked", "insult"),
    ("you are cooked", "insult"),
    ("low taper fade", "other"),
    ("huzz", "other"),
    ("unc status", "insult"),
    ("unc", "insult"),
    ("auntie behavior", "insult"),
    ("fed", "insult"),
    ("snitch", "insult"),
    ("ops", "insult"),
    ("clout", "other"),
    ("clout chaser", "insult"),
]


def main() -> int:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0].keys())

    seen = {row["term"].strip().lower() for row in rows}
    added = 0
    for term, category in MORE_GENZ_TERMS:
        if term in seen:
            continue
        rows.append({"term": term, "category": category, "data_curated": ""})
        seen.add(term)
        added += 1

    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Added {added} more Gen Z terms to {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
