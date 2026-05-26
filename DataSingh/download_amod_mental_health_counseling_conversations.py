from __future__ import annotations

import csv
from pathlib import Path

from datasets import load_dataset


DATASET_ID = "Amod/mental_health_counseling_conversations"
CONFIG = "default"
SPLIT = "train"
OUTPUT_DIR = Path(__file__).resolve().parent / "curated" / "Amod"
OUTPUT_PATH = OUTPUT_DIR / "mental_health_counseling_conversations_train_context_response.csv"
OUTPUT_COLUMNS = ["Context", "Response"]


def _extract_value(value: object) -> str:
    if isinstance(value, dict) and "value" in value:
        value = value.get("value")
    if value is None:
        return ""
    return str(value)


def _normalize_row(row: dict[str, object]) -> dict[str, str]:
    return {
        "Context": _extract_value(row.get("Context")),
        "Response": _extract_value(row.get("Response")),
    }


def iter_rows_from_datasets() -> tuple[int, list[dict[str, str]]]:
    dataset = load_dataset(DATASET_ID, CONFIG, split=SPLIT)
    rows = [_normalize_row(row) for row in dataset]
    return len(rows), rows


def write_csv(rows: list[dict[str, str]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    print(f"Dataset: {DATASET_ID}")
    print(f"Config: {CONFIG}")
    print(f"Split: {SPLIT}")
    print(f"Output: {OUTPUT_PATH}")

    total_rows, rows = iter_rows_from_datasets()
    write_csv(rows)
    print(f"Rows written: {total_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
