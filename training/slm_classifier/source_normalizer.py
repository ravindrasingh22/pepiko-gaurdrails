from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.guardrails.runtime_contracts import G2_ALIAS_MAP
from training.slm_classifier.data_pipeline import (
    CANONICAL_DATASET,
    DATASET_SPLITS_PATH,
    G2_VOCAB,
    LABEL_VOCAB_PATH,
    CODEBOOK,
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
TOPIC_HEADER_CANDIDATES = ("topic", "topics")
QUESTION_HEADER_CANDIDATES = ("question", "questions", "prompt", "query")
G1_HEADER_CANDIDATES = ("g1", "g_1")
G2_HEADER_CANDIDATES = ("g2", "g_2")
G2_ALL_HEADER_CANDIDATES = ("g2_all", "g2all", "g_2_all", "g2_multi", "g2_multilabel")
G3_HEADER_CANDIDATES = ("g3", "g_3")
G4_HEADER_CANDIDATES = ("g4", "g_4")
CONTEXT_HEADER_CANDIDATES = ("context", "recent_context")
INTENT_FAMILIES_HEADER_CANDIDATES = ("intent_families", "intentfamilies")
INTENT_PHRASES_HEADER_CANDIDATES = ("intent_phrases", "intentphrases")
REVIEW_STATUS_HEADER_CANDIDATES = ("review_status", "reviewstatus")
GENERATED_PROMPT_HEADER_CANDIDATES = ("generated_prompt", "generatedprompt")
CANONICAL_COLUMNS = [
    "sample_id",
    "question",
    "context",
    "topic",
    "g1",
    "g2",
    "g2_all",
    "intent_families",
    "intent_phrases",
    "review_status",
]

@dataclass
class AuthoringRow:
    source_row: int
    question: str
    topic: str
    g1: str
    g2: list[str]
    g2_all: list[str]


@dataclass
class SheetSchema:
    topic_idx: int | None
    question_idx: int
    guideline_tags_idx: int | None
    g1_idx: int
    g2_idx: int
    g2_all_idx: int | None
    g3_idx: int | None
    g4_idx: int | None
    context_idx: int | None = None
    intent_families_idx: int | None = None
    intent_phrases_idx: int | None = None
    review_status_idx: int | None = None
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
    parsed_json = None
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed_json = json.loads(value)
        except json.JSONDecodeError:
            parsed_json = None
    if isinstance(parsed_json, list):
        parts = [G2_ALIAS_MAP.get(str(item).strip(), str(item).strip()) for item in parsed_json if str(item).strip()]
    elif "," in value:
        parts = [G2_ALIAS_MAP.get(item.strip(), item.strip()) for item in value.split(",") if item.strip()]
    else:
        value = G2_ALIAS_MAP.get(value, value)
        if value and value not in G2_VOCAB:
            raise ValueError(f"Unsupported G2 LOV in source data: {value}")
        return [value] if value else []
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


def _intent_fields_for_g2(g2_values: list[str]) -> tuple[list[str], list[str]]:
    families: list[str] = []
    phrases: list[str] = []
    for g2 in g2_values:
        spec = CODEBOOK.intent_lexicon.get(g2)
        if not spec:
            continue
        for family in spec.families:
            if family not in families:
                families.append(family)
        for phrase in spec.phrases:
            if phrase not in phrases:
                phrases.append(phrase)
    return families, phrases


def _find_header_index(row: list[str], candidates: tuple[str, ...]) -> int | None:
    normalized = [_slugify(cell) for cell in row]
    for idx, cell in enumerate(normalized):
        if cell in candidates:
            return idx
    return None


def _read_csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle))


