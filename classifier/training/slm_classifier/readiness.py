from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from training.slm_classifier.data_pipeline import RAW_DIR, READINESS_REPORT_PATH, STAGING_DIR, SUPPORTED_EXTENSIONS, primary_g2_label
from training.slm_classifier.source_normalizer import (
    _clean_g2_values,
    _default_flags,
    _detect_schema,
    _find_header_index,
    _load_authoring_rows_with_rejections,
    _parse_flags,
    _slugify,
)


QUESTION_HEADER_CANDIDATES = ("question", "questions", "prompt", "query")
G1_HEADER_CANDIDATES = ("g1", "g_1")
G2_HEADER_CANDIDATES = ("g2", "g_2")
FLAGS_HEADER_CANDIDATES = ("flags",)

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
class ChecklistItem:
    id: str
    passed: bool
    detail: str


@dataclass
class SourceReadinessAssessment:
    path: str
    ready: bool
    checklist: list[ChecklistItem]
    accepted_rows: int
    rejected_rows: int
    target_path: str


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def _header_indexes(fieldnames: list[str]) -> dict[str, int | None]:
    return {
        "question": _find_header_index(fieldnames, QUESTION_HEADER_CANDIDATES),
        "g1": _find_header_index(fieldnames, G1_HEADER_CANDIDATES),
        "g2": _find_header_index(fieldnames, G2_HEADER_CANDIDATES),
        "flags": _find_header_index(fieldnames, FLAGS_HEADER_CANDIDATES),
    }


def _ensure_required_columns(fieldnames: list[str]) -> list[str]:
    updated = list(fieldnames)
    normalized = [_slugify(name) for name in updated]
    for required_name, candidates in (
        ("Question", QUESTION_HEADER_CANDIDATES),
        ("G1", G1_HEADER_CANDIDATES),
        ("G2", G2_HEADER_CANDIDATES),
        ("Flags", FLAGS_HEADER_CANDIDATES),
    ):
        if not any(cell in candidates for cell in normalized):
            updated.append(required_name)
            normalized.append(_slugify(required_name))
    return updated


def _json_all_flags(flags: dict[str, bool]) -> str:
    return json.dumps(flags, sort_keys=True)


def _normalize_row_flags(g2_values: list[str], flags: dict[str, bool]) -> tuple[list[str], dict[str, bool]]:
    normalized_flags = _default_flags()
    for key, value in flags.items():
        if key in normalized_flags and value is True:
            normalized_flags[key] = True

    for g2 in g2_values:
        for flag_name in ALWAYS_FLAGS_BY_G2.get(g2, set()):
            normalized_flags[flag_name] = True

    for flag_name, g2 in FLAG_TO_G2.items():
        if normalized_flags.get(flag_name, False) and g2 not in g2_values:
            g2_values.append(g2)

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


def _rewrite_source_rows(source_path: Path) -> tuple[bool, list[str], list[dict[str, str]]]:
    fieldnames, rows = _read_csv(source_path)
    if not fieldnames:
        return False, [], []
    updated_fieldnames = _ensure_required_columns(fieldnames)
    indexes = _header_indexes(updated_fieldnames)
    g2_name = updated_fieldnames[indexes["g2"]] if indexes["g2"] is not None else "G2"
    flags_name = updated_fieldnames[indexes["flags"]] if indexes["flags"] is not None else "Flags"

    changed = False
    rewritten_rows: list[dict[str, str]] = []
    for row in rows:
        current = {key: row.get(key, "") for key in updated_fieldnames}
        raw_g2 = current.get(g2_name, "")
        raw_flags = current.get(flags_name, "")
        try:
            g2_values = _clean_g2_values(raw_g2, first_only=False) if str(raw_g2).strip() else []
        except Exception:
            g2_values = []
        try:
            flags = _parse_flags(raw_flags)
        except Exception:
            flags = _default_flags()
        fixed_g2_values, fixed_flags = _normalize_row_flags(list(g2_values), flags)
        fixed_g2 = primary_g2_label(fixed_g2_values) if fixed_g2_values else ""
        fixed_flags_text = _json_all_flags(fixed_flags)

        if current.get(g2_name, "") != fixed_g2:
            current[g2_name] = fixed_g2
            changed = True
        if current.get(flags_name, "") != fixed_flags_text:
            current[flags_name] = fixed_flags_text
            changed = True
        rewritten_rows.append(current)

    if updated_fieldnames != fieldnames:
        changed = True
    return changed, updated_fieldnames, rewritten_rows


