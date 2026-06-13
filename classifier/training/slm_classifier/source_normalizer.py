from __future__ import annotations

import ast
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.guardrails.runtime_contracts import G2_ALIAS_MAP
from training.slm_classifier.data_pipeline import (
    CANONICAL_DATASET,
    CANONICAL_SHARD_ROWS,
    DATASET_SPLITS_PATH,
    G2_VOCAB,
    TRAINING_EXCLUDED_G2,
    FLAG_VOCAB,
    LABEL_VOCAB_PATH,
    CODEBOOK,
    primary_g2_label,
    iter_jsonl_paths,
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
QUESTION_HEADER_CANDIDATES = ("question", "questions", "prompt", "query", "user_input", "input_text")
G1_HEADER_CANDIDATES = ("g1", "g_1", "g1_lov_id")
G2_HEADER_CANDIDATES = ("g2", "g_2", "g2_lov_id")
CONTEXT_HEADER_CANDIDATES = ("context", "recent_context")
FLAGS_HEADER_CANDIDATES = ("flags",)
INTENT_FAMILIES_HEADER_CANDIDATES = ("intent_families", "intent_family", "intentfamily", "intentfamilies")
INTENT_PHRASES_HEADER_CANDIDATES = ("intent_phrases", "intent_phrase", "intentphrase", "intentphrases")
CANONICAL_COLUMNS = [
    "sample_id",
    "question",
    "context",
    "g1",
    "g2",
    "flags",
    "intent_families",
    "intent_families_present",
    "intent_phrases",
    "intent_phrases_present",
]

IGNORED_LEGACY_SOURCE_FLAGS = {"has_personal_direction"}
LEGACY_FLAG_ALIASES = {
    "has_subsatance_use_concern": "has_substance_use_concern",
}

@dataclass
class AuthoringRow:
    source_row: int
    question: str
    g1: str
    g2: list[str]
    flags: dict[str, bool]
    intent_families: list[str]
    intent_families_present: bool
    intent_phrases: list[str]
    intent_phrases_present: bool


@dataclass
class SheetSchema:
    question_idx: int
    g1_idx: int
    g2_idx: int
    context_idx: int | None = None
    flags_idx: int | None = None
    intent_families_idx: int | None = None
    intent_phrases_idx: int | None = None
    header_row_index: int = 0


@dataclass
class RejectedAuthoringRow:
    source_file: str
    source_row: int
    question: str
    g1: str
    g2: str
    rejection_reason: str


@dataclass
class AuthoringLoadResult:
    accepted_rows: list[AuthoringRow]
    rejected_rows: list[RejectedAuthoringRow]


@dataclass
class NormalizationAudit:
    total_rows: int = 0
    g2_changed_rows: int = 0
    flags_changed_rows: int = 0


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
    if value:
        value = value.strip("\"'")
    aliases = {
        "BLOCK + ESCALATE": "BLOCK_ESCALATE",
        "BLOCK (Hard)": "BLOCK_HARD",
        "TRANSFORM (hold)": "TRANSFORM_HOLD",
    }
    return aliases.get(value, value)


def _clean_g2_values(raw: str, *, first_only: bool = False) -> list[str]:
    value = _clean_gate_value(raw)
    parsed_json = None
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed_json = json.loads(value)
        except json.JSONDecodeError:
            try:
                parsed_json = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                parsed_json = None
    if isinstance(parsed_json, list):
        parts = [G2_ALIAS_MAP.get(str(item).strip(), str(item).strip()) for item in parsed_json if str(item).strip()]
    elif "," in value or ";" in value:
        separator = ";" if ";" in value and "," not in value else ","
        parts = [G2_ALIAS_MAP.get(item.strip(), item.strip()) for item in value.split(separator) if item.strip()]
    else:
        value = G2_ALIAS_MAP.get(value, value)
        if value in TRAINING_EXCLUDED_G2:
            raise ValueError(f"G2 LOV is excluded from training normalization: {value}")
        if value and value not in G2_VOCAB:
            raise ValueError(f"Unsupported G2 LOV in source data: {value}")
        return [value] if value else []
    excluded = [item for item in parts if item in TRAINING_EXCLUDED_G2]
    if excluded:
        raise ValueError(f"G2 LOVs are excluded from training normalization: {', '.join(sorted(dict.fromkeys(excluded)))}")
    unsupported = [item for item in parts if item not in G2_VOCAB]
    if unsupported:
        raise ValueError(f"Unsupported G2 LOVs in source data: {', '.join(sorted(dict.fromkeys(unsupported)))}")
    cleaned = list(dict.fromkeys(parts))
    if first_only:
        return cleaned[:1]
    return cleaned


def _normalize_training_question(question: str) -> tuple[str, list[str]]:
    collapsed = " ".join(question.strip().split())
    notes: list[str] = []
    if collapsed != question:
        notes.append("collapsed repeated whitespace")
    return collapsed, notes


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
        question_idx = _find_header_index(row, QUESTION_HEADER_CANDIDATES)
        g1_idx = _find_header_index(row, G1_HEADER_CANDIDATES)
        g2_idx = _find_header_index(row, G2_HEADER_CANDIDATES)
        context_idx = _find_header_index(row, CONTEXT_HEADER_CANDIDATES)
        flags_idx = _find_header_index(row, FLAGS_HEADER_CANDIDATES)
        intent_families_idx = _find_header_index(row, INTENT_FAMILIES_HEADER_CANDIDATES)
        intent_phrases_idx = _find_header_index(row, INTENT_PHRASES_HEADER_CANDIDATES)
        if None not in {question_idx, g1_idx, g2_idx}:
            return SheetSchema(
                question_idx=int(question_idx),
                g1_idx=int(g1_idx),
                g2_idx=int(g2_idx),
                context_idx=int(context_idx) if context_idx is not None else None,
                flags_idx=int(flags_idx) if flags_idx is not None else None,
                intent_families_idx=int(intent_families_idx) if intent_families_idx is not None else None,
                intent_phrases_idx=int(intent_phrases_idx) if intent_phrases_idx is not None else None,
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


def _default_flags() -> dict[str, bool]:
    return {flag: False for flag in FLAG_VOCAB}


def _resolve_intent_families(g2_values: list[str], raw_intent_families: list[str] | None) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for g2_value in g2_values:
        spec = CODEBOOK.intent_lexicon.get(str(g2_value).strip())
        if spec:
            for family in spec.families:
                normalized = str(family).strip()
                if normalized and normalized not in seen:
                    resolved.append(normalized)
                    seen.add(normalized)
    for family in raw_intent_families or []:
        normalized = str(family).strip()
        if normalized and normalized not in seen:
            resolved.append(normalized)
            seen.add(normalized)
    return resolved


def _resolve_intent_phrases(g2_values: list[str], raw_intent_phrases: list[str] | None) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for g2_value in g2_values:
        spec = CODEBOOK.intent_lexicon.get(str(g2_value).strip())
        if spec:
            for phrase in spec.phrases:
                normalized = str(phrase).strip()
                if normalized and normalized not in seen:
                    resolved.append(normalized)
                    seen.add(normalized)
    for phrase in raw_intent_phrases or []:
        normalized = str(phrase).strip()
        if normalized and normalized not in seen:
            resolved.append(normalized)
            seen.add(normalized)
    return resolved


def _normalize_g2_and_flags(g2_values: list[str], flags: dict[str, bool]) -> tuple[list[str], dict[str, bool]]:
    normalized_flags = {
        flag: bool(flags.get(flag, False))
        for flag in FLAG_VOCAB
    }
    primary = primary_g2_label(g2_values)
    return ([primary] if primary else []), normalized_flags


def _audit_normalization_change(
    original_g2: list[str],
    original_flags: dict[str, bool],
    normalized_g2: list[str],
    normalized_flags: dict[str, bool],
) -> tuple[bool, bool]:
    original_primary = primary_g2_label(original_g2)
    normalized_primary = primary_g2_label(normalized_g2)
    g2_changed = original_primary != normalized_primary
    flags_changed = any(
        bool(original_flags.get(flag, False)) != bool(normalized_flags.get(flag, False))
        for flag in FLAG_VOCAB
    )
    return g2_changed, flags_changed


def _parse_flags(raw: str) -> dict[str, bool]:
    text = (raw or "").strip()
    if not text:
        return _default_flags()
    if "=" in text:
        payload = {}
        for item in text.split(";"):
            key, separator, raw_value = item.partition("=")
            if not separator or raw_value.strip().lower() not in {"true", "false"}:
                raise ValueError(f"Invalid flags key/value item: {item}")
            payload[key.strip()] = raw_value.strip().lower() == "true"
    else:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            try:
                payload = ast.literal_eval(text)
            except (ValueError, SyntaxError) as fallback_exc:
                raise ValueError(f"Invalid flags JSON: {exc}") from fallback_exc
    if not isinstance(payload, dict):
        raise ValueError("Flags must be a JSON object.")
    payload = {
        LEGACY_FLAG_ALIASES.get(str(key), str(key)): value
        for key, value in payload.items()
    }
    unknown = [str(key) for key in payload if str(key) not in FLAG_VOCAB and str(key) not in IGNORED_LEGACY_SOURCE_FLAGS]
    if unknown:
        raise ValueError(f"Unknown flags in source data: {', '.join(sorted(dict.fromkeys(unknown)))}")
    normalized = _default_flags()
    for key, value in payload.items():
        if not isinstance(value, bool):
            raise ValueError(f"Flag '{key}' must be boolean.")
        if str(key) in normalized:
            normalized[str(key)] = value
    return normalized


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
            raw_g2 = row[schema.g2_idx] if len(row) > schema.g2_idx else ""
            try:
                g2 = _clean_g2_values(raw_g2, first_only=True)
                raw_flags = row[schema.flags_idx] if schema.flags_idx is not None and len(row) > schema.flags_idx else ""
                flags = _parse_flags(raw_flags)
                g2, flags = _normalize_g2_and_flags(list(g2), flags)
                raw_intent_families = (
                    row[schema.intent_families_idx]
                    if schema.intent_families_idx is not None and len(row) > schema.intent_families_idx
                    else ""
                )
                parsed_intent_families = _parse_jsonish_list(raw_intent_families) or []
                intent_families = _resolve_intent_families(g2, parsed_intent_families)
                intent_families_present = bool(intent_families) or schema.intent_families_idx is not None
                raw_intent_phrases = (
                    row[schema.intent_phrases_idx]
                    if schema.intent_phrases_idx is not None and len(row) > schema.intent_phrases_idx
                    else ""
                )
                parsed_intent_phrases = _parse_jsonish_list(raw_intent_phrases) or []
                intent_phrases = _resolve_intent_phrases(g2, parsed_intent_phrases)
                intent_phrases_present = bool(intent_phrases) or schema.intent_phrases_idx is not None
            except ValueError as exc:
                rejected_rows.append(
                    RejectedAuthoringRow(
                        source_file=path.name,
                        source_row=row_number,
                        question=question,
                        g1=g1,
                        g2=raw_g2.strip(),
                        rejection_reason=str(exc),
                    )
                )
                continue
            if not any((g1, g2)):
                continue
            rows.append(
                AuthoringRow(
                    source_row=row_number,
                    question=question,
                    g1=g1,
                    g2=g2,
                    flags=flags,
                    intent_families=intent_families,
                    intent_families_present=intent_families_present,
                    intent_phrases=intent_phrases,
                    intent_phrases_present=intent_phrases_present,
                )
            )
    return AuthoringLoadResult(accepted_rows=rows, rejected_rows=rejected_rows)


def load_authoring_rows(path: Path = DEFAULT_SOURCE) -> list[AuthoringRow]:
    return _load_authoring_rows_with_rejections(path).accepted_rows


def collect_normalization_audit(paths: list[Path] | None = None) -> NormalizationAudit:
    source_paths = paths or discover_source_files()
    audit = NormalizationAudit()
    for path in source_paths:
        schema = _detect_schema(path)
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            for row_number, row in enumerate(reader, start=1):
                if row_number <= schema.header_row_index + 1:
                    continue
                question = _clean_question_text(row[schema.question_idx] if len(row) > schema.question_idx else "")
                if not question:
                    continue
                raw_g2 = row[schema.g2_idx] if len(row) > schema.g2_idx else ""
                raw_flags = row[schema.flags_idx] if schema.flags_idx is not None and len(row) > schema.flags_idx else ""
                try:
                    parsed_g2 = _clean_g2_values(raw_g2, first_only=True)
                    parsed_flags = _parse_flags(raw_flags)
                    normalized_g2, normalized_flags = _normalize_g2_and_flags(list(parsed_g2), dict(parsed_flags))
                except ValueError:
                    continue
                audit.total_rows += 1
                g2_changed, flags_changed = _audit_normalization_change(parsed_g2, parsed_flags, normalized_g2, normalized_flags)
                audit.g2_changed_rows += int(g2_changed)
                audit.flags_changed_rows += int(flags_changed)
    return audit


def expand_authoring_rows(path: Path = DEFAULT_SOURCE) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    schema = _detect_schema(path)
    source_row_map = {row_number: row for row_number, row in enumerate(_read_csv_rows(path), start=1)}
    for item_index, row in enumerate(load_authoring_rows(path), start=1):
        base_id = f"{_slugify(path.stem)}_{row.source_row:06d}_{_slugify(row.question)[:32]}"
        question_normalized, _ = _normalize_training_question(row.question)
        context = ""
        source_row = source_row_map.get(row.source_row)
        if source_row is not None:
            if schema.context_idx is not None and len(source_row) > schema.context_idx:
                context = (source_row[schema.context_idx] or "").strip()
        normalized.append(
            {
                "sample_id": base_id,
                "question": question_normalized,
                "context": context,
                "g1": row.g1,
                "g2": row.g2,
                "flags": row.flags,
                "intent_families": row.intent_families,
                "intent_families_present": row.intent_families_present,
                "intent_phrases": row.intent_phrases,
                "intent_phrases_present": row.intent_phrases_present,
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
        "G1": str(row.get("g1", "")),
        "G2": ",".join(str(item) for item in row.get("g2", [])) if isinstance(row.get("g2"), list) else str(row.get("g2", "")),
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
                    "TOPIC": "",
                    "Question": row.question,
                    "G1": row.g1,
                    "G2": row.g2,
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
    fieldnames = ["TOPIC", "Question", "G1", "G2", "source_file", "source_row", "rejection_reason"]
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
    normalization_audit = collect_normalization_audit(source_paths)
    rows = expand_all_sources(source_paths)
    valid_rows, validation_rejected = split_valid_and_rejected_rows(rows)
    source_rejected = collect_rejected_rows(source_paths)
    all_rejected = [*source_rejected, *validation_rejected]
    REJECTED_ROWS_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["TOPIC", "Question", "G1", "G2", "source_file", "source_row", "rejection_reason"]
    with REJECTED_ROWS_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(_csv_safe_row(row) for row in all_rejected)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    payloads = [
        {key: row[key] for key in CANONICAL_COLUMNS if key in row}
        for row in valid_rows
    ]
    if target_path == CANONICAL_DATASET:
        target_path.mkdir(parents=True, exist_ok=True)
        for shard_path in iter_jsonl_paths(target_path):
            shard_path.unlink()
        for shard_index, offset in enumerate(range(0, len(payloads), CANONICAL_SHARD_ROWS)):
            shard_path = target_path / f"part-{shard_index:03d}.jsonl"
            with shard_path.open("w", encoding="utf-8") as handle:
                for payload in payloads[offset:offset + CANONICAL_SHARD_ROWS]:
                    handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    else:
        with target_path.open("w", encoding="utf-8") as handle:
            for payload in payloads:
                handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    write_dataset_splits(valid_rows, target_path=split_target_path or DATASET_SPLITS_PATH)
    write_label_vocab(valid_rows, target_path=vocab_target_path or LABEL_VOCAB_PATH)
    print(
        "Canonical normalization summary: "
        f"rows={normalization_audit.total_rows} "
        f"g2_changed_rows={normalization_audit.g2_changed_rows} "
        f"flags_changed_rows={normalization_audit.flags_changed_rows}"
    )
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
