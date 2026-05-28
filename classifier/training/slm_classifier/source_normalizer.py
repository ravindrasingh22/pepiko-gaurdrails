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
    DATASET_SPLITS_PATH,
    G2_VOCAB,
    FLAG_VOCAB,
    LABEL_VOCAB_PATH,
    CODEBOOK,
    primary_g2_label,
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
QUESTION_HEADER_CANDIDATES = ("question", "questions", "prompt", "query")
G1_HEADER_CANDIDATES = ("g1", "g_1")
G2_HEADER_CANDIDATES = ("g2", "g_2")
G3_HEADER_CANDIDATES = ("g3", "g_3")
G4_HEADER_CANDIDATES = ("g4", "g_4")
CONTEXT_HEADER_CANDIDATES = ("context", "recent_context")
GENERATED_PROMPT_HEADER_CANDIDATES = ("generated_prompt", "generatedprompt")
FLAGS_HEADER_CANDIDATES = ("flags",)
INTENT_FAMILIES_HEADER_CANDIDATES = ("intent_families", "intent_family", "intentfamily", "intentfamilies")
CANONICAL_COLUMNS = [
    "sample_id",
    "question",
    "context",
    "g1",
    "g2",
    "flags",
    "intent_families",
    "intent_families_present",
]

ALWAYS_FLAGS_BY_G2 = {
    "AMBIGUOUS_RISK": {"has_ambiguous_risk"},
    "BULLYING": {"has_bullying_involved"},
    "COERCIVE_CONTROL": {"has_coercive_control"},
    "DANGEROUS": {"has_dangerous_context"},
    "GROOMING": {"has_grooming_involved"},
    "HATE_GROUP": {"has_hate_group_language"},
    "PERSONAL_DIRECTION": {"has_personal_direction"},
    "SAFETY_HAZARD": {"has_dangerous_context", "has_safety_hazard"},
    "SELF_HARM": {"has_emotional_distress", "has_self_harm"},
    "UNSAFE_SEXUAL_CONTENT": {"has_unsafe_sexual_content"},
    "VIOLENCE": {"has_violence_possibility"},
    "VULN_EXPLOIT": {"has_vuln_exploit"},
}

