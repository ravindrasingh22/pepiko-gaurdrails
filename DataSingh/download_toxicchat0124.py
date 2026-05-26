from __future__ import annotations

import csv
import re
from pathlib import Path

from datasets import load_dataset


DATASET_ID = "lmsys/toxic-chat"
CONFIG = "toxicchat0124"
SPLIT = "train"
OUTPUT_DIR = Path(__file__).resolve().parent / "curated" / "toxicchat0124"
OUTPUT_PATH = OUTPUT_DIR / "toxicchat0124_train_user_input_model_output.csv"
ENGLISH_MARKERS = {
    "the", "and", "you", "your", "with", "that", "this", "for", "have", "are",
    "not", "can", "what", "how", "please", "help", "about", "from", "just", "was",
    "like", "they", "them", "there", "would", "should", "could", "into", "when",
}
WORD_RE = re.compile(r"[a-z']+")


def _extract_cell_value(cell: object) -> str:
    if isinstance(cell, dict) and "value" in cell:
        value = cell.get("value")
    else:
        value = cell
    if value is None:
        return ""
    return str(value)


def _looks_english(*parts: str) -> bool:
    text = " ".join(part for part in parts if part).strip()
    if not text:
        return False
    lowered = text.lower()
    words = WORD_RE.findall(lowered)
    if not words:
        return False
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    ascii_ratio = ascii_chars / len(text)
    marker_hits = sum(1 for word in words if word in ENGLISH_MARKERS)
    marker_ratio = marker_hits / len(words)
    return ascii_ratio >= 0.95 and (marker_hits >= 2 or marker_ratio >= 0.08)


def iter_rows() -> tuple[int, list[dict[str, str]]]:
    dataset = load_dataset(DATASET_ID, CONFIG, split=SPLIT)
    collected_rows = [
        {
            "user_input": _extract_cell_value(row.get("user_input")),
            "model_output": _extract_cell_value(row.get("model_output")),
        }
        for row in dataset
        if _looks_english(
            _extract_cell_value(row.get("user_input")),
            _extract_cell_value(row.get("model_output")),
        )
    ]
    return len(collected_rows), collected_rows


def write_csv(rows: list[dict[str, str]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["user_input", "model_output"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    print(f"Dataset: {DATASET_ID}")
    print(f"Config: {CONFIG}")
    print(f"Split: {SPLIT}")
    print(f"Output: {OUTPUT_PATH}")

    total_rows, rows = iter_rows()
    write_csv(rows)
    print(f"Rows written: {total_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
