from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.slm_classifier.infer import run_infer

EVAL_DIR = ROOT / "data" / "eval"

G1_OUTPUT_CANDIDATES = ("slm_g1", "g1_slm")
G2_OUTPUT_CANDIDATES = ("slm_g2", "g2_slm")
G1_MATCH_CANDIDATES = ("slm_g1_matched", "g1_slm_matched")
G2_MATCH_CANDIDATES = ("slm_g2_matched", "g2_slm_matched")


def _parse_expected_g2(value: str) -> set[str]:
    return {
        item.strip()
        for item in str(value or "").split(";")
        if item.strip()
    }


def _format_g2_output(primary_g2: str, g2_all_ids: list[str]) -> str:
    ordered: list[str] = []
    if primary_g2:
        ordered.append(primary_g2)
    for item in g2_all_ids:
        if item and item not in ordered:
            ordered.append(item)
    return ";".join(ordered)


def _load_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header row: {path}")
        rows = [dict(row) for row in reader]
        return rows, list(reader.fieldnames)


def _write_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _resolve_or_add_column(fieldnames: list[str], candidates: tuple[str, ...]) -> str:
    for name in candidates:
        if name in fieldnames:
            return name
    chosen = candidates[0]
    fieldnames.append(chosen)
    return chosen


def update_eval_sheet(filename: str) -> dict[str, int]:
    path = EVAL_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Eval file not found: {path}")
    if path.suffix.lower() != ".csv":
        raise ValueError("Only CSV eval sheets are supported.")

    rows, fieldnames = _load_rows(path)
    required = {"question", "expected_g1", "expected_g2"}
    missing = [name for name in required if name not in fieldnames]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    g1_output_column = _resolve_or_add_column(fieldnames, G1_OUTPUT_CANDIDATES)
    g2_output_column = _resolve_or_add_column(fieldnames, G2_OUTPUT_CANDIDATES)
    g1_match_column = _resolve_or_add_column(fieldnames, G1_MATCH_CANDIDATES)
    g2_match_column = _resolve_or_add_column(fieldnames, G2_MATCH_CANDIDATES)

    g1_matches = 0
    g2_matches = 0
    for row in rows:
        question = str(row.get("question", "")).strip()
        if not question:
            row[g1_output_column] = ""
            row[g2_output_column] = ""
            row[g1_match_column] = ""
            row[g2_match_column] = ""
            continue
        result = run_infer(
            mode="slm",
            question=question,
            age_band="9-10",
            language="en",
            recent_context="none",
            thresholds={"g1": 0.5, "g2": 0.5},
        )
        predicted_g1 = str(result.get("g1", {}).get("id", "")).strip()
        primary_g2 = str(result.get("g2", {}).get("id", "")).strip()
        predicted_g2_ids = [
            str(item).strip()
            for item in result.get("g2_all", {}).get("ids", [])
            if str(item).strip()
        ]
        predicted_g2 = {item for item in predicted_g2_ids}
        if primary_g2:
            predicted_g2.add(primary_g2)
        expected_g1 = str(row.get("expected_g1", "")).strip()
        expected_g2 = _parse_expected_g2(str(row.get("expected_g2", "")))
        g1_ok = predicted_g1 == expected_g1
        g2_ok = bool(expected_g2.intersection(predicted_g2))
        row[g1_output_column] = predicted_g1
        row[g2_output_column] = _format_g2_output(primary_g2, predicted_g2_ids)
        row[g1_match_column] = "TRUE" if g1_ok else "FALSE"
        row[g2_match_column] = "TRUE" if g2_ok else "FALSE"
        g1_matches += int(g1_ok)
        g2_matches += int(g2_ok)

    _write_rows(path, rows, fieldnames)
    return {
        "rows": len(rows),
        "g1_matches": g1_matches,
        "g2_matches": g2_matches,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Update an eval CSV in data/eval with SLM G1/G2 match flags.")
    parser.add_argument("filename", help="CSV filename inside data/eval")
    args = parser.parse_args()
    summary = update_eval_sheet(args.filename)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