def needs_fix(source_path: Path) -> bool:
    changed, _, _ = _rewrite_source_rows(source_path)
    return changed


def fix_source_file(source_path: Path) -> bool:
    changed, updated_fieldnames, rewritten_rows = _rewrite_source_rows(source_path)
    if changed:
        with source_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=updated_fieldnames)
            writer.writeheader()
            writer.writerows(rewritten_rows)
    return changed


def fix_staging_sources(staging_dir: Path = STAGING_DIR) -> list[Path]:
    fixed_paths: list[Path] = []
    for path in _supported_source_files(staging_dir):
        if fix_source_file(path):
            fixed_paths.append(path)
    return fixed_paths


def _checklist_path(source_path: Path) -> Path:
    return source_path.with_suffix(source_path.suffix + ".checklist.json")


def _is_checklist_artifact(path: Path) -> bool:
    return ".checklist.json" in path.name


def _supported_source_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [
        path
        for path in sorted(root.iterdir())
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
        and not path.name.startswith(".")
        and path.name.lower() != "gl-codebook.csv"
        and not _is_checklist_artifact(path)
    ]


def _cleanup_checklist_artifacts(root: Path) -> int:
    if not root.exists():
        return 0
    removed = 0
    for path in root.iterdir():
        if path.is_file() and _is_checklist_artifact(path):
            path.unlink()
            removed += 1
    return removed


def assess_source_file(source_path: Path, raw_dir: Path = RAW_DIR) -> SourceReadinessAssessment:
    checklist: list[ChecklistItem] = []
    target_path = raw_dir / source_path.name
    checklist.append(
        ChecklistItem(
            id="supported_extension",
            passed=source_path.suffix.lower() in SUPPORTED_EXTENSIONS,
            detail=f"extension={source_path.suffix.lower() or '(none)'}",
        )
    )
    checklist.append(
        ChecklistItem(
            id="target_not_present",
            passed=not target_path.exists(),
            detail=f"target={target_path}",
        )
    )
    try:
        schema = _detect_schema(source_path)
        checklist.append(
            ChecklistItem(
                id="schema_detected",
                passed=True,
                detail=f"question_idx={schema.question_idx}, g1_idx={schema.g1_idx}, g2_idx={schema.g2_idx}",
            )
        )
    except Exception as exc:
        checklist.append(ChecklistItem(id="schema_detected", passed=False, detail=str(exc)))
        return SourceReadinessAssessment(
            path=str(source_path),
            ready=False,
            checklist=checklist,
            accepted_rows=0,
            rejected_rows=0,
            target_path=str(target_path),
        )

    try:
        result = _load_authoring_rows_with_rejections(source_path)
        checklist.append(
            ChecklistItem(
                id="has_accepted_rows",
                passed=len(result.accepted_rows) > 0,
                detail=f"accepted_rows={len(result.accepted_rows)}",
            )
        )
        checklist.append(
            ChecklistItem(
                id="no_rejected_rows",
                passed=len(result.rejected_rows) == 0,
                detail=f"rejected_rows={len(result.rejected_rows)}",
            )
        )
        requires_fix = needs_fix(source_path)
        checklist.append(
            ChecklistItem(
                id="flags_and_labels_consistent",
                passed=not requires_fix,
                detail="no in-place fixes required" if not requires_fix else "scan found fixable row-level mismatches",
            )
        )
    except Exception as exc:
        checklist.append(ChecklistItem(id="authoring_rows_loadable", passed=False, detail=str(exc)))
        return SourceReadinessAssessment(
            path=str(source_path),
            ready=False,
            checklist=checklist,
            accepted_rows=0,
            rejected_rows=0,
            target_path=str(target_path),
        )

    ready = all(item.passed for item in checklist)
    return SourceReadinessAssessment(
        path=str(source_path),
        ready=ready,
        checklist=checklist,
        accepted_rows=len(result.accepted_rows),
        rejected_rows=len(result.rejected_rows),
        target_path=str(target_path),
    )


def write_checklist(source_path: Path, raw_dir: Path = RAW_DIR) -> SourceReadinessAssessment:
    assessment = assess_source_file(source_path, raw_dir=raw_dir)
    checklist_path = _checklist_path(source_path)
    payload = asdict(assessment)
    checklist_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return assessment


