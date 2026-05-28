from __future__ import annotations

import csv
from pathlib import Path

from datasets import get_dataset_config_names, get_dataset_split_names, load_dataset


DATASET_ID = "walledai/HarmBench"
CONFIG = "standard"
OUTPUT_DIR = Path(__file__).resolve().parent / "curated" / "HarmBench"


def _extract_value(value: object) -> str:
    if isinstance(value, dict) and "value" in value:
        value = value.get("value")
    if value is None:
        return ""
    return str(value)


def _normalize_row(row: dict[str, object], fieldnames: list[str]) -> dict[str, str]:
    return {field: _extract_value(row.get(field)) for field in fieldnames}


def write_split(split: str) -> tuple[int, Path]:
    dataset = load_dataset(DATASET_ID, CONFIG, split=split)
    fieldnames = list(dataset.column_names)
    rows = [_normalize_row(row, fieldnames) for row in dataset]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"harmbench_{CONFIG}_{split}.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows), output_path


def main() -> int:
    print(f"Dataset: {DATASET_ID}")
    print(f"Config: {CONFIG}")
    print(f"Output directory: {OUTPUT_DIR}")

    configs = get_dataset_config_names(DATASET_ID)
    if CONFIG not in configs:
        raise ValueError(f"Config '{CONFIG}' not found. Available configs: {configs}")

    splits = get_dataset_split_names(DATASET_ID, CONFIG)
    for split in splits:
        row_count, output_path = write_split(split)
        print(f"Split: {split}")
        print(f"Output: {output_path}")
        print(f"Rows written: {row_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
