from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.guardrails.runtime_contracts import G2_ALIAS_MAP, build_applies_when_flags
from training.slm_classifier.data_pipeline import (
    CANONICAL_DATASET,
    DATASET_SPLITS_PATH,
    GL_COLUMNS,
    G2_VOCAB,
    LABEL_VOCAB_PATH,
    validate_dataset_rows,
    write_dataset_splits,
    write_label_vocab,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "docs" / "Religion-politics-idealogy.csv"
RAW_DIR = ROOT / "data" / "raw"
NORMALIZED_RAW_DIR = RAW_DIR / "normalized"
NORMALIZED_CSV = NORMALIZED_RAW_DIR / "slm_training_normalized.csv"
MERGED_NORMALIZED_CSV = NORMALIZED_RAW_DIR / "slm_training_merged.csv"
REJECTED_ROWS_CSV = NORMALIZED_RAW_DIR / "slm_training_rejected_rows.csv"
TAG_RE = re.compile(r"GL\s*[-\u2010\u2011\u2012\u2013\u2014\u2212]?\s*\d{2}", re.IGNORECASE)
CANONICAL_COLUMNS = [
    "sample_id",
    "question",
    "question_normalized",
    "normalization_notes",
    "language",
    "age_band",
    "source",
    "difficulty",
    "g1",
    "g1_reason",
    "g2",
    "g2_reasons",
    "applies_when_flags",
    "review_status",
    "source_file",
    "source_row",
]

@dataclass
class AuthoringRow:
    source_row: int
    topic: str
    question: str
    guideline_tags: list[str]
    g1: str
    g2: list[str]


@dataclass
class SheetSchema:
    topic_idx: int | None
    question_idx: int
    guideline_tags_idx: int
    g1_idx: int
    g2_idx: int
    g3_idx: int | None
    g4_idx: int | None
    generated_prompt_idx: int | None = None
    header_row_index: int = 0


@dataclass
class RejectedAuthoringRow:
    source_file: str
    source_row: int
    topic: str
    question: str
    gl: str
    g1: str
    g2: str
    g3: str
    g4: str
    rejection_reason: str


@dataclass
class AuthoringLoadResult:
    accepted_rows: list[AuthoringRow]
    rejected_rows: list[RejectedAuthoringRow]


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return cleaned or "sample"


def _parse_guideline_tags(raw: str) -> list[str]:
    tags = []
    for item in TAG_RE.findall(raw or ""):
        normalized = item.strip().upper()
        normalized = re.sub(r"[-\u2010\u2011\u2012\u2013\u2014\u2212]", "-", normalized)
        normalized = normalized.replace(" ", "")
        tags.append(normalized)
    return sorted(dict.fromkeys(tags))


def _clean_question_text(raw: str) -> str:
    value = (raw or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def _clean_gate_value(raw: str) -> str:
    value = (raw or "").split("|", 1)[0].strip()
    aliases = {
        "BLOCK + ESCALATE": "BLOCK_ESCALATE",
        "BLOCK (Hard)": "BLOCK_HARD",
        "TRANSFORM (hold)": "TRANSFORM_HOLD",
    }
    return aliases.get(value, value)


def _clean_g2_values(raw: str) -> list[str]:
    value = _clean_gate_value(raw)
    if "," not in value:
        value = G2_ALIAS_MAP.get(value, value)
        if value and value not in G2_VOCAB:
            raise ValueError(f"Unsupported G2 LOV in source data: {value}")
        return [value] if value else []
    parts = [G2_ALIAS_MAP.get(item.strip(), item.strip()) for item in value.split(",") if item.strip()]
    unsupported = [item for item in parts if item not in G2_VOCAB]
    if unsupported:
        raise ValueError(f"Unsupported G2 LOVs in source data: {', '.join(sorted(dict.fromkeys(unsupported)))}")
    return list(dict.fromkeys(parts))


def _normalize_training_question(question: str) -> tuple[str, list[str]]:
    collapsed = " ".join(question.strip().split())
    notes: list[str] = []
    if collapsed != question:
        notes.append("collapsed repeated whitespace")
    return collapsed, notes


def _default_g1_reason(g1: str) -> str:
    return f"The question is classified under broad topic {g1}."


def _default_g2_reasons(question: str, g2_values: list[str]) -> dict[str, str]:
    return {g2: f"The question matches the {g2} framing or safety pattern." for g2 in g2_values}


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
        gl_idx = _find_header_index(row, ("gl", "guideline_tags", "guidelines", "gl_tags"))
        g1_idx = _find_header_index(row, ("g1",))
        g2_idx = _find_header_index(row, ("g2",))
        g3_idx = _find_header_index(row, ("g3",))
        g4_idx = _find_header_index(row, ("g4",))
        prompt_idx = _find_header_index(row, ("generated_prompt",))
        if None not in {question_idx, gl_idx, g1_idx, g2_idx}:
            return SheetSchema(
                topic_idx=int(topic_idx) if topic_idx is not None else None,
                question_idx=int(question_idx),
                guideline_tags_idx=int(gl_idx),
                g1_idx=int(g1_idx),
                g2_idx=int(g2_idx),
                g3_idx=int(g3_idx) if g3_idx is not None else None,
                g4_idx=int(g4_idx) if g4_idx is not None else None,
                generated_prompt_idx=int(prompt_idx) if prompt_idx is not None else None,
                header_row_index=idx,
            )
    raise ValueError(f"Unsupported raw sheet format: {path}")


def _load_authoring_rows_with_rejections(path: Path = DEFAULT_SOURCE) -> AuthoringLoadResult:
    schema = _detect_schema(path)
    rows: list[AuthoringRow] = []
    rejected_rows: list[RejectedAuthoringRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row_number, row in enumerate(reader, start=1):
            if row_number <= schema.header_row_index + 1:
                continue
            question = _clean_question_text(row[schema.question_idx] if len(row) > schema.question_idx else "")
            if not question:
                continue
            topic = (
                (row[schema.topic_idx] if schema.topic_idx is not None and len(row) > schema.topic_idx else "").strip()
                or "Generic"
            )
            g1 = _clean_gate_value(row[schema.g1_idx] if len(row) > schema.g1_idx else "")
            raw_gl = row[schema.guideline_tags_idx] if len(row) > schema.guideline_tags_idx else ""
            raw_g2 = row[schema.g2_idx] if len(row) > schema.g2_idx else ""
            g3 = _clean_gate_value(
                row[schema.g3_idx] if schema.g3_idx is not None and len(row) > schema.g3_idx else ""
            )
            g4 = _clean_gate_value(
                row[schema.g4_idx] if schema.g4_idx is not None and len(row) > schema.g4_idx else ""
            )
            try:
                g2 = _clean_g2_values(raw_g2)
            except ValueError as exc:
                rejected_rows.append(
                    RejectedAuthoringRow(
                        source_file=path.name,
                        source_row=row_number,
                        topic=topic,
                        question=question,
                        gl=raw_gl,
                        g1=g1,
                        g2=raw_g2.strip(),
                        g3=g3,
                        g4=g4,
                        rejection_reason=str(exc),
                    )
                )
                continue
            if not any((g1, g2, g3, g4)):
                # Some source sheets include category/header rows in the question column.
                # They are not trainable examples and must be skipped before dataset validation.
                continue
            guideline_tags = _parse_guideline_tags(raw_gl)
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
                )
            )
    return AuthoringLoadResult(accepted_rows=rows, rejected_rows=rejected_rows)


def load_authoring_rows(path: Path = DEFAULT_SOURCE) -> list[AuthoringRow]:
    return _load_authoring_rows_with_rejections(path).accepted_rows


def expand_authoring_rows(path: Path = DEFAULT_SOURCE) -> list[dict[str, object]]:
    source_name = path.name
    normalized: list[dict[str, object]] = []
    for item_index, row in enumerate(load_authoring_rows(path), start=1):
        base_id = f"{_slugify(row.topic)}_{item_index:03d}_{_slugify(row.question)[:32]}"
        question_normalized, normalization_notes = _normalize_training_question(row.question)
        normalized.append(
            {
                "sample_id": base_id,
                "question": row.question,
                "question_normalized": question_normalized,
                "normalization_notes": normalization_notes,
                "language": "en",
                "age_band": "11-12",
                "source": source_name,
                "difficulty": "medium",
                "g1": row.g1,
                "g1_reason": _default_g1_reason(row.g1),
                "g2": row.g2,
                "g2_reasons": _default_g2_reasons(row.question, row.g2),
                "applies_when_flags": build_applies_when_flags(row.question, row.g1, row.g2),
                "review_status": "approved",
                "source_file": source_name,
                "source_row": row.source_row,
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


def collect_rejected_rows(paths: list[Path] | None = None) -> list[dict[str, object]]:
    source_paths = paths or discover_source_files()
    rejected_rows: list[dict[str, object]] = []
    for path in source_paths:
        result = _load_authoring_rows_with_rejections(path)
        for row in result.rejected_rows:
            rejected_rows.append(
                {
                    "TOPIC": row.topic,
                    "Question": row.question,
                    "GL": row.gl,
                    "G1": row.g1,
                    "G2": row.g2,
                    "G3": row.g3,
                    "G4": row.g4,
                    "source_file": row.source_file,
                    "source_row": row.source_row,
                    "rejection_reason": row.rejection_reason,
                }
            )
    return rejected_rows


def _csv_safe_row(row: dict[str, object]) -> dict[str, object]:
    return dict(row)


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


def write_rejected_rows_csv(paths: list[Path] | None = None, target_path: Path = REJECTED_ROWS_CSV) -> Path:
    rows = collect_rejected_rows(paths)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["TOPIC", "Question", "GL", "G1", "G2", "G3", "G4", "source_file", "source_row", "rejection_reason"]
    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
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
    source_paths = [source_path] if isinstance(source_path, Path) else None
    rows = expand_all_sources(source_paths)
    validate_dataset_rows(rows)
    write_rejected_rows_csv(source_paths)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = {key: row[key] for key in CANONICAL_COLUMNS if key in row}
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    write_dataset_splits(rows, target_path=split_target_path or DATASET_SPLITS_PATH)
    write_label_vocab(rows, target_path=vocab_target_path or LABEL_VOCAB_PATH)
    return target_path


def main() -> None:
    csv_path = write_merged_normalized_csv()
    rejected_csv_path = write_rejected_rows_csv()
    jsonl_path = write_canonical_jsonl()
    print(f"Normalized CSV: {csv_path}")
    print(f"Rejected rows CSV: {rejected_csv_path}")
    print(f"Canonical JSONL: {jsonl_path}")


if __name__ == "__main__":
    main()
