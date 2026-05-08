from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from training.slm_classifier.codebook import label_columns

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CANONICAL_DATASET = PROCESSED_DIR / "piku_gl_classifier_train.jsonl"
MANIFEST_PATH = PROCESSED_DIR / "piku_gl_classifier_manifest.json"
SUPPORTED_EXTENSIONS = {".jsonl", ".json", ".csv", ".xlsx"}
GL_COLUMNS = label_columns()


@dataclass
class DatasetManifest:
    canonical_dataset: str
    pending_sources: list[str]
    ready_sources: list[str]


def discover_training_sources() -> DatasetManifest:
    ready_sources: list[str] = []
    pending_sources: list[str] = []
    if RAW_DIR.exists():
        for path in sorted(RAW_DIR.iterdir()):
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
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
