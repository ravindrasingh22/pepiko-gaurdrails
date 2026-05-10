from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.guardrails.gate_mapper import AGE_POLICY
from training.slm_classifier.data_pipeline import (
    CANONICAL_DATASET,
    DATASET_SPLITS_PATH,
    GL_COLUMNS,
    LABEL_VOCAB_PATH,
    validate_dataset_rows,
    write_dataset_splits,
    write_label_vocab,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "docs" / "Religion-politics-idealogy.csv"
NORMALIZED_CSV = ROOT / "data" / "processed" / "religion_politics_ideology_normalized.csv"
RAW_DIR = ROOT / "data" / "raw"
MERGED_NORMALIZED_CSV = ROOT / "data" / "processed" / "slm_training_normalized.csv"
AGE_BANDS = tuple(AGE_POLICY.keys())
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
G2_PRIORITY = [
    "UNSAFE_CONTENT",
    "GROOMING",
    "COERCIVE_CONTROL",
    "VULN_EXPLOIT",
    "DANGEROUS",
    "HATE_GROUP",
    "PD",
    "LP",
    "COMPARATIVE",
    "EMOTIONAL",
    "NEUTRAL_FACT",
    "GENERIC_INTENT",
]


@dataclass
class AuthoringRow:
    source_row: int
    topic: str
    question: str
    guideline_tags: list[str]
    g1: str
    g2: str
    g3: str
    g4: str


@dataclass
class SheetSchema:
    topic_idx: int
    question_idx: int
    guideline_tags_idx: int
    g1_idx: int
    g2_idx: int
    g3_idx: int
    g4_idx: int
    generated_prompt_idx: int | None = None
    header_row_index: int = 0


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return cleaned or "sample"


def _parse_guideline_tags(raw: str) -> list[str]:
    return sorted(dict.fromkeys(TAG_RE.findall(raw or "")))


def _clean_gate_value(raw: str) -> str:
    value = (raw or "").split("|", 1)[0].strip()
    aliases = {
        "BLOCK + ESCALATE": "BLOCK_ESCALATE",
        "BLOCK (Hard)": "BLOCK_HARD",
        "TRANSFORM (hold)": "TRANSFORM_HOLD",
    }
    return aliases.get(value, value)


def _clean_g2_value(raw: str) -> str:
    value = _clean_gate_value(raw)
    aliases = {
        "GAMBLING": "PD",
    }
    value = aliases.get(value, value)
    if "," not in value:
        return value
    parts = [item.strip() for item in value.split(",") if item.strip()]
    for item in G2_PRIORITY:
        if item in parts:
            return item
    return parts[0] if parts else ""


def _gl_vector(tags: list[str]) -> dict[str, int]:
    active = {tag.lower().replace("-", "_") for tag in tags}
    return {column: int(column in active) for column in GL_COLUMNS}


def _infer_guideline_tags(g1: str, g2: str, g3: str, g4: str) -> list[str]:
    tags = {"GL-01"}
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
    if g2 == "BULLYING":
        tags.add("GL-09")
    if g2 == "GROOMING":
        tags.add("GL-10")
    if g2 == "UNSAFE_CONTENT":
        tags.add("GL-11")
    if g2 == "COERCIVE_CONTROL":
        tags.add("GL-12")
    if g2 == "VULN_EXPLOIT":
        tags.add("GL-13")
    if g2 == "SELF_HARM":
        tags.add("GL-06")
    if g2 == "AMBIGUOUS_RISK":
        tags.add("GL-07")
    return sorted(tags)


def _find_header_index(row: list[str], candidates: tuple[str, ...]) -> int | None:
    normalized = [_slugify(cell) for cell in row]
    for idx, cell in enumerate(normalized):
        if cell in candidates:
            return idx
    return None


def _detect_schema(path: Path) -> SheetSchema:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ValueError(f"Empty raw sheet: {path}")

    for idx, row in enumerate(rows[:5]):
        topic_idx = _find_header_index(row, ("topic",))
        question_idx = _find_header_index(row, ("question",))
        gl_idx = _find_header_index(row, ("gl",))
        g1_idx = _find_header_index(row, ("g1",))
        g2_idx = _find_header_index(row, ("g2",))
        g3_idx = _find_header_index(row, ("g3",))
        g4_idx = _find_header_index(row, ("g4",))
        prompt_idx = _find_header_index(row, ("generated_prompt",))
        if None not in {topic_idx, question_idx, gl_idx, g1_idx, g2_idx, g3_idx, g4_idx}:
            return SheetSchema(
                topic_idx=int(topic_idx),
                question_idx=int(question_idx),
                guideline_tags_idx=int(gl_idx),
                g1_idx=int(g1_idx),
                g2_idx=int(g2_idx),
                g3_idx=int(g3_idx),
                g4_idx=int(g4_idx),
                generated_prompt_idx=int(prompt_idx) if prompt_idx is not None else None,
                header_row_index=idx,
            )
    raise ValueError(f"Unsupported raw sheet format: {path}")


def load_authoring_rows(path: Path = DEFAULT_SOURCE) -> list[AuthoringRow]:
    schema = _detect_schema(path)
    rows: list[AuthoringRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row_number, row in enumerate(reader, start=1):
            if row_number <= schema.header_row_index + 1:
                continue
            question = (row[schema.question_idx] if len(row) > schema.question_idx else "").strip()
            if not question:
                continue
            topic = (row[schema.topic_idx] if len(row) > schema.topic_idx else "").strip() or "Unknown"
            g1 = _clean_gate_value(row[schema.g1_idx] if len(row) > schema.g1_idx else "")
            g2 = _clean_g2_value(row[schema.g2_idx] if len(row) > schema.g2_idx else "")
            g3 = _clean_gate_value(row[schema.g3_idx] if len(row) > schema.g3_idx else "")
            g4 = _clean_gate_value(row[schema.g4_idx] if len(row) > schema.g4_idx else "")
            if not any((g1, g2, g3, g4)):
                # Some source sheets include category/header rows in the question column.
                # They are not trainable examples and must be skipped before dataset validation.
                continue
            guideline_tags = _parse_guideline_tags(row[schema.guideline_tags_idx] if len(row) > schema.guideline_tags_idx else "")
            if not guideline_tags:
                guideline_tags = _infer_guideline_tags(g1, g2, g3, g4)
            elif "GL-01" not in guideline_tags:
                guideline_tags = sorted({"GL-01", *guideline_tags})
            rows.append(
                AuthoringRow(
                    source_row=row_number,
                    topic=topic,
                    question=question,
                    guideline_tags=guideline_tags,
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
                    "reference_answer": "",
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
    raw_sources: list[Path] = []
    for path in sorted(RAW_DIR.glob("*")):
        if path.suffix.lower() != ".csv" or path.name.startswith(".") or path.name.lower() == "gl-codebook.csv":
            continue
        try:
            _detect_schema(path)
        except ValueError:
            continue
        raw_sources.append(path)
    if raw_sources:
        return raw_sources
    if DEFAULT_SOURCE.exists():
        return [DEFAULT_SOURCE]
    return []


def expand_all_sources(paths: list[Path] | None = None) -> list[dict[str, object]]:
    source_paths = paths or discover_source_files()
    if not source_paths:
        raise ValueError("No supported training source files found in data/raw and no default source is available.")
    rows: list[dict[str, object]] = []
    for path in source_paths:
        rows.extend(expand_authoring_rows(path))
    return rows


def _csv_safe_row(row: dict[str, object]) -> dict[str, object]:
    safe_row = dict(row)
    age_band = str(safe_row.get("age_band", "")).strip()
    if age_band:
        safe_row["age_band"] = f'="{age_band}"'
    return safe_row


def write_normalized_csv(source_path: Path = DEFAULT_SOURCE, target_path: Path = NORMALIZED_CSV) -> Path:
    rows = expand_authoring_rows(source_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_COLUMNS)
        writer.writeheader()
        writer.writerows(_csv_safe_row(row) for row in rows)
    return target_path


def write_merged_normalized_csv(paths: list[Path] | None = None, target_path: Path = MERGED_NORMALIZED_CSV) -> Path:
    rows = expand_all_sources(paths)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_COLUMNS)
        writer.writeheader()
        writer.writerows(_csv_safe_row(row) for row in rows)
    return target_path


def write_canonical_jsonl(source_path: Path | None = None, target_path: Path = CANONICAL_DATASET) -> Path:
    return write_canonical_jsonl_with_metadata(source_path=source_path, target_path=target_path)


def write_canonical_jsonl_with_metadata(
    source_path: Path | None = None,
    target_path: Path = CANONICAL_DATASET,
    split_target_path: Path | None = None,
    vocab_target_path: Path | None = None,
) -> Path:
    rows = expand_all_sources([source_path] if isinstance(source_path, Path) else None)
    validate_dataset_rows(rows)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = {key: row[key] for key in ["sample_id", "question", "age_band", "language", "recent_context", *GL_COLUMNS, "g1", "g2", "g3", "g4"]}
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    write_dataset_splits(rows, target_path=split_target_path or DATASET_SPLITS_PATH)
    write_label_vocab(target_path=vocab_target_path or LABEL_VOCAB_PATH)
    return target_path


def main() -> None:
    csv_path = write_merged_normalized_csv()
    jsonl_path = write_canonical_jsonl()
    print(f"Normalized CSV: {csv_path}")
    print(f"Canonical JSONL: {jsonl_path}")


if __name__ == "__main__":
    main()
