from __future__ import annotations

import csv
from pathlib import Path


CSV_PATH = Path(__file__).resolve().parent / "curated" / "example-terms.csv"


def main() -> int:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["term"].strip(), row["example"].strip())
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"term": key[0], "example": key[1]})

    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["term", "example"])
        writer.writeheader()
        writer.writerows(deduped)

    print(f"Deduped {CSV_PATH}: {len(rows)} -> {len(deduped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