FLAG_TO_G2 = {
    "has_ambiguous_risk": "AMBIGUOUS_RISK",
    "has_bullying_involved": "BULLYING",
    "has_coercive_control": "COERCIVE_CONTROL",
    "has_grooming_involved": "GROOMING",
    "has_hate_group_language": "HATE_GROUP",
    "has_personal_direction": "PERSONAL_DIRECTION",
    "has_self_harm": "SELF_HARM",
    "has_unsafe_sexual_content": "UNSAFE_SEXUAL_CONTENT",
    "has_violence_possibility": "VIOLENCE",
    "has_vuln_exploit": "VULN_EXPLOIT",
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


@dataclass
class SheetSchema:
    question_idx: int
    guideline_tags_idx: int | None
    g1_idx: int
    g2_idx: int
    g3_idx: int | None
    g4_idx: int | None
    context_idx: int | None = None
    generated_prompt_idx: int | None = None
    flags_idx: int | None = None
    intent_families_idx: int | None = None
    header_row_index: int = 0


@dataclass
class RejectedAuthoringRow:
    source_file: str
    source_row: int
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
        if value and value not in G2_VOCAB:
            raise ValueError(f"Unsupported G2 LOV in source data: {value}")
        return [value] if value else []
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
        gl_idx = _find_header_index(row, ("gl", "guideline_tags", "guidelines", "gl_tags"))
        g1_idx = _find_header_index(row, G1_HEADER_CANDIDATES)
        g2_idx = _find_header_index(row, G2_HEADER_CANDIDATES)
        g3_idx = _find_header_index(row, G3_HEADER_CANDIDATES)
        g4_idx = _find_header_index(row, G4_HEADER_CANDIDATES)
        context_idx = _find_header_index(row, CONTEXT_HEADER_CANDIDATES)
        prompt_idx = _find_header_index(row, GENERATED_PROMPT_HEADER_CANDIDATES)
        flags_idx = _find_header_index(row, FLAGS_HEADER_CANDIDATES)
        intent_families_idx = _find_header_index(row, INTENT_FAMILIES_HEADER_CANDIDATES)
        if None not in {question_idx, g1_idx, g2_idx}:
            return SheetSchema(
                question_idx=int(question_idx),
                guideline_tags_idx=int(gl_idx) if gl_idx is not None else None,
                g1_idx=int(g1_idx),
                g2_idx=int(g2_idx),
                g3_idx=int(g3_idx) if g3_idx is not None else None,
                g4_idx=int(g4_idx) if g4_idx is not None else None,
                context_idx=int(context_idx) if context_idx is not None else None,
                generated_prompt_idx=int(prompt_idx) if prompt_idx is not None else None,
                flags_idx=int(flags_idx) if flags_idx is not None else None,
                intent_families_idx=int(intent_families_idx) if intent_families_idx is not None else None,
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


def _normalize_g2_and_flags(g2_values: list[str], flags: dict[str, bool]) -> tuple[list[str], dict[str, bool]]:
    normalized_flags = _default_flags()
    for key, value in flags.items():
        if key in normalized_flags and value is True:
            normalized_flags[key] = True

    for g2 in g2_values:
        for flag_name in ALWAYS_FLAGS_BY_G2.get(g2, set()):
            normalized_flags[flag_name] = True

    for flag_name, mapped_g2 in FLAG_TO_G2.items():
        if normalized_flags.get(flag_name, False) and mapped_g2 not in g2_values:
            g2_values.append(mapped_g2)

    if normalized_flags.get("has_safety_hazard", False) and normalized_flags.get("has_dangerous_context", False):
        if "SAFETY_HAZARD" not in g2_values:
            g2_values.append("SAFETY_HAZARD")
    if normalized_flags.get("has_emotional_distress", False) and normalized_flags.get("has_self_harm", False):
        if "SELF_HARM" not in g2_values:
            g2_values.append("SELF_HARM")

    for g2 in g2_values:
        for flag_name in ALWAYS_FLAGS_BY_G2.get(g2, set()):
            normalized_flags[flag_name] = True

    deduped_g2: list[str] = []
    seen: set[str] = set()
    for value in g2_values:
        if value and value not in seen:
            deduped_g2.append(value)
            seen.add(value)
    primary = primary_g2_label(deduped_g2)
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
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        try:
            payload = ast.literal_eval(text)
        except (ValueError, SyntaxError) as fallback_exc:
            raise ValueError(f"Invalid flags JSON: {exc}") from fallback_exc
    if not isinstance(payload, dict):
        raise ValueError("Flags must be a JSON object.")
    unknown = [str(key) for key in payload if str(key) not in FLAG_VOCAB]
    if unknown:
        raise ValueError(f"Unknown flags in source data: {', '.join(sorted(dict.fromkeys(unknown)))}")
    normalized = _default_flags()
    for key, value in payload.items():
        if not isinstance(value, bool):
            raise ValueError(f"Flag '{key}' must be boolean.")
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
            except ValueError as exc:
                rejected_rows.append(
                    RejectedAuthoringRow(
                        source_file=path.name,
                        source_row=row_number,
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
                    g1=g1,
                    g2=g2,
                    flags=flags,
                    intent_families=intent_families,
                    intent_families_present=intent_families_present,
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
        base_id = f"sample_{item_index:03d}_{_slugify(row.question)[:32]}"
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
        "G2": ",".join(str(item) for item in row.get("g2", [])) if isinstance(row.get("g2"), list) else str(row.get("g2", "")),
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
                    "TOPIC": "",
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
    normalization_audit = collect_normalization_audit(source_paths)
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
