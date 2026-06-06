from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from training.slm_classifier.codebook import parse_codebook

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
STAGING_DIR = ROOT / "data" / "staging"
PROCESSED_DIR = ROOT / "data" / "processed"
CANONICAL_DATASET = PROCESSED_DIR / "piku_gl_classifier_train"
CANONICAL_SHARD_ROWS = 25000
MANIFEST_PATH = PROCESSED_DIR / "piku_gl_classifier_manifest.json"
READINESS_REPORT_PATH = PROCESSED_DIR / "piku_gl_classifier_readiness.json"
DATASET_SPLITS_PATH = PROCESSED_DIR / "piku_gl_classifier_splits.json"
LABEL_VOCAB_PATH = PROCESSED_DIR / "piku_gl_classifier_label_vocab.json"
SUPPORTED_EXTENSIONS = {".jsonl", ".json", ".csv", ".xlsx"}
CODEBOOK = parse_codebook()
G1_VOCAB = list(CODEBOOK.g1_specs.keys())
G2_VOCAB = list(CODEBOOK.g2_specs.keys())
G2_PRIORITY = [
    "UNSAFE_SEXUAL_CONTENT",
    "GROOMING",
    "COERCIVE_CONTROL",
    "VULN_EXPLOIT",
    "SELF_HARM",
    "DANGEROUS",
    "HATE_GROUP",
    "VIOLENCE",
    "PERSONAL_DIRECTION",
    "AMBIGUOUS_RISK",
    "SAFETY_HAZARD",
    "EMOTIONAL",
    "BULLYING",
    "NEUTRAL_FACT",
    "GENERIC_INTENT",
]
FLAG_VOCAB = list(CODEBOOK.flag_mappings.keys())


@dataclass
class DatasetManifest:
    canonical_dataset: str
    pending_sources: list[str]
    ready_sources: list[str]
    staging_ready_sources: list[str]
    blocked_sources: list[str]


@dataclass
class DatasetSplitManifest:
    train_ids: list[str]
    test_ids: list[str]
    fingerprint: str


def discover_training_sources() -> DatasetManifest:
    ready_sources: list[str] = []
    pending_sources: list[str] = []
    staging_ready_sources: list[str] = []
    blocked_sources: list[str] = []
    if RAW_DIR.exists():
        for path in sorted(RAW_DIR.iterdir()):
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if path.name.startswith(".") or path.name.lower() == "gl-codebook.csv" or path.name == "normalized":
                continue
            ready_sources.append(str(path))
    if STAGING_DIR.exists():
        for path in sorted(STAGING_DIR.iterdir()):
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if path.name.startswith(".") or path.name.lower() == "gl-codebook.csv":
                continue
            checklist_path = path.with_suffix(path.suffix + ".checklist.json")
            if checklist_path.exists():
                staging_ready_sources.append(str(path))
            else:
                blocked_sources.append(str(path))
            pending_sources.append(str(path))
    return DatasetManifest(
        canonical_dataset=str(CANONICAL_DATASET),
        pending_sources=pending_sources,
        ready_sources=ready_sources,
        staging_ready_sources=staging_ready_sources,
        blocked_sources=blocked_sources,
    )


def write_manifest() -> DatasetManifest:
    manifest = discover_training_sources()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest.__dict__, indent=2), encoding="utf-8")
    return manifest


def build_input_text(row: dict[str, str]) -> str:
    return (
        "Classify the child-safety G1, G2, and flag signals.\n"
        f"Recent context: {row.get('context', '') or 'none'}\n"
        f"Question: {row['question']}"
    )


def iter_jsonl_paths(path: Path = CANONICAL_DATASET) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("part-*.jsonl"))
    return [path] if path.exists() else []


def load_jsonl_rows(path: Path = CANONICAL_DATASET) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for jsonl_path in iter_jsonl_paths(path):
        with jsonl_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def build_group_id(row: dict[str, object]) -> str:
    sample_id = str(row.get("sample_id", "")).strip()
    if sample_id:
        return hashlib.sha256(sample_id.encode("utf-8")).hexdigest()[:16]
    question = str(row.get("question", "")).strip().lower()
    source_file = str(row.get("source_file", "")).strip().lower()
    source_row = str(row.get("source_row", "")).strip()
    digest = hashlib.sha256(f"{source_file}|{source_row}|{question}".encode("utf-8")).hexdigest()[:16]
    return digest


