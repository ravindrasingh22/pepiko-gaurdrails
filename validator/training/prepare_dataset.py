from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


SAFE_LABELS = {"0", "safe", "SAFE", "false", "False"}
UNSAFE_LABELS = {"1", "unsafe", "UNSAFE", "true", "True"}


def _parse_label(value: object) -> int:
    raw = str(value).strip()
    if raw in SAFE_LABELS:
        return 0
    if raw in UNSAFE_LABELS:
        return 1
    raise ValueError(f"unsupported label value: {value!r}")


def _format_text(age_group: str, response_text: str) -> str:
    return f"Age Group: {age_group.strip()} | Content: {' '.join(response_text.strip().split())}"


def convert_csv_to_json(
    *,
    source_path: Path,
    output_path: Path,
    age_group_column: str,
    response_text_column: str,
    label_column: str,
) -> None:
    rows: list[dict[str, object]] = []
    with source_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader, start=2):
            age_group = str(row.get(age_group_column, "")).strip()
            response_text = str(row.get(response_text_column, "")).strip()
            if not age_group or not response_text:
                continue
            try:
                label = _parse_label(row.get(label_column, ""))
            except ValueError as exc:
                raise ValueError(f"{source_path}:{row_index}: {exc}") from exc
            rows.append({"text": _format_text(age_group, response_text), "label": label})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert validator CSV rows to DeBERTa sequence-classifier JSON.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", default=Path("validator/data/processed/dataset.json"), type=Path)
    parser.add_argument("--age-group-column", default="age_group")
    parser.add_argument("--response-text-column", default="response_text")
    parser.add_argument("--label-column", default="label")
    args = parser.parse_args()

    convert_csv_to_json(
        source_path=args.source,
        output_path=args.output,
        age_group_column=args.age_group_column,
        response_text_column=args.response_text_column,
        label_column=args.label_column,
    )


if __name__ == "__main__":
    main()
