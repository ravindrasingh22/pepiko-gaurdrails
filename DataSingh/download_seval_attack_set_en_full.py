from __future__ import annotations

import csv
from pathlib import Path

from datasets import load_dataset


DATASET_ID = "IS2Lab/S-Eval"
CONFIG = "attack_set_en_full"
SPLIT = "test"
OUTPUT_DIR = Path(__file__).resolve().parent / "curated" / "S-Eval"
OUTPUT_PATH = OUTPUT_DIR / "seval_attack_set_en_full_test.csv"


def _extract_value(value: object) -> str:
    if isinstance(value, dict) and "value" in value:
        value = value.get("value")
    if value is None:
        return ""
    return str(value)


def _normalize_row(row: dict[str, object], fieldnames: list[str]) -> dict[str, str]:
    return {field: _extract_value(row.get(field)) for field in fieldnames}


def iter_rows() -> tuple[list[str], list[dict[str, str]]]:
    dataset = load_dataset(DATASET_ID, CONFIG, split=SPLIT)
    fieldnames = list(dataset.column_names)
    rows = [_normalize_row(row, fieldnames) for row in dataset]
    return fieldnames, rows


def write_csv(fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    print(f"Dataset: {DATASET_ID}")
    print(f"Config: {CONFIG}")
    print(f"Split: {SPLIT}")
    print(f"Output: {OUTPUT_PATH}")

    fieldnames, rows = iter_rows()
    write_csv(fieldnames, rows)
    print(f"Columns: {', '.join(fieldnames)}")
    print(f"Rows written: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