def _detect_schema(path: Path) -> SheetSchema:
    rows = _read_csv_rows(path)
    if not rows:
        raise ValueError(f"Empty raw sheet: {path}")

    for idx, row in enumerate(rows[:5]):
        topic_idx = _find_header_index(row, TOPIC_HEADER_CANDIDATES)
        question_idx = _find_header_index(row, QUESTION_HEADER_CANDIDATES)
        gl_idx = _find_header_index(row, ("gl", "guideline_tags", "guidelines", "gl_tags"))
        g1_idx = _find_header_index(row, G1_HEADER_CANDIDATES)
        g2_idx = _find_header_index(row, G2_HEADER_CANDIDATES)
        g2_all_idx = _find_header_index(row, G2_ALL_HEADER_CANDIDATES)
        g3_idx = _find_header_index(row, G3_HEADER_CANDIDATES)
        g4_idx = _find_header_index(row, G4_HEADER_CANDIDATES)
        context_idx = _find_header_index(row, CONTEXT_HEADER_CANDIDATES)
        intent_families_idx = _find_header_index(row, INTENT_FAMILIES_HEADER_CANDIDATES)
        intent_phrases_idx = _find_header_index(row, INTENT_PHRASES_HEADER_CANDIDATES)
        review_status_idx = _find_header_index(row, REVIEW_STATUS_HEADER_CANDIDATES)
        prompt_idx = _find_header_index(row, GENERATED_PROMPT_HEADER_CANDIDATES)
        if None not in {question_idx, g1_idx, g2_idx}:
            return SheetSchema(
                topic_idx=int(topic_idx) if topic_idx is not None else None,
                question_idx=int(question_idx),
                guideline_tags_idx=int(gl_idx) if gl_idx is not None else None,
                g1_idx=int(g1_idx),
                g2_idx=int(g2_idx),
                g2_all_idx=int(g2_all_idx) if g2_all_idx is not None else None,
                g3_idx=int(g3_idx) if g3_idx is not None else None,
                g4_idx=int(g4_idx) if g4_idx is not None else None,
                context_idx=int(context_idx) if context_idx is not None else None,
                intent_families_idx=int(intent_families_idx) if intent_families_idx is not None else None,
                intent_phrases_idx=int(intent_phrases_idx) if intent_phrases_idx is not None else None,
                review_status_idx=int(review_status_idx) if review_status_idx is not None else None,
                generated_prompt_idx=int(prompt_idx) if prompt_idx is not None else None,
                header_row_index=idx,
            )
    raise ValueError(f"Unsupported raw sheet format: {path}")