def dataset_fingerprint(rows: list[dict[str, object]]) -> str:
    payload = [
        {
            "sample_id": row.get("sample_id"),
            "question": row.get("question"),
            "context": row.get("context"),
            "g1": row.get("g1"),
            "g2": row.get("g2"),
            "flags": row.get("flags", {}),
        }
        for row in rows
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def parse_g2_values(value: object) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
    else:
        items = [item.strip() for item in str(value or "").split(",") if item.strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def primary_g2_label(values: object) -> str:
    parsed = parse_g2_values(values)
    for item in G2_PRIORITY:
        if item in parsed:
            return item
    return parsed[0] if parsed else ""


def validate_dataset_rows(rows: list[dict[str, object]]) -> None:
    for row in rows:
        if not str(row.get("question", "")).strip():
            raise ValueError(f"Missing question in row {row.get('sample_id')}")
        if "context" not in row:
            raise ValueError(f"Missing context in row {row.get('sample_id')}")
        if str(row.get("g1", "")).strip() not in G1_VOCAB:
            raise ValueError(f"Unsupported G1 label in row {row.get('sample_id')}: {row.get('g1')}")
        g2_values = parse_g2_values(row.get("g2", ""))
        if not g2_values:
            raise ValueError(f"Missing G2 labels in row {row.get('sample_id')}")
        if len(g2_values) != 1:
            raise ValueError(f"Expected one G2 label in row {row.get('sample_id')}: {g2_values}")
        unsupported = [value for value in g2_values if value not in G2_VOCAB]
        if unsupported:
            raise ValueError(f"Unsupported G2 labels in row {row.get('sample_id')}: {unsupported}")
        flags = row.get("flags", {})
        if not isinstance(flags, dict):
            raise ValueError(f"Missing flags dict in row {row.get('sample_id')}")
        unknown_flags = [key for key in flags if str(key) not in FLAG_VOCAB]
        if unknown_flags:
            raise ValueError(f"Unknown flags in row {row.get('sample_id')}: {sorted(unknown_flags)}")
        invalid_flags = [key for key, value in flags.items() if not isinstance(value, bool)]
        if invalid_flags:
            raise ValueError(f"Non-boolean flags in row {row.get('sample_id')}: {sorted(invalid_flags)}")
        intent_families = row.get("intent_families", [])
        if intent_families is None:
            continue
        if not isinstance(intent_families, list):
            raise ValueError(f"intent_families must be a list in row {row.get('sample_id')}")
        invalid_intent_families = [item for item in intent_families if not str(item).strip()]
        if invalid_intent_families:
            raise ValueError(f"Blank intent_families entries in row {row.get('sample_id')}")
        intent_phrases = row.get("intent_phrases", [])
        if intent_phrases is None:
            continue
        if not isinstance(intent_phrases, list):
            raise ValueError(f"intent_phrases must be a list in row {row.get('sample_id')}")
        invalid_intent_phrases = [item for item in intent_phrases if not str(item).strip()]
        if invalid_intent_phrases:
            raise ValueError(f"Blank intent_phrases entries in row {row.get('sample_id')}")


def write_label_vocab(rows: list[dict[str, object]] | None = None, target_path: Path = LABEL_VOCAB_PATH) -> Path:
    intent_family_vocab: list[str] = []
    intent_phrase_vocab: list[str] = []
    seen_families: set[str] = set()
    seen_phrases: set[str] = set()
    for spec in CODEBOOK.intent_lexicon.values():
        for item in spec.families:
            normalized = str(item).strip()
            if normalized and normalized not in seen_families:
                intent_family_vocab.append(normalized)
                seen_families.add(normalized)
        for item in spec.phrases:
            normalized = str(item).strip()
            if normalized and normalized not in seen_phrases:
                intent_phrase_vocab.append(normalized)
                seen_phrases.add(normalized)
    if rows:
        for row in rows:
            for item in row.get("intent_families", []) or []:
                normalized = str(item).strip()
                if normalized and normalized not in seen_families:
                    intent_family_vocab.append(normalized)
                    seen_families.add(normalized)
            for item in row.get("intent_phrases", []) or []:
                normalized = str(item).strip()
                if normalized and normalized not in seen_phrases:
                    intent_phrase_vocab.append(normalized)
                    seen_phrases.add(normalized)
    payload = {
        "g1": G1_VOCAB,
        "g2": G2_VOCAB,
        "flags": FLAG_VOCAB,
        "intent_families": intent_family_vocab,
        "intent_phrases": intent_phrase_vocab,
        "age_bands": list(CODEBOOK.age_bands.keys()),
    }
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target_path


def _partition_groups(group_ids: list[str]) -> DatasetSplitManifest:
    ordered = sorted(group_ids)
    total = len(ordered)
    if total == 0:
        return DatasetSplitManifest(train_ids=[], test_ids=[], fingerprint="empty")
    test_count = max(1, total // 10) if total >= 3 else 1 if total >= 2 else 0
    train_count = max(total - test_count, 1)
    if train_count + test_count > total:
        overflow = train_count + test_count - total
        test_count = max(test_count - overflow, 0)
    train_ids = ordered[:train_count]
    test_ids = ordered[train_count:train_count + test_count]
    fingerprint = hashlib.sha256("|".join(ordered).encode("utf-8")).hexdigest()[:16]
    return DatasetSplitManifest(train_ids=train_ids, test_ids=test_ids, fingerprint=fingerprint)


def build_dataset_splits(rows: list[dict[str, object]]) -> DatasetSplitManifest:
    groups = sorted({build_group_id(row) for row in rows})
    return _partition_groups(groups)


def write_dataset_splits(rows: list[dict[str, object]], target_path: Path = DATASET_SPLITS_PATH) -> Path:
    split_manifest = build_dataset_splits(rows)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(split_manifest.__dict__, indent=2), encoding="utf-8")
    return target_path


def load_dataset_splits(path: Path = DATASET_SPLITS_PATH) -> DatasetSplitManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return DatasetSplitManifest(
        train_ids=list(payload.get("train_ids", [])),
        test_ids=list(payload.get("test_ids", [])),
        fingerprint=str(payload.get("fingerprint", "")),
    )


def select_rows_for_split(rows: list[dict[str, object]], split_name: str, split_manifest: DatasetSplitManifest | None = None) -> list[dict[str, object]]:
    manifest = split_manifest or load_dataset_splits()
    target_ids = {
        "train": set(manifest.train_ids),
        "test": set(manifest.test_ids),
    }.get(split_name, set())
    return [row for row in rows if build_group_id(row) in target_ids]
