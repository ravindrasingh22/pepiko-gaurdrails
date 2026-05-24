from __future__ import annotations

import csv
from pathlib import Path


CSV_PATH = Path(__file__).resolve().parent / "master-profinity-terms.csv"


def main() -> int:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    fieldnames = [name for name in rows[0].keys() if name != "usage_examples"]

    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fieldnames})

    print(f"Removed usage_examples from {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
