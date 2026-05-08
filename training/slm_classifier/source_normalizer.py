from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from training.slm_classifier.data_pipeline import CANONICAL_DATASET, GL_COLUMNS


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "docs" / "Religion-politics-idealogy.csv"
NORMALIZED_CSV = ROOT / "data" / "processed" / "religion_politics_ideology_normalized.csv"
RAW_DIR = ROOT / "data" / "raw"
MERGED_NORMALIZED_CSV = ROOT / "data" / "processed" / "slm_training_normalized.csv"
AGE_BANDS = ("5-8", "9-12", "13-17")
AGE_RESPONSE_INDEX = {"5-8": 1, "9-12": 2, "13-17": 3}
TAG_RE = re.compile(r"GL-\d{2}")
CANONICAL_COLUMNS = [
    "sample_id",
    "source_file",
    "source_row",
    "topic",
    "question",
    "age_band",
    "language",
    "recent_context",
    "reference_answer",
    "guideline_tags",
    *GL_COLUMNS,
    "g1",
    "g2",
    "g3",
    "g4",
]


@dataclass
class AuthoringRow:
    source_row: int
    topic: str
    question: str
    age_answers: dict[str, str]
    guideline_tags: list[str]
    g1: str
    g2: str
    g3: str
    g4: str


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return cleaned or "sample"


def _parse_guideline_tags(raw: str) -> list[str]:
    return TAG_RE.findall(raw or "")


def _clean_gate_value(raw: str) -> str:
    return (raw or "").split("|", 1)[0].strip()


def _gl_vector(tags: list[str]) -> dict[str, int]:
    active = {tag.lower().replace("-", "_") for tag in tags}
    return {column: int(column in active) for column in GL_COLUMNS}


def _infer_guideline_tags(g1: str, g2: str, g3: str, g4: str) -> list[str]:
    tags = {"GL-01"}
    if g2 == "NEUTRAL_FACT":
        tags.add("GL-09")
    if g2 == "COMPARATIVE":
        tags.add("GL-02")
    if g2 == "PD":
        tags.add("GL-03")
    if g2 == "LP":
        tags.add("GL-04")
    if g2 == "DANGEROUS":
        tags.add("GL-05")
    if g2 == "EMOTIONAL" or g1 == "DEATH_GRIEF":
        tags.add("GL-06")
    if g2 == "HATE_GROUP":
        tags.add("GL-08")
    if g2 == "GROOMING":
        tags.add("GL-10")
    if g2 == "UNSAFE_CONTENT":
        tags.add("GL-11")
    if g2 == "COERCIVE_CONTROL":
        tags.add("GL-12")
    if g2 == "VULN_EXPLOIT":
        tags.add("GL-13")
    if g2 == "COMPARATIVE" or g4 == "TRANSFORM":
        tags.add("GL-07")
    return sorted(tags)


def load_authoring_rows(path: Path = DEFAULT_SOURCE) -> list[AuthoringRow]:
    rows: list[AuthoringRow] = []
    current_topic = ""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row_number, row in enumerate(reader, start=1):
            if row_number <= 2:
                continue
            first = (row[0] if row else "").strip()
            if not first:
                continue
            if first.isupper() and len(first.split()) <= 3:
                current_topic = first.title()
                continue
            guideline_tags = _parse_guideline_tags((row[5] if len(row) > 5 else "").strip())
            g1 = _clean_gate_value((row[6] if len(row) > 6 else "").strip())
            g2 = _clean_gate_value((row[7] if len(row) > 7 else "").strip())
            g3 = _clean_gate_value((row[8] if len(row) > 8 else "").strip())
            g4 = _clean_gate_value((row[9] if len(row) > 9 else "").strip())
            rows.append(
                AuthoringRow(
                    source_row=row_number,
                    topic=current_topic or "Unknown",
                    question=first,
                    age_answers={age_band: (row[index] or "").strip() for age_band, index in AGE_RESPONSE_INDEX.items()},
                    guideline_tags=guideline_tags or _infer_guideline_tags(g1, g2, g3, g4),
                    g1=g1,
                    g2=g2,
                    g3=g3,
                    g4=g4,
                )
            )
    return rows


def expand_authoring_rows(path: Path = DEFAULT_SOURCE) -> list[dict[str, object]]:
    source_name = path.name
    normalized: list[dict[str, object]] = []
    for item_index, row in enumerate(load_authoring_rows(path), start=1):
        tag_vector = _gl_vector(row.guideline_tags)
        base_id = f"{_slugify(row.topic)}_{item_index:03d}_{_slugify(row.question)[:32]}"
        for age_band in AGE_BANDS:
            normalized.append(
                {
                    "sample_id": f"{base_id}_{age_band.replace('-', '_')}",
                    "source_file": source_name,
                    "source_row": row.source_row,
                    "topic": row.topic,
                    "question": row.question,
                    "age_band": age_band,
                    "language": "en",
                    "recent_context": "none",
                    "reference_answer": row.age_answers[age_band],
                    "guideline_tags": ",".join(row.guideline_tags),
                    **tag_vector,
                    "g1": row.g1,
                    "g2": row.g2,
                    "g3": row.g3,
                    "g4": row.g4,
                }
            )
    return normalized


def discover_source_files() -> list[Path]:
    raw_sources = sorted(path for path in RAW_DIR.glob("*") if path.suffix.lower() == ".csv")
    return raw_sources or [DEFAULT_SOURCE]


def expand_all_sources(paths: list[Path] | None = None) -> list[dict[str, object]]:
    source_paths = paths or discover_source_files()
    rows: list[dict[str, object]] = []
    for path in source_paths:
        rows.extend(expand_authoring_rows(path))
    return rows


def write_normalized_csv(source_path: Path = DEFAULT_SOURCE, target_path: Path = NORMALIZED_CSV) -> Path:
    rows = expand_authoring_rows(source_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return target_path


def write_merged_normalized_csv(paths: list[Path] | None = None, target_path: Path = MERGED_NORMALIZED_CSV) -> Path:
    rows = expand_all_sources(paths)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return target_path


def write_canonical_jsonl(source_path: Path | None = None, target_path: Path = CANONICAL_DATASET) -> Path:
    rows = expand_all_sources([source_path] if isinstance(source_path, Path) else None)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = {key: row[key] for key in ["sample_id", "question", "age_band", "language", "recent_context", *GL_COLUMNS, "g1", "g2", "g3", "g4"]}
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    return target_path


def main() -> None:
    csv_path = write_merged_normalized_csv()
    jsonl_path = write_canonical_jsonl()
    print(f"Normalized CSV: {csv_path}")
    print(f"Canonical JSONL: {jsonl_path}")


if __name__ == "__main__":
    main()
