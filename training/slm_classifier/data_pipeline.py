from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from training.slm_classifier.codebook import label_columns, parse_codebook

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CANONICAL_DATASET = PROCESSED_DIR / "piku_gl_classifier_train.jsonl"
MANIFEST_PATH = PROCESSED_DIR / "piku_gl_classifier_manifest.json"
DATASET_SPLITS_PATH = PROCESSED_DIR / "piku_gl_classifier_splits.json"
LABEL_VOCAB_PATH = PROCESSED_DIR / "piku_gl_classifier_label_vocab.json"
SUPPORTED_EXTENSIONS = {".jsonl", ".json", ".csv", ".xlsx"}
GL_COLUMNS = label_columns()
CODEBOOK = parse_codebook()
AGE_BANDS = tuple(CODEBOOK.age_bands.keys())
G1_VOCAB = ["FACT", "BELIEF", "DEATH_GRIEF", "VIOLENCE", "SCIENCE", "TECHNOLOGY", "SAFETY_HAZARD", "CIVIC_LAW", "GENERIC"]
G2_VOCAB = list(CODEBOOK.g2_specs.keys())
G3_VOCAB = ["SV0", "SV1", "SV2", "SV3", "SV4"]
G4_VOCAB = ["ALLOW", "TRANSFORM", "TRANSFORM_HOLD", "BLOCK", "BLOCK_HARD", "BLOCK_ESCALATE"]


@dataclass
class DatasetManifest:
    canonical_dataset: str
    pending_sources: list[str]
    ready_sources: list[str]


@dataclass
class DatasetSplitManifest:
    train_ids: list[str]
    dev_ids: list[str]
    test_ids: list[str]
    fingerprint: str


def discover_training_sources() -> DatasetManifest:
    ready_sources: list[str] = []
    pending_sources: list[str] = []
    if RAW_DIR.exists():
        for path in sorted(RAW_DIR.iterdir()):
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if path.name.startswith(".") or path.name.lower() == "gl-codebook.csv":
                continue
            if path.name.startswith("trained_"):
                ready_sources.append(str(path))
            else:
                pending_sources.append(str(path))
    return DatasetManifest(
        canonical_dataset=str(CANONICAL_DATASET),
        pending_sources=pending_sources,
        ready_sources=ready_sources,
    )


def write_manifest() -> DatasetManifest:
    manifest = discover_training_sources()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest.__dict__, indent=2), encoding="utf-8")
    return manifest


def build_input_text(row: dict[str, str]) -> str:
    return (
        "Classify the child-safety guideline signals.\n"
        f"Age band: {row['age_band']}\n"
        f"Language: {row.get('language', 'en')}\n"
        f"Recent context: {row.get('recent_context', 'none')}\n"
        f"Question: {row['question']}"
    )


def build_label_vector(row: dict[str, str | int | float]) -> list[float]:
    return [float(row[column]) for column in GL_COLUMNS]


def build_group_id(row: dict[str, object]) -> str:
    sample_id = str(row.get("sample_id", "")).strip()
    if sample_id:
        suffixes = tuple(f"_{band.replace('-', '_')}" for band in AGE_BANDS)
        for suffix in suffixes:
            if sample_id.endswith(suffix):
                return hashlib.sha256(sample_id[: -len(suffix)].encode("utf-8")).hexdigest()[:16]
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
            "age_band": row.get("age_band"),
            "gl": [row.get(column) for column in GL_COLUMNS],
            "g1": row.get("g1"),
            "g2": row.get("g2"),
            "g3": row.get("g3"),
            "g4": row.get("g4"),
        }
        for row in rows
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def validate_dataset_rows(rows: list[dict[str, object]]) -> None:
    supported_gls = set(GL_COLUMNS)
    for row in rows:
        missing = supported_gls - set(row.keys())
        if missing:
            raise ValueError(f"Missing GL columns for row {row.get('sample_id')}: {sorted(missing)}")
        for column in GL_COLUMNS:
            value = row.get(column)
            if int(value) not in {0, 1}:
                raise ValueError(f"Expected binary label for {column} in row {row.get('sample_id')}: {value}")
        if str(row.get("age_band", "")).strip() not in AGE_BANDS:
            raise ValueError(f"Unsupported age band in row {row.get('sample_id')}: {row.get('age_band')}")
        if str(row.get("g1", "")).strip() not in G1_VOCAB:
            raise ValueError(f"Unsupported G1 label in row {row.get('sample_id')}: {row.get('g1')}")
        if str(row.get("g2", "")).strip() not in G2_VOCAB:
            raise ValueError(f"Unsupported G2 label in row {row.get('sample_id')}: {row.get('g2')}")
        if str(row.get("g3", "")).strip() not in G3_VOCAB:
            raise ValueError(f"Unsupported G3 label in row {row.get('sample_id')}: {row.get('g3')}")
        if str(row.get("g4", "")).strip() not in G4_VOCAB:
            raise ValueError(f"Unsupported G4 label in row {row.get('sample_id')}: {row.get('g4')}")


def write_label_vocab(target_path: Path = LABEL_VOCAB_PATH) -> Path:
    payload = {
        "gl_columns": GL_COLUMNS,
        "g1": G1_VOCAB,
        "g2": G2_VOCAB,
        "g3": G3_VOCAB,
        "g4": G4_VOCAB,
        "age_bands": list(AGE_BANDS),
    }
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target_path


def _partition_groups(group_ids: list[str]) -> DatasetSplitManifest:
    ordered = sorted(group_ids)
    total = len(ordered)
    if total == 0:
        return DatasetSplitManifest(train_ids=[], dev_ids=[], test_ids=[], fingerprint="empty")
    dev_count = max(1, total // 10) if total >= 3 else 1 if total >= 2 else 0
    test_count = max(1, total // 10) if total >= 4 else 1 if total >= 3 else 0
    train_count = max(total - dev_count - test_count, 1)
    if train_count + dev_count + test_count > total:
        overflow = train_count + dev_count + test_count - total
        if dev_count >= overflow:
            dev_count -= overflow
        else:
            test_count = max(test_count - (overflow - dev_count), 0)
            dev_count = 0
    train_ids = ordered[:train_count]
    dev_ids = ordered[train_count:train_count + dev_count]
    test_ids = ordered[train_count + dev_count:train_count + dev_count + test_count]
    fingerprint = hashlib.sha256("|".join(ordered).encode("utf-8")).hexdigest()[:16]
    return DatasetSplitManifest(train_ids=train_ids, dev_ids=dev_ids, test_ids=test_ids, fingerprint=fingerprint)


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
        dev_ids=list(payload.get("dev_ids", [])),
        test_ids=list(payload.get("test_ids", [])),
        fingerprint=str(payload.get("fingerprint", "")),
    )


def select_rows_for_split(rows: list[dict[str, object]], split_name: str, split_manifest: DatasetSplitManifest | None = None) -> list[dict[str, object]]:
    manifest = split_manifest or load_dataset_splits()
    target_ids = {
        "train": set(manifest.train_ids),
        "dev": set(manifest.dev_ids),
        "test": set(manifest.test_ids),
    }.get(split_name, set())
    return [row for row in rows if build_group_id(row) in target_ids]
