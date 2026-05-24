from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.guardrails.policy_loader import load_yaml_config


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ClassifierRuntimeConfig:
    selected_backend: str
    rollout_mode: str
    model_artifact_path: Path
    label_vocab_path: Path
    gl_thresholds: dict[str, float]
    promotion_thresholds: dict[str, float]


def load_classifier_runtime_config() -> ClassifierRuntimeConfig:
    raw = load_yaml_config("classifier_backend.yaml")
    model_artifact_path = ROOT / str(raw.get("model_artifact_path", "models/piku-slm-guardrail-deberta-v3-small"))
    label_vocab_path = ROOT / str(raw.get("label_vocab_path", "models/piku-slm-guardrail-deberta-v3-small/label_vocab.json"))
    gl_thresholds_raw = raw.get("gl_thresholds", {})
    promotion_thresholds_raw = raw.get("promotion_thresholds", {})
    return ClassifierRuntimeConfig(
        selected_backend=str(raw.get("selected_backend", "heuristic")),
        rollout_mode=str(raw.get("rollout_mode", "shadow")),
        model_artifact_path=model_artifact_path,
        label_vocab_path=label_vocab_path,
        gl_thresholds={str(key): float(value) for key, value in gl_thresholds_raw.items()},
        promotion_thresholds={str(key): float(value) for key, value in promotion_thresholds_raw.items()},
    )
