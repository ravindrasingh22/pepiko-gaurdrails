from __future__ import annotations

import csv
from pathlib import Path

from datasets import load_dataset


DATASET_ID = "SalKhan12/prompt-safety-dataset"
CONFIG = "default"
SPLIT = "train"
OUTPUT_DIR = Path(__file__).resolve().parent / "curated" / "SalKhan12"
OUTPUT_PATH = OUTPUT_DIR / "prompt_safety_dataset_train_text_label_content_category.csv"
OUTPUT_COLUMNS = ["text", "label", "content_category"]

TEXT_KEYS = ("text", "prompt", "input", "question")
LABEL_KEYS = ("label", "labels", "safety_label")
CONTENT_CATEGORY_KEYS = ("content_category", "category", "content_type")


def _extract_value(value: object) -> str:
    if isinstance(value, dict) and "value" in value:
        value = value.get("value")
    if value is None:
        return ""
    return str(value)


def _pick_first(row: dict[str, object], keys: tuple[str, ...]) -> str:
    for key in keys:
        if key in row:
            return _extract_value(row.get(key))
    return ""


def _normalize_row(row: dict[str, object]) -> dict[str, str]:
    return {
        "text": _pick_first(row, TEXT_KEYS),
        "label": _pick_first(row, LABEL_KEYS),
        "content_category": _pick_first(row, CONTENT_CATEGORY_KEYS),
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