def _parse_jsonish_list(raw: str) -> list[str] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, list):
        return [str(item).strip() for item in payload if str(item).strip()]
    if isinstance(payload, str):
        text = payload
    separators = ";" if ";" in text else ","
    items = [item.strip() for item in text.split(separators) if item.strip()]
    return items or None


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
            g1 = _clean_gate_value(row[schema.g1_idx] if len(row) > schema.g1_idx else "")
            raw_gl = (
                row[schema.guideline_tags_idx]
                if schema.guideline_tags_idx is not None and len(row) > schema.guideline_tags_idx
                else ""
            )
            raw_g2 = row[schema.g2_idx] if len(row) > schema.g2_idx else ""
            g3 = _clean_gate_value(
                row[schema.g3_idx] if schema.g3_idx is not None and len(row) > schema.g3_idx else ""
            )
            g4 = _clean_gate_value(
                row[schema.g4_idx] if schema.g4_idx is not None and len(row) > schema.g4_idx else ""
            )
            try:
                g2 = _clean_g2_values(raw_g2)
                raw_g2_all = row[schema.g2_all_idx] if schema.g2_all_idx is not None and len(row) > schema.g2_all_idx else ""
                g2_all = _clean_g2_values(raw_g2_all) if raw_g2_all.strip() else list(g2)
            except ValueError as exc:
                rejected_rows.append(
                    RejectedAuthoringRow(
                        source_file=path.name,
                        source_row=row_number,
                        topic="",
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
                continue
            rows.append(
                AuthoringRow(
                    source_row=row_number,
                    question=question,
                    topic=(row[schema.topic_idx].strip() if schema.topic_idx is not None and len(row) > schema.topic_idx else "") or "General Learning",
                    g1=g1,
                    g2=g2,
                    g2_all=g2_all,
                )
            )
    return AuthoringLoadResult(accepted_rows=rows, rejected_rows=rejected_rows)


def load_authoring_rows(path: Path = DEFAULT_SOURCE) -> list[AuthoringRow]:
    return _load_authoring_rows_with_rejections(path).accepted_rows


def expand_authoring_rows(path: Path = DEFAULT_SOURCE) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    schema = _detect_schema(path)
    source_row_map = {row_number: row for row_number, row in enumerate(_read_csv_rows(path), start=1)}
    for item_index, row in enumerate(load_authoring_rows(path), start=1):
        base_id = f"sample_{item_index:03d}_{_slugify(row.question)[:32]}"
        question_normalized, _ = _normalize_training_question(row.question)
        context = ""
        intent_families, intent_phrases = _intent_fields_for_g2(row.g2_all)
        review_status = "approved"
        source_row = source_row_map.get(row.source_row)
        if source_row is not None:
            if schema.context_idx is not None and len(source_row) > schema.context_idx:
                context = (source_row[schema.context_idx] or "").strip()
            if schema.intent_families_idx is not None and len(source_row) > schema.intent_families_idx:
                parsed_families = _parse_jsonish_list(source_row[schema.intent_families_idx])
                if parsed_families is not None:
                    intent_families = parsed_families
            if schema.intent_phrases_idx is not None and len(source_row) > schema.intent_phrases_idx:
                parsed_phrases = _parse_jsonish_list(source_row[schema.intent_phrases_idx])
                if parsed_phrases is not None:
                    intent_phrases = parsed_phrases
            if schema.review_status_idx is not None and len(source_row) > schema.review_status_idx:
                review_status = (source_row[schema.review_status_idx] or "").strip() or "approved"
        normalized.append(
            {
                "sample_id": base_id,
                "question": question_normalized,
                "context": context,
                "topic": row.topic or "General Learning",
                "g1": row.g1,
                "g2": row.g2,
                "g2_all": row.g2_all,
                "intent_families": intent_families,
                "intent_phrases": intent_phrases,
                "review_status": review_status,
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


def _validation_rejected_row(row: dict[str, object], reason: str) -> dict[str, object]:
    return {
        "TOPIC": str(row.get("source", "")),
        "Question": str(row.get("question", "")),
        "GL": "",
        "G1": str(row.get("g1", "")),
        "G2": ",".join(str(item) for item in row.get("g2_all", row.get("g2", []))) if isinstance(row.get("g2_all", row.get("g2")), list) else str(row.get("g2_all", row.get("g2", ""))),
        "G3": "",
        "G4": "",
        "source_file": str(row.get("source_file", "")),
        "source_row": row.get("source_row", ""),
        "rejection_reason": reason,
    }


def split_valid_and_rejected_rows(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    accepted: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    for row in rows:
        try:
            validate_dataset_rows([row])
            accepted.append(row)
        except Exception as exc:
            rejected.append(_validation_rejected_row(row, str(exc)))
    return accepted, rejected


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
    valid_rows, validation_rejected = split_valid_and_rejected_rows(rows)
    source_rejected = collect_rejected_rows(source_paths)
    all_rejected = [*source_rejected, *validation_rejected]
    REJECTED_ROWS_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["TOPIC", "Question", "GL", "G1", "G2", "G3", "G4", "source_file", "source_row", "rejection_reason"]
    with REJECTED_ROWS_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(_csv_safe_row(row) for row in all_rejected)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as handle:
        for row in valid_rows:
            payload = {key: row[key] for key in CANONICAL_COLUMNS if key in row}
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    write_dataset_splits(valid_rows, target_path=split_target_path or DATASET_SPLITS_PATH)
    write_label_vocab(valid_rows, target_path=vocab_target_path or LABEL_VOCAB_PATH)
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