def scan_staging_sources(staging_dir: Path = STAGING_DIR, raw_dir: Path = RAW_DIR) -> list[SourceReadinessAssessment]:
    _cleanup_checklist_artifacts(staging_dir)
    assessments = [write_checklist(path, raw_dir=raw_dir) for path in _supported_source_files(staging_dir)]
    report_payload: dict[str, Any] = {
        "staging_dir": str(staging_dir),
        "raw_dir": str(raw_dir),
        "sources": [asdict(item) for item in assessments],
        "ready_count": sum(1 for item in assessments if item.ready),
        "blocked_count": sum(1 for item in assessments if not item.ready),
    }
    READINESS_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    READINESS_REPORT_PATH.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    return assessments


def promote_ready_sources(staging_dir: Path = STAGING_DIR, raw_dir: Path = RAW_DIR) -> list[Path]:
    promoted: list[Path] = []
    assessments = scan_staging_sources(staging_dir=staging_dir, raw_dir=raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for assessment in assessments:
        if not assessment.ready:
            continue
        source_path = Path(assessment.path)
        target_path = raw_dir / source_path.name
        shutil.move(str(source_path), str(target_path))
        checklist_path = _checklist_path(source_path)
        if checklist_path.exists():
            checklist_path.unlink()
        promoted.append(target_path)
    return promoted


def _print_assessment(assessment: SourceReadinessAssessment) -> None:
    status = "READY" if assessment.ready else "BLOCKED"
    print(
        f"[{status}] {Path(assessment.path).name} "
        f"(accepted={assessment.accepted_rows}, rejected={assessment.rejected_rows})"
    )
    for item in assessment.checklist:
        marker = "PASS" if item.passed else "FAIL"
        print(f"  - {marker} {item.id}: {item.detail}")


def _run_scan(staging_dir: Path, raw_dir: Path) -> int:
    print(f"Scanning staged sources in {staging_dir}")
    assessments = scan_staging_sources(staging_dir=staging_dir, raw_dir=raw_dir)
    if not assessments:
        print("No staged source files found.")
        print(f"Readiness report written to {READINESS_REPORT_PATH}")
        return 0
    for assessment in assessments:
        _print_assessment(assessment)
    ready_count = sum(1 for item in assessments if item.ready)
    blocked_count = sum(1 for item in assessments if not item.ready)
    print(f"Summary: ready={ready_count} blocked={blocked_count}")
    print(f"Readiness report written to {READINESS_REPORT_PATH}")
    return 0 if blocked_count == 0 else 1


def _run_promote(staging_dir: Path, raw_dir: Path) -> int:
    print(f"Promoting ready staged sources from {staging_dir} to {raw_dir}")
    assessments = scan_staging_sources(staging_dir=staging_dir, raw_dir=raw_dir)
    if not assessments:
        print("No staged source files found. Nothing to promote.")
        print(f"Readiness report written to {READINESS_REPORT_PATH}")
        return 0
    for assessment in assessments:
        _print_assessment(assessment)
    promoted = promote_ready_sources(staging_dir=staging_dir, raw_dir=raw_dir)
    if promoted:
        print("Promoted files:")
        for path in promoted:
            print(f"  - {path}")
    else:
        print("No files were promoted.")
    ready_count = sum(1 for item in assessments if item.ready)
    blocked_count = sum(1 for item in assessments if not item.ready)
    print(f"Summary: ready={ready_count} blocked={blocked_count} promoted={len(promoted)}")
    return 0 if promoted else (1 if blocked_count else 0)


def _run_fix(staging_dir: Path) -> int:
    print(f"Fixing staged sources in {staging_dir}")
    staged_files = _supported_source_files(staging_dir)
    if not staged_files:
        print("No staged source files found. Nothing to fix.")
        return 0
    fixed_paths = fix_staging_sources(staging_dir=staging_dir)
    if fixed_paths:
        print("Rewritten files:")
        for path in fixed_paths:
            print(f"  - {path}")
    else:
        print("No file content changes were needed.")
    print("Re-running readiness scan after fixes.")
    return _run_scan(staging_dir=staging_dir, raw_dir=RAW_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Training data readiness gate for staged classifier sources.")
    parser.add_argument("command", choices=["scan", "fix", "promote"])
    parser.add_argument("--staging-dir", default=str(STAGING_DIR))
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    args = parser.parse_args()

    staging_dir = Path(args.staging_dir)
    raw_dir = Path(args.raw_dir)

    if args.command == "scan":
        raise SystemExit(_run_scan(staging_dir=staging_dir, raw_dir=raw_dir))
    if args.command == "fix":
        raise SystemExit(_run_fix(staging_dir=staging_dir))
    raise SystemExit(_run_promote(staging_dir=staging_dir, raw_dir=raw_dir))


if __name__ == "__main__":
    main()
