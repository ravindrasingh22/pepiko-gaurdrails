from __future__ import annotations

import importlib.util
import json
import os
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.guardrails import gate_mapper, runtime_contracts, slm_classifier as heuristic_classifier
from app.models.guardrail_decision import GuardrailDecision
from training.slm_classifier.codebook import codebook_fingerprint
from training.slm_classifier.data_pipeline import (
    CANONICAL_DATASET,
    LABEL_VOCAB_PATH,
    build_group_id,
    dataset_fingerprint,
    load_jsonl_rows,
    load_dataset_splits,
    parse_g2_values,
    primary_g2_label,
    select_rows_for_split,
    validate_dataset_rows,
    write_label_vocab,
)
from training.slm_classifier.runtime_config import load_classifier_runtime_config
from training.slm_classifier.source_normalizer import expand_authoring_rows

# Keep Hugging Face fully local for this project. Transformers can start a
# safetensors auto-conversion background thread during import/model loading, so
# these flags need to exist before any AutoModel call.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
    from transformers import AutoModel, AutoTokenizer
except Exception:  # pragma: no cover
    torch = None
    nn = None
    Dataset = object
    DataLoader = None
    WeightedRandomSampler = None
    AutoModel = None
    AutoTokenizer = None


MODELS_ROOT = Path(__file__).resolve().parents[2] / "models"
CORE_MODELS = {
    "deberta": {
        "model_name": "microsoft/deberta-v3-small",
        "dir_name": "piku-slm-guardrail-deberta-v3-small",
    },
}
CORE_ALIASES = {
    "deberta-v3-xsmall": "deberta",
    "deberta-v3-small": "deberta",
    "deberta": "deberta",
}
DEFAULT_CORE = "deberta"
DEFAULT_CLASSIFIER_THRESHOLD = 0.8

# Inference loads a full backbone per call without this cache (very slow for eval_sheet / pytest).
_TRAINED_MODEL_CACHE: dict[tuple[str, str], tuple[Any, Any]] = {}


def clear_trained_model_cache() -> None:
    _TRAINED_MODEL_CACHE.clear()


@dataclass
class LoadedSLMPackage:
    metadata: dict[str, Any]
    label_vocab: dict[str, list[str]]
    training_config: dict[str, Any]


def available_cores() -> list[str]:
    return list(CORE_MODELS.keys())


def resolve_core(core: str | None) -> str:
    if not core:
        return DEFAULT_CORE
    normalized = str(core).strip().lower()
    resolved = CORE_ALIASES.get(normalized, normalized)
    if resolved not in CORE_MODELS:
        raise ValueError(f"Unsupported core model: {core}")
    return resolved


def model_name_for_core(core: str | None = None) -> str:
    return str(CORE_MODELS[resolve_core(core)]["model_name"])


def model_dir_for_core(core: str | None = None) -> Path:
    return MODELS_ROOT / str(CORE_MODELS[resolve_core(core)]["dir_name"])


def _paths_for_core(core: str | None = None, model_dir: Path | None = None) -> dict[str, Path]:
    model_dir = model_dir or model_dir_for_core(core)
    return {
        "model_dir": model_dir,
        "metadata": model_dir / "training_metadata.json",
        "label_vocab": model_dir / "label_vocab.json",
        "state": model_dir / "pytorch_model.bin",
        "checkpoint": model_dir / "training_checkpoint.pt",
        "training_config": model_dir / "training_config.json",
        "batch_debug": model_dir / "training_batch_debug.jsonl",
    }


def _load_tokenizer(model_name: str) -> Any:
    normalized_name = str(model_name or "").strip().lower()
    if "deberta-v3" in normalized_name and importlib.util.find_spec("sentencepiece") is None:
        raise RuntimeError(
            f"Tokenizer for {model_name} requires the `sentencepiece` package. "
            "Install it in the active environment and rerun training."
        )
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
    except Exception as exc:
        print(f"[SLM] fast tokenizer failed for {model_name}: {exc}")
        tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=False)

    if tokenizer.pad_token is None:
        if tokenizer.eos_token is not None:
            tokenizer.pad_token = tokenizer.eos_token
        elif tokenizer.unk_token is not None:
            tokenizer.pad_token = tokenizer.unk_token
        else:
            tokenizer.add_special_tokens({"pad_token": "[PAD]"})

    return tokenizer


def _load_training_tokenizer(model_name: str, model_dir: Path) -> Any:
    if (model_dir / "tokenizer.json").exists():
        try:
            return AutoTokenizer.from_pretrained(model_dir, use_fast=True, local_files_only=True)
        except Exception as exc:
            print(f"[SLM] local tokenizer failed for {model_dir}: {exc}")
    return _load_tokenizer(model_name)


def _apply_tokenizer_padding_to_model(model: Any, tokenizer: Any) -> None:
    pad_token_id = getattr(tokenizer, "pad_token_id", None)
    if pad_token_id is None:
        return
    model.config.pad_token_id = pad_token_id
    generation_config = getattr(model, "generation_config", None)
    if generation_config is not None:
        generation_config.pad_token_id = pad_token_id


def _codebook_fingerprint() -> str:
    return codebook_fingerprint()


def _iter_rows(path: Path = CANONICAL_DATASET) -> list[dict[str, Any]]:
    return [dict(row) for row in load_jsonl_rows(path)]


def _load_label_vocab() -> dict[str, list[str]]:
    if not LABEL_VOCAB_PATH.exists():
        write_label_vocab(target_path=LABEL_VOCAB_PATH)
    return json.loads(LABEL_VOCAB_PATH.read_text(encoding="utf-8"))


def _decode_g2_predictions(
    label_vocab: dict[str, list[str]],
    primary_probs: list[float],
) -> str:
    g2_labels = list(label_vocab.get("g2", []))
    if not g2_labels:
        return "GENERIC_INTENT"
    primary_index = max(range(len(primary_probs)), key=lambda idx: float(primary_probs[idx]))
    return g2_labels[primary_index]


def ensure_label_vocab(model_dir: Path | None = None, core: str | None = None) -> Path:
    if model_dir is None:
        model_dir = model_dir_for_core(core)
    source = LABEL_VOCAB_PATH
    if not source.exists():
        write_label_vocab(source)
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "label_vocab.json").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return model_dir / "label_vocab.json"


def _training_defaults(core: str | None = None) -> dict[str, Any]:
    resolved_core = resolve_core(core)
    config = {
        "core_model": resolved_core,
        "model_name": model_name_for_core(resolved_core),
        "device": "auto",
        "max_length": 128,
        "batch_size": 12,
        "epochs": 4,
        "learning_rate": 5e-6,
        "head_learning_rate": 5e-5,
        "weight_decay": 0.01,
        "g1_loss_weight": 0.2,
        "g2_loss_weight": 2.0,
        "flag_loss_weight": 0.3,
        "intent_family_loss_weight": 0.15,
        "intent_phrase_loss_weight": 0.10,
        "flag_max_pos_weight": 8.0,  # Stricter cap for lower-dimensional flags
        "intent_family_max_pos_weight": 18.0,  # Higher headroom for sparse child safety behaviors
        "intent_phrase_max_pos_weight": 18.0,
        "g2_focal_gamma": 2.0,
        "intent_family_focal_gamma": 2.0,
        "intent_phrase_focal_gamma": 2.0,
        "train_split": "train",
        "eval_split": "test",
        "freeze_backbone": False,
        "unfreeze_top_layers": 0,
        "log_every_batches": 25,
        "checkpoint_every_batches": 500,
        "resume_if_available": False,
        "local_files_only": True,
        "balanced_sampling": False,
        "balanced_sampling_max_epochs": 4,
        "balanced_sampling_force_frozen_backbone": True,
        "gradient_clip_norm": 1.0,
        "use_class_weights": False,
        "train_intent_heads": True,
        "cross_feature_fusion_version": 3,
        "write_batch_debug": True,
        "batch_debug_loss_threshold": 9.0,
        "seed": 42,
    }
    if resolved_core == "smol":
        config["epochs"] = 2
        config["batch_size"] = 1
        config["max_length"] = 128
        config["learning_rate"] = 5e-6
        config["weight_decay"] = 0.0
        config["freeze_backbone"] = True
        config["log_every_batches"] = 10
        config["checkpoint_every_batches"] = 1000
    elif resolved_core == "llama_guard":
        config["epochs"] = 2
        config["batch_size"] = 1
        config["max_length"] = 256
        config["learning_rate"] = 1e-5
        config["freeze_backbone"] = True
        config["log_every_batches"] = 5
        config["checkpoint_every_batches"] = 250
    return config


def _checkpoint_is_compatible(state_dict: dict[str, Any]) -> bool:
    return any(
        key.startswith(prefix)
        for key in state_dict
        for prefix in ("g1_classifier.", "g2_classifier.", "flag_classifier.", "classifier.")
    )


def _filter_compatible_state_dict(model: Any, state_dict: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    model_state = model.state_dict()
    filtered: dict[str, Any] = {}
    skipped: list[str] = []
    for key, value in state_dict.items():
        if key not in model_state:
            skipped.append(key)
            continue
        if tuple(value.shape) != tuple(model_state[key].shape):
            skipped.append(key)
            continue
        filtered[key] = value
    return filtered, skipped


def _build_training_metadata(
    rows: list[dict[str, Any]],
    train_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    trained: bool,
    training_backend: str,
    core: str,
) -> dict[str, Any]:
    return {
        "core_model": core,
        "model_name": model_name_for_core(core),
        "model_type": "slm-g2-sequence-classifier",
        "runtime": "transformers-local",
        "language_scope": "english-first",
        "dataset_rows": len(rows),
        "dataset_fingerprint": dataset_fingerprint(rows),
        "codebook_fingerprint": _codebook_fingerprint(),
        "group_count": len({build_group_id(row) for row in rows}),
        "train_rows": len(train_rows),
        "test_rows": len(test_rows),
        "transformers_available": bool(AutoModel and AutoTokenizer and torch and nn),
        "trained": trained,
        "training_backend": training_backend,
        "flags_trained": bool(trained),
    }


def _existing_training_metadata(model_dir: Path) -> dict[str, Any]:
    path = model_dir / "training_metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _checkpoint_payload_is_compatible(payload: dict[str, Any]) -> bool:
    model_state = payload.get("model_state")
    return isinstance(model_state, dict) and _checkpoint_is_compatible(model_state)


def _optimizer_state_is_compatible(optimizer: Any, optimizer_state: dict[str, Any] | None) -> bool:
    if not isinstance(optimizer_state, dict):
        return False
    saved_groups = optimizer_state.get("param_groups", [])
    current_groups = optimizer.state_dict().get("param_groups", [])
    if not (isinstance(saved_groups, list) and len(saved_groups) == len(current_groups)):
        return False
    saved_state = optimizer_state.get("state", {})
    if len(optimizer.param_groups) != len(saved_groups):
        return False
    for live_group, saved_group in zip(optimizer.param_groups, saved_groups):
        live_params = list(live_group.get("params", []))
        saved_params = list(saved_group.get("params", []))
        if len(live_params) != len(saved_params):
            return False
        for live_param, saved_param_id in zip(live_params, saved_params):
            state_entry = saved_state.get(saved_param_id, {})
            for value in state_entry.values():
                if hasattr(value, "shape") and tuple(value.shape) != tuple(live_param.shape):
                    return False
    return True


def _build_epoch_train_loader(
    train_rows: list[dict[str, Any]],
    tokenizer: Any,
    label_vocab: dict[str, list[str]],
    config: dict[str, Any],
    epoch_index: int,
) -> Any:
    train_dataset = CanonicalSLMDataset(train_rows, tokenizer, label_vocab, config["max_length"])
    sampler = None
    generator = torch.Generator()
    generator.manual_seed(int(config.get("seed", 42)) + int(epoch_index))
    if bool(config.get("balanced_sampling", True)):
        if WeightedRandomSampler is None:
            raise RuntimeError("WeightedRandomSampler is not available for balanced SLM training.")
        sample_weights = _compute_sample_weights(train_rows, label_vocab)
        sampler = WeightedRandomSampler(
            weights=torch.tensor(sample_weights, dtype=torch.double),
            num_samples=len(sample_weights),
            replacement=True,
            generator=generator,
        )
    return DataLoader(
        train_dataset,
        batch_size=config["batch_size"],
        shuffle=sampler is None,
        sampler=sampler,
        generator=None if sampler is not None else generator,
    )


def _save_training_checkpoint(
    *,
    path: Path,
    model_state: dict[str, Any],
    optimizer_state: dict[str, Any],
    epoch_index: int,
    batch_index: int,
    best_test_loss: float | None,
    config: dict[str, Any],
    dataset_fingerprint_value: str,
) -> None:
    payload = {
        "model_state": model_state,
        "optimizer_state": optimizer_state,
        "epoch_index": int(epoch_index),
        "batch_index": int(batch_index),
        "best_test_loss": best_test_loss,
        "config": dict(config),
        "dataset_fingerprint": dataset_fingerprint_value,
    }
    torch.save(payload, path)


def _classifier_token_usage(encoded: dict[str, Any]) -> dict[str, int]:
    attention_mask = encoded.get("attention_mask")
    if attention_mask is not None:
        prompt_tokens = int(attention_mask.sum().item())
    else:
        input_ids = encoded.get("input_ids")
        prompt_tokens = int(input_ids.numel()) if input_ids is not None else 0
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": 0,
        "total_tokens": prompt_tokens,
    }


def _format_classifier_input(row: dict[str, Any]) -> str:
    context = str(row.get("context", row.get("recent_context", "none")) or "none").strip()
    question = str(row["question"]).strip()
    return (
        "Classify the PRIMARY QUESTION for child-safety gating.\n"
        "Use BACKGROUND CONTEXT only when it changes the meaning of the primary question.\n"
        f"PRIMARY QUESTION: {question}\n"
        f"BACKGROUND CONTEXT: {context if context else 'none'}"
    )


def _index_map(values: list[str]) -> dict[str, int]:
    return {value: idx for idx, value in enumerate(values)}


def _compute_class_weights(rows: list[dict[str, Any]], key: str, vocab: list[str]) -> list[float]:
    counts = {value: 0 for value in vocab}
    for row in rows:
        if key == "g2":
            label = primary_g2_label(row.get("g2", []))
        else:
            label = str(row[key])
        if label in counts:
            counts[label] += 1
    total = max(len(rows), 1)
    weights: list[float] = []
    for value in vocab:
        count = max(counts[value], 1)
        weights.append(total / (len(vocab) * count))
    return weights


def _compute_list_multilabel_pos_weight(
    rows: list[dict[str, Any]],
    vocab: list[str],
    key: str,
    *,
    max_pos_weight: float | None = None,
) -> list[float]:
    total = max(len(rows), 1)
    counts = {value: 0 for value in vocab}
    for row in rows:
        raw_values = row.get(key, [])
        if isinstance(raw_values, dict):
            values = [str(label).strip() for label, enabled in raw_values.items() if str(label).strip() and bool(enabled)]
        else:
            values = [str(item).strip() for item in raw_values if str(item).strip()]
        for value in values:
            if value in counts:
                counts[value] += 1
    weights: list[float] = []
    for value in vocab:
        positives = max(counts[value], 1)
        negatives = max(total - positives, 1)
        weight = negatives / positives
        if max_pos_weight is not None:
            weight = min(weight, float(max_pos_weight))
        weights.append(weight)
    return weights


def _compute_sample_weights(rows: list[dict[str, Any]], label_vocab: dict[str, list[str]]) -> list[float]:
    g2_counts = {value: 0 for value in label_vocab["g2"]}
    total = max(len(rows), 1)

    for row in rows:
        for value in parse_g2_values(row.get("g2", [])):
            if value in g2_counts:
                g2_counts[value] += 1
    weights: list[float] = []
    for row in rows:
        active_g2_weights = [
            total / max(g2_counts[value], 1)
            for value in parse_g2_values(row.get("g2", []))
            if value in g2_counts
        ]
        g2_weight = max(active_g2_weights) if active_g2_weights else 1.0
        weights.append(float(g2_weight))
    return weights


def _validate_rows_against_label_vocab(rows: list[dict[str, Any]], label_vocab: dict[str, list[str]]) -> None:
    vocab_sets = {
        "g1": set(label_vocab.get("g1", [])),
        "g2": set(label_vocab.get("g2", [])),
        "flags": set(label_vocab.get("flags", [])),
        "intent_families": set(label_vocab.get("intent_families", [])),
        "intent_phrases": set(label_vocab.get("intent_phrases", [])),
    }
    errors: list[str] = []
    for row in rows:
        sample_id = str(row.get("sample_id", "unknown"))
        g1 = str(row.get("g1", "")).strip()
        if g1 and g1 not in vocab_sets["g1"]:
            errors.append(f"{sample_id}: unknown g1={g1}")
        for g2 in parse_g2_values(row.get("g2", [])):
            if g2 not in vocab_sets["g2"]:
                errors.append(f"{sample_id}: unknown g2={g2}")
        flags = row.get("flags", {})
        if isinstance(flags, dict):
            for flag, enabled in flags.items():
                if enabled and str(flag) not in vocab_sets["flags"]:
                    errors.append(f"{sample_id}: unknown flag={flag}")
        for family in row.get("intent_families", []) or []:
            family_id = str(family).strip()
            if family_id and family_id not in vocab_sets["intent_families"]:
                errors.append(f"{sample_id}: unknown intent_family={family_id}")
        for phrase in row.get("intent_phrases", []) or []:
            phrase_id = str(phrase).strip()
            if phrase_id and phrase_id not in vocab_sets["intent_phrases"]:
                errors.append(f"{sample_id}: unknown intent_phrase={phrase_id}")
    if errors:
        preview = "\n".join(errors[:20])
        suffix = f"\n... and {len(errors) - 20} more" if len(errors) > 20 else ""
        raise ValueError(
            "Incremental source is incompatible with the existing model label vocab. "
            "Run full training with --rebuild-dataset if you need to add new vocab entries.\n"
            f"{preview}{suffix}"
        )


class CanonicalSLMDataset(Dataset):  # pragma: no cover - exercised through training/inference path
    def __init__(self, rows: list[dict[str, Any]], tokenizer: Any, label_vocab: dict[str, list[str]], max_length: int) -> None:
        self.rows = rows
        self.tokenizer = tokenizer
        self.label_vocab = label_vocab
        self.max_length = max_length
        self.g1_index = _index_map(label_vocab["g1"])
        self.g2_index = _index_map(label_vocab["g2"])
        self.flag_vocab = list(label_vocab.get("flags", []))
        self.intent_family_vocab = list(label_vocab.get("intent_families", []))
        self.intent_family_index = _index_map(self.intent_family_vocab) if self.intent_family_vocab else {}
        self.intent_phrase_vocab = list(label_vocab.get("intent_phrases", []))

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.rows[index]
        encoded = self.tokenizer(
            _format_classifier_input(row),
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt",
        )
        return {
            "input_ids": encoded["input_ids"].squeeze(0),
            "attention_mask": encoded["attention_mask"].squeeze(0),
            "intent_rule_features": torch.tensor(
                runtime_contracts.build_intent_family_rule_vector(
                    str(row.get("question", "")),
                    str(row.get("context", "")),
                    self.intent_family_vocab,
                ),
                dtype=torch.float32,
            ),
            "phrase_trigger_features": torch.tensor(
                runtime_contracts.build_g2_phrase_trigger_vector(
                    str(row.get("question", "")),
                    str(row.get("context", "")),
                    list(self.label_vocab.get("g2", [])),
                ),
                dtype=torch.float32,
            ),
            "g1_labels": torch.tensor(self.g1_index[str(row.get("g1", ""))], dtype=torch.long),
            "g2_labels": torch.tensor(self.g2_index[primary_g2_label(row.get("g2", []))], dtype=torch.long),
            "flag_labels": torch.tensor(
                [1.0 if bool(row.get("flags", {}).get(flag, False)) else 0.0 for flag in self.flag_vocab],
                dtype=torch.float32,
            ),
            "intent_family_labels": torch.tensor(
                [
                    1.0 if str(intent_family) in {str(item).strip() for item in row.get("intent_families", []) or []} else 0.0
                    for intent_family in self.intent_family_vocab
                ],
                dtype=torch.float32,
            ),
            "intent_family_mask": torch.tensor(
                1.0 if bool(row.get("intent_families_present", False)) and self.intent_family_vocab else 0.0,
                dtype=torch.float32,
            ),
            "intent_phrase_labels": torch.tensor(
                [
                    1.0 if str(intent_phrase) in {str(item).strip() for item in row.get("intent_phrases", []) or []} else 0.0
                    for intent_phrase in self.intent_phrase_vocab
                ],
                dtype=torch.float32,
            ),
            "intent_phrase_mask": torch.tensor(
                1.0 if bool(row.get("intent_phrases_present", False)) and self.intent_phrase_vocab else 0.0,
                dtype=torch.float32,
            ),
            "sample_id": str(row.get("sample_id", "")),
            "question": str(row.get("question", "")),
            "context": str(row.get("context", "")),
            "g1_text": str(row.get("g1", "")),
            "g2_text": primary_g2_label(row.get("g2", [])),
            "flags_json": json.dumps(row.get("flags", {}), sort_keys=True),
        }


class CrossFeatureFusionHead(nn.Module):  # pragma: no cover - exercised through training/inference path
    def __init__(self, hidden_size: int, num_intent_rules: int, num_phrase_triggers: int, num_g2_labels: int) -> None:
        super().__init__()
        self.num_intent_rules = int(num_intent_rules)
        self.num_phrase_triggers = int(num_phrase_triggers)
        self.intent_rule_projection = nn.Linear(self.num_intent_rules, hidden_size) if self.num_intent_rules else None
        self.phrase_trigger_projection = nn.Linear(self.num_phrase_triggers, hidden_size) if self.num_phrase_triggers else None
        self.prior_attention = nn.MultiheadAttention(hidden_size, num_heads=1, batch_first=True)
        self.glu_projection = nn.Linear(hidden_size * 2, hidden_size * 2)
        self.fusion_norm = nn.LayerNorm(hidden_size)
        self.classifier = nn.Linear(hidden_size, num_g2_labels)

    def forward(self, pooled: Any, intent_rule_features: Any | None, phrase_trigger_features: Any | None) -> Any:
        intent_signal = torch.zeros_like(pooled)
        phrase_signal = torch.zeros_like(pooled)
        if self.intent_rule_projection is not None and intent_rule_features is not None:
            intent_signal = self.intent_rule_projection(intent_rule_features.to(dtype=pooled.dtype))
        if self.phrase_trigger_projection is not None and phrase_trigger_features is not None:
            phrase_signal = self.phrase_trigger_projection(phrase_trigger_features.to(dtype=pooled.dtype))
        prior_tokens = torch.stack((intent_signal, phrase_signal), dim=1)
        attended_prior, _ = self.prior_attention(
            pooled.unsqueeze(1),
            prior_tokens,
            prior_tokens,
            need_weights=False,
        )
        fusion_input = torch.cat((pooled, attended_prior.squeeze(1)), dim=-1)
        candidate, gate = self.glu_projection(fusion_input).chunk(2, dim=-1)
        fused = self.fusion_norm(pooled + candidate * torch.sigmoid(gate))
        return self.classifier(fused)


class MultiHeadSLMClassifier(nn.Module):  # pragma: no cover - exercised through training/inference path
    def __init__(self, model_name: str, num_g1_labels: int, num_g2_labels: int, num_flags: int, num_intent_families: int, num_intent_phrases: int, num_intent_rules: int, num_phrase_triggers: int, *, local_files_only: bool = False) -> None:
        super().__init__()
        if local_files_only:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
        self.backbone = AutoModel.from_pretrained(model_name, local_files_only=local_files_only)
        hidden_size = int(self.backbone.config.hidden_size)
        dropout_prob = float(
            getattr(self.backbone.config, "cls_dropout", None)
            or getattr(self.backbone.config, "hidden_dropout_prob", 0.1)
            or 0.1
        )
        self.dropout = nn.Dropout(dropout_prob)
        self.g1_classifier = nn.Linear(hidden_size, num_g1_labels)
        self.g2_classifier = CrossFeatureFusionHead(hidden_size, num_intent_rules, num_phrase_triggers, num_g2_labels)
        self.flag_classifier = nn.Linear(hidden_size, num_flags)
        self.intent_family_classifier = nn.Linear(hidden_size, num_intent_families) if num_intent_families > 0 else None
        self.intent_phrase_classifier = nn.Linear(hidden_size, num_intent_phrases) if num_intent_phrases > 0 else None
        self.config = self.backbone.config

    def forward(
        self,
        input_ids: Any,
        attention_mask: Any,
        token_type_ids: Any | None = None,
        intent_rule_features: Any | None = None,
        phrase_trigger_features: Any | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        backbone_kwargs = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        if token_type_ids is not None:
            backbone_kwargs["token_type_ids"] = token_type_ids
        outputs = self.backbone(**backbone_kwargs)
        hidden_state = outputs.last_hidden_state
        mask = attention_mask.unsqueeze(-1).to(hidden_state.dtype)
        pooled = (hidden_state * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1.0)
        pooled = self.dropout(pooled.float())
        intent_family_logits = self.intent_family_classifier(pooled) if self.intent_family_classifier is not None else None
        fusion_intent_features = intent_rule_features
        if intent_family_logits is not None:
            learned_intent_features = torch.sigmoid(intent_family_logits)
            fusion_intent_features = (
                torch.maximum(learned_intent_features, intent_rule_features.to(dtype=pooled.dtype))
                if intent_rule_features is not None
                else learned_intent_features
            )
        payload = {
            "g1_logits": self.g1_classifier(pooled),
            "g2_logits": self.g2_classifier(pooled, fusion_intent_features, phrase_trigger_features),
            "flag_logits": self.flag_classifier(pooled),
        }
        if self.intent_family_classifier is not None:
            payload["intent_family_logits"] = intent_family_logits
        if self.intent_phrase_classifier is not None:
            payload["intent_phrase_logits"] = self.intent_phrase_classifier(pooled)
        return payload


def _model_backbone(model: Any) -> Any:
    return getattr(model, "backbone", getattr(model, "base_model", model))


def _freeze_backbone(model: Any) -> None:
    for parameter in _model_backbone(model).parameters():
        parameter.requires_grad = False


def _unfreeze_backbone(model: Any) -> None:
    for parameter in _model_backbone(model).parameters():
        parameter.requires_grad = True


def _unfreeze_top_layers(model: Any, layer_count: int) -> int:
    _freeze_backbone(model)
    requested = max(int(layer_count), 0)
    if requested <= 0:
        return 0
    backbone = _model_backbone(model)
    layer_container = None
    if hasattr(backbone, "model") and hasattr(backbone.model, "layers"):
        layer_container = backbone.model.layers
    elif hasattr(backbone, "layers"):
        layer_container = backbone.layers
    elif hasattr(backbone, "encoder") and hasattr(backbone.encoder, "layer"):
        layer_container = backbone.encoder.layer
    if layer_container is None:
        raise RuntimeError("Backbone does not expose a supported layer stack for partial unfreezing.")
    total_layers = len(layer_container)
    actual = min(requested, total_layers)
    for layer in list(layer_container)[-actual:]:
        for parameter in layer.parameters():
            parameter.requires_grad = True
    return actual


def _prefers_cpu_on_mps(model_name: str | None = None) -> bool:
    normalized = str(model_name or "").strip().lower()
    return "deberta" in normalized or "smollm" in normalized or "llama-guard" in normalized


def _device(model_name: str | None = None, device_preference: str = "auto") -> Any:
    if torch is None:
        raise RuntimeError("Torch is not available.")
    normalized_preference = str(device_preference or "auto").strip().lower()
    if normalized_preference not in {"auto", "cpu", "mps"}:
        raise ValueError(f"Unsupported device preference: {device_preference}")
    if normalized_preference == "cpu":
        return torch.device("cpu")
    if normalized_preference == "mps":
        if not hasattr(torch.backends, "mps") or not torch.backends.mps.is_available():
            raise RuntimeError("Requested device='mps' but MPS is not available.")
        return torch.device("mps")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() and not _prefers_cpu_on_mps(model_name):
        return torch.device("mps")
    return torch.device("cpu")


def _cpu_device() -> Any:
    if torch is None:
        raise RuntimeError("Torch is not available.")
    return torch.device("cpu")


def _load_rows_by_split(dataset_path: Path, split_name: str) -> list[dict[str, Any]]:
    rows = _iter_rows(dataset_path)
    return select_rows_for_split(rows, split_name, load_dataset_splits())


class MulticlassFocalLoss(nn.Module):
    def __init__(self, gamma: float = 2.0, weight: Any | None = None) -> None:
        super().__init__()
        self.gamma = float(gamma)
        if self.gamma < 0.0:
            raise ValueError("Focal loss gamma must be non-negative.")
        self.register_buffer("weight", weight)

    def forward(self, logits: Any, targets: Any) -> Any:
        log_probs = torch.nn.functional.log_softmax(logits.float(), dim=-1)
        target_log_probs = log_probs.gather(1, targets.view(-1, 1)).squeeze(1)
        target_probs = target_log_probs.exp().clamp(min=0.0, max=1.0)
        focal_factor = (1.0 - target_probs).clamp(min=0.0, max=1.0).pow(self.gamma)
        loss = -focal_factor * target_log_probs
        if self.weight is not None:
            loss = loss * self.weight.to(logits.device).gather(0, targets)
        return loss.mean()


class BinaryFocalLoss(nn.Module):
    def __init__(self, gamma: float = 2.0, pos_weight: Any | None = None) -> None:
        super().__init__()
        self.gamma = float(gamma)
        if self.gamma < 0.0:
            raise ValueError("Focal loss gamma must be non-negative.")
        self.register_buffer("pos_weight", pos_weight)

    def forward(self, logits: Any, targets: Any) -> Any:
        return _binary_focal_loss_elements(logits, targets, self).mean()


def _binary_focal_loss_elements(logits: Any, targets: Any, loss_fn: Any) -> Any:
    float_logits = logits.float()
    float_targets = targets.float()
    raw_loss = torch.nn.functional.binary_cross_entropy_with_logits(
        float_logits,
        float_targets,
        pos_weight=getattr(loss_fn, "pos_weight", None),
        reduction="none",
    )
    log_prob_true = (
        float_targets * torch.nn.functional.logsigmoid(float_logits)
        + (1.0 - float_targets) * torch.nn.functional.logsigmoid(-float_logits)
    )
    prob_true = log_prob_true.exp().clamp(min=0.0, max=1.0)
    gamma = float(getattr(loss_fn, "gamma", 0.0))
    focal_factor = (1.0 - prob_true).clamp(min=0.0, max=1.0).pow(gamma)
    return raw_loss * focal_factor


def _compute_loss(
    outputs: dict[str, Any],
    batch: dict[str, Any],
    g1_loss_fn: Any,
    g2_loss_fn: Any,
    flag_loss_fn: Any,
    intent_family_loss_fn: Any | None = None,
    intent_phrase_loss_fn: Any | None = None,
    g1_loss_weight: float = 0.2,
    g2_loss_weight: float = 2.0,
    flag_loss_weight: float = 0.45,
    intent_family_loss_weight: float = 0.15,
    intent_phrase_loss_weight: float = 0.10,
) -> Any:
    g1_loss = g1_loss_fn(outputs["g1_logits"].float(), batch["g1_labels"])
    g2_loss = g2_loss_fn(outputs["g2_logits"].float(), batch["g2_labels"])
    flag_loss = flag_loss_fn(outputs["flag_logits"].float(), batch["flag_labels"])
    total_loss = (
        float(g1_loss_weight) * g1_loss
        + float(g2_loss_weight) * g2_loss
        + float(flag_loss_weight) * flag_loss
    )
    if intent_family_loss_fn is not None and "intent_family_logits" in outputs and batch["intent_family_labels"].numel():
        intent_family_mask = batch["intent_family_mask"].float().view(-1, 1)
        if float(intent_family_mask.sum().item()) > 0:
            raw_loss = _binary_focal_loss_elements(
                outputs["intent_family_logits"].float(),
                batch["intent_family_labels"],
                intent_family_loss_fn,
            )
            valid_element_count = intent_family_mask.sum() * raw_loss.shape[1]
            masked_loss = (raw_loss * intent_family_mask).sum() / valid_element_count.clamp(min=1.0)
            total_loss = total_loss + float(intent_family_loss_weight) * masked_loss
    if intent_phrase_loss_fn is not None and "intent_phrase_logits" in outputs and batch["intent_phrase_labels"].numel():
        intent_phrase_mask = batch["intent_phrase_mask"].float().view(-1, 1)
        if float(intent_phrase_mask.sum().item()) > 0:
            raw_loss = _binary_focal_loss_elements(
                outputs["intent_phrase_logits"].float(),
                batch["intent_phrase_labels"],
                intent_phrase_loss_fn,
            )
            valid_element_count = intent_phrase_mask.sum() * raw_loss.shape[1]
            masked_loss = (raw_loss * intent_phrase_mask).sum() / valid_element_count.clamp(min=1.0)
            total_loss = total_loss + float(intent_phrase_loss_weight) * masked_loss
    return total_loss


def _compute_loss_breakdown(
    outputs: dict[str, Any],
    batch: dict[str, Any],
    g1_loss_fn: Any,
    g2_loss_fn: Any,
    flag_loss_fn: Any,
    intent_family_loss_fn: Any | None = None,
    intent_phrase_loss_fn: Any | None = None,
) -> dict[str, float]:
    payload = {
        "g1_loss": float(g1_loss_fn(outputs["g1_logits"].float(), batch["g1_labels"]).item()),
        "g2_loss": float(g2_loss_fn(outputs["g2_logits"].float(), batch["g2_labels"]).item()),
        "flag_loss": float(flag_loss_fn(outputs["flag_logits"].float(), batch["flag_labels"]).item()),
    }
    if intent_family_loss_fn is not None and "intent_family_logits" in outputs and batch["intent_family_labels"].numel():
        intent_family_mask = batch["intent_family_mask"].float().view(-1, 1)
        if float(intent_family_mask.sum().item()) > 0:
            raw_loss = _binary_focal_loss_elements(
                outputs["intent_family_logits"].float(),
                batch["intent_family_labels"],
                intent_family_loss_fn,
            )
            valid_element_count = intent_family_mask.sum() * raw_loss.shape[1]
            payload["intent_family_loss"] = float(
                ((raw_loss * intent_family_mask).sum() / valid_element_count.clamp(min=1.0)).item()
            )
    if intent_phrase_loss_fn is not None and "intent_phrase_logits" in outputs and batch["intent_phrase_labels"].numel():
        intent_phrase_mask = batch["intent_phrase_mask"].float().view(-1, 1)
        if float(intent_phrase_mask.sum().item()) > 0:
            raw_loss = _binary_focal_loss_elements(
                outputs["intent_phrase_logits"].float(),
                batch["intent_phrase_labels"],
                intent_phrase_loss_fn,
            )
            valid_element_count = intent_phrase_mask.sum() * raw_loss.shape[1]
            payload["intent_phrase_loss"] = float(
                ((raw_loss * intent_phrase_mask).sum() / valid_element_count.clamp(min=1.0)).item()
            )
    return payload


def _evaluate_loss(
    model: Any,
    loader: Any,
    g1_loss_fn: Any,
    g2_loss_fn: Any,
    flag_loss_fn: Any,
    intent_family_loss_fn: Any | None = None,
    intent_phrase_loss_fn: Any | None = None,
    g1_loss_weight: float = 0.2,
    g2_loss_weight: float = 2.0,
    flag_loss_weight: float = 0.45,
    intent_family_loss_weight: float = 0.15,
    intent_phrase_loss_weight: float = 0.10,
) -> float:
    model.eval()
    total_loss = 0.0
    total_batches = 0
    with torch.no_grad():
        for batch in loader:
            tensor_batch, _ = _split_batch_for_training(batch)
            tensor_batch = {key: value.to(_device(getattr(model.config, "_name_or_path", None))) for key, value in tensor_batch.items()}
            outputs = model(
                input_ids=tensor_batch["input_ids"],
                attention_mask=tensor_batch["attention_mask"],
                intent_rule_features=tensor_batch["intent_rule_features"],
                phrase_trigger_features=tensor_batch["phrase_trigger_features"],
            )
            loss = _compute_loss(
                outputs,
                tensor_batch,
                g1_loss_fn,
                g2_loss_fn,
                flag_loss_fn,
                intent_family_loss_fn,
                intent_phrase_loss_fn,
                g1_loss_weight=g1_loss_weight,
                g2_loss_weight=g2_loss_weight,
                flag_loss_weight=flag_loss_weight,
                intent_family_loss_weight=intent_family_loss_weight,
                intent_phrase_loss_weight=intent_phrase_loss_weight,
            )
            total_loss += float(loss.item())
            total_batches += 1
    return total_loss / total_batches if total_batches else 0.0


def _evaluate_gate_accuracy(model: Any, loader: Any, label_vocab: dict[str, list[str]]) -> dict[str, Any]:
    model.eval()
    g1_correct = 0
    g2_correct = 0
    total = 0
    g1_predictions: Counter[str] = Counter()
    g1_counts = {
        label: {"tp": 0, "fp": 0, "fn": 0}
        for label in label_vocab.get("g1", [])
    }
    g2_predictions: Counter[str] = Counter()
    g2_counts = {
        label: {"tp": 0, "fp": 0, "fn": 0}
        for label in label_vocab.get("g2", [])
    }
    flag_counts = {
        label: {"tp": 0, "fp": 0, "fn": 0}
        for label in label_vocab.get("flags", [])
    }
    intent_family_counts = {
        label: {"tp": 0, "fp": 0, "fn": 0}
        for label in label_vocab.get("intent_families", [])
    }
    intent_phrase_counts = {
        label: {"tp": 0, "fp": 0, "fn": 0}
        for label in label_vocab.get("intent_phrases", [])
    }
    flag_exact_match = 0
    intent_family_exact_match = 0
    intent_family_evaluated_total = 0
    intent_phrase_exact_match = 0
    intent_phrase_evaluated_total = 0
    with torch.no_grad():
        for batch in loader:
            device = _device(getattr(model.config, "_name_or_path", None))
            tensor_batch, meta_batch = _split_batch_for_training(batch)
            tensor_batch = {key: value.to(device) for key, value in tensor_batch.items()}
            outputs = model(
                input_ids=tensor_batch["input_ids"],
                attention_mask=tensor_batch["attention_mask"],
                intent_rule_features=tensor_batch["intent_rule_features"],
                phrase_trigger_features=tensor_batch["phrase_trigger_features"],
            )
            g1_pred = torch.argmax(outputs["g1_logits"], dim=-1)
            g2_pred = torch.argmax(outputs["g2_logits"], dim=-1)
            flag_pred = (torch.sigmoid(outputs["flag_logits"]) >= 0.5).to(dtype=tensor_batch["flag_labels"].dtype)
            intent_family_pred = None
            if "intent_family_logits" in outputs and "intent_family_labels" in tensor_batch and tensor_batch["intent_family_labels"].shape[-1] > 0:
                intent_family_pred = (torch.sigmoid(outputs["intent_family_logits"]) >= 0.5).to(
                    dtype=tensor_batch["intent_family_labels"].dtype
                )
            intent_phrase_pred = None
            if "intent_phrase_logits" in outputs and "intent_phrase_labels" in tensor_batch and tensor_batch["intent_phrase_labels"].shape[-1] > 0:
                intent_phrase_pred = (torch.sigmoid(outputs["intent_phrase_logits"]) >= 0.5).to(
                    dtype=tensor_batch["intent_phrase_labels"].dtype
                )
            g1_correct += int((g1_pred == tensor_batch["g1_labels"]).sum().item())
            g2_correct += int((g2_pred == tensor_batch["g2_labels"]).sum().item())
            batch_size = int(tensor_batch["g2_labels"].shape[0])
            total += batch_size
            predicted_g1_values = [label_vocab["g1"][int(idx)] for idx in g1_pred.cpu().tolist()]
            gold_g1_values = [str(value) for value in meta_batch.get("g1_text", [])]
            g2_pred_values = g2_pred.cpu().tolist()
            g2_gold_values = tensor_batch["g2_labels"].cpu().tolist()
            for value in predicted_g1_values:
                g1_predictions[str(value)] += 1
            for pred_label, gold_label in zip(predicted_g1_values, gold_g1_values):
                for label in g1_counts:
                    gold = gold_label == label
                    pred = pred_label == label
                    if gold and pred:
                        g1_counts[label]["tp"] += 1
                    elif (not gold) and pred:
                        g1_counts[label]["fp"] += 1
                    elif gold and (not pred):
                        g1_counts[label]["fn"] += 1
            for value in g2_pred_values:
                g2_predictions[str(value)] += 1
            for pred_idx, gold_idx in zip(g2_pred_values, g2_gold_values):
                pred_label = label_vocab["g2"][pred_idx]
                gold_label = label_vocab["g2"][gold_idx]
                for label in g2_counts:
                    gold = gold_label == label
                    pred = pred_label == label
                    if gold and pred:
                        g2_counts[label]["tp"] += 1
                    elif (not gold) and pred:
                        g2_counts[label]["fp"] += 1
                    elif gold and (not pred):
                        g2_counts[label]["fn"] += 1
            if flag_counts:
                flag_gold = tensor_batch["flag_labels"].cpu().tolist()
                flag_pred_values = flag_pred.cpu().tolist()
                for pred_row, gold_row in zip(flag_pred_values, flag_gold):
                    if pred_row == gold_row:
                        flag_exact_match += 1
                    for idx, label in enumerate(label_vocab["flags"]):
                        gold = bool(gold_row[idx])
                        pred = bool(pred_row[idx])
                        if gold and pred:
                            flag_counts[label]["tp"] += 1
                        elif (not gold) and pred:
                            flag_counts[label]["fp"] += 1
                        elif gold and (not pred):
                            flag_counts[label]["fn"] += 1
            if intent_family_counts and intent_family_pred is not None:
                intent_gold = tensor_batch["intent_family_labels"].cpu().tolist()
                intent_pred_values = intent_family_pred.cpu().tolist()
                intent_mask = tensor_batch["intent_family_mask"].cpu().tolist()
                for pred_row, gold_row, mask_value in zip(intent_pred_values, intent_gold, intent_mask):
                    if not bool(mask_value):
                        continue
                    intent_family_evaluated_total += 1
                    if pred_row == gold_row:
                        intent_family_exact_match += 1
                    for idx, label in enumerate(label_vocab["intent_families"]):
                        gold = bool(gold_row[idx])
                        pred = bool(pred_row[idx])
                        if gold and pred:
                            intent_family_counts[label]["tp"] += 1
                        elif (not gold) and pred:
                            intent_family_counts[label]["fp"] += 1
                        elif gold and (not pred):
                            intent_family_counts[label]["fn"] += 1
            if intent_phrase_counts and intent_phrase_pred is not None:
                intent_gold = tensor_batch["intent_phrase_labels"].cpu().tolist()
                intent_pred_values = intent_phrase_pred.cpu().tolist()
                intent_mask = tensor_batch["intent_phrase_mask"].cpu().tolist()
                for pred_row, gold_row, mask_value in zip(intent_pred_values, intent_gold, intent_mask):
                    if not bool(mask_value):
                        continue
                    intent_phrase_evaluated_total += 1
                    if pred_row == gold_row:
                        intent_phrase_exact_match += 1
                    for idx, label in enumerate(label_vocab["intent_phrases"]):
                        gold = bool(gold_row[idx])
                        pred = bool(pred_row[idx])
                        if gold and pred:
                            intent_phrase_counts[label]["tp"] += 1
                        elif (not gold) and pred:
                            intent_phrase_counts[label]["fp"] += 1
                        elif gold and (not pred):
                            intent_phrase_counts[label]["fn"] += 1
    def _multiclass_summary(counts_map: dict[str, dict[str, int]]) -> dict[str, float]:
        f1_values: list[float] = []
        weighted_f1_numerator = 0.0
        weighted_support = 0
        for counts in counts_map.values():
            tp = counts["tp"]
            fp = counts["fp"]
            fn = counts["fn"]
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
            support = tp + fn
            f1_values.append(f1)
            weighted_f1_numerator += f1 * support
            weighted_support += support
        return {
            "macro_f1": (sum(f1_values) / len(f1_values)) if f1_values else 0.0,
            "weighted_f1": (weighted_f1_numerator / weighted_support) if weighted_support else 0.0,
        }
    g2_summary = _multiclass_summary(g2_counts)
    g1_summary = _multiclass_summary(g1_counts)
    def _multilabel_summary(counts_map: dict[str, dict[str, int]], exact_match_count: int, evaluated_total: int) -> dict[str, float]:
        if not counts_map:
            return {
                "exact_match_accuracy": 0.0,
                "micro_precision": 0.0,
                "micro_recall": 0.0,
                "micro_f1": 0.0,
                "macro_f1": 0.0,
            }
        macro_f1_values: list[float] = []
        total_tp = 0
        total_fp = 0
        total_fn = 0
        for counts in counts_map.values():
            tp = counts["tp"]
            fp = counts["fp"]
            fn = counts["fn"]
            total_tp += tp
            total_fp += fp
            total_fn += fn
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            macro_f1_values.append((2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0)
        micro_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
        micro_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
        micro_f1 = (
            2 * micro_precision * micro_recall / (micro_precision + micro_recall)
            if (micro_precision + micro_recall) else 0.0
        )
        return {
            "exact_match_accuracy": (exact_match_count / evaluated_total) if evaluated_total else 0.0,
            "micro_precision": micro_precision,
            "micro_recall": micro_recall,
            "micro_f1": micro_f1,
            "macro_f1": (sum(macro_f1_values) / len(macro_f1_values)) if macro_f1_values else 0.0,
        }
    return {
        "g1_accuracy": (g1_correct / total) if total else 0.0,
        "g1_macro_f1": g1_summary["macro_f1"],
        "g1_weighted_f1": g1_summary["weighted_f1"],
        "g2_accuracy": (g2_correct / total) if total else 0.0,
        "g2_macro_f1": g2_summary["macro_f1"],
        "g2_weighted_f1": g2_summary["weighted_f1"],
        "flags": _multilabel_summary(flag_counts, flag_exact_match, total),
        "intent_families": _multilabel_summary(intent_family_counts, intent_family_exact_match, intent_family_evaluated_total),
        "intent_phrases": _multilabel_summary(intent_phrase_counts, intent_phrase_exact_match, intent_phrase_evaluated_total),
        "total_rows": total,
        "g1_predicted_indices": dict(g1_predictions),
        "g2_predicted_indices": dict(g2_predictions),
    }


def _split_batch_for_training(batch: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    tensor_batch: dict[str, Any] = {}
    meta_batch: dict[str, Any] = {}
    for key, value in batch.items():
        if torch is not None and isinstance(value, torch.Tensor):
            tensor_batch[key] = value
        else:
            meta_batch[key] = value
    return tensor_batch, meta_batch


def _append_batch_debug(
    path: Path,
    *,
    epoch_index: int,
    total_epochs: int,
    batch_index: int,
    total_batches: int,
    loss_value: float,
    avg_loss: float,
    batch_time: float,
    loss_breakdown: dict[str, float],
    g2_confusion: dict[str, int],
    rows: list[dict[str, Any]],
) -> None:
    payload = {
        "epoch": epoch_index + 1,
        "epochs_total": total_epochs,
        "batch": batch_index,
        "batches_total": total_batches,
        "loss": loss_value,
        "avg_loss": avg_loss,
        "batch_time_seconds": batch_time,
        "loss_breakdown": loss_breakdown,
        "g2_confusion": g2_confusion,
        "rows": rows,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def train_slm_classifier(
    dataset_path: Path = CANONICAL_DATASET,
    model_dir: Path | None = None,
    *,
    core: str | None = None,
    enable_training: bool = False,
    incremental_source_path: Path | None = None,
    epochs: int | None = None,
    batch_size: int | None = None,
    max_length: int | None = None,
    device: str | None = None,
    freeze_backbone: bool | None = None,
    unfreeze_top_layers: int | None = None,
    learning_rate: float | None = None,
    head_learning_rate: float | None = None,
    g1_loss_weight: float | None = None,
    g2_loss_weight: float | None = None,
    flag_loss_weight: float | None = None,
    intent_family_loss_weight: float | None = None,
    intent_phrase_loss_weight: float | None = None,
    g2_focal_gamma: float | None = None,
    intent_family_focal_gamma: float | None = None,
    intent_phrase_focal_gamma: float | None = None,
    flag_max_pos_weight: float | None = None,
    intent_family_max_pos_weight: float | None = None,
    intent_phrase_max_pos_weight: float | None = None,
    train_intent_heads: bool | None = None,
    resume_if_available: bool | None = None,
    train_on_all_data: bool = False,
    checkpoint_every_batches: int | None = None,
    balanced_sampling: bool | None = None,
) -> dict[str, Any]:
    resolved_core = resolve_core(core)
    model_dir = model_dir or model_dir_for_core(resolved_core)
    rows: list[dict[str, Any]] = []
    train_rows: list[dict[str, Any]] = []
    test_rows: list[dict[str, Any]] = []
    paths = _paths_for_core(resolved_core, model_dir=model_dir)
    incremental_mode = incremental_source_path is not None
    if incremental_mode:
        incremental_source_path = Path(incremental_source_path)
        if not incremental_source_path.exists():
            raise FileNotFoundError(f"Incremental source not found: {incremental_source_path}")
        rows = expand_authoring_rows(incremental_source_path)
        validate_dataset_rows(rows)
        train_rows = list(rows)
        test_rows = []
        train_on_all_data = True
    elif not dataset_path.exists():
        try:
            from training.slm_classifier.source_normalizer import write_canonical_jsonl_with_metadata

            write_canonical_jsonl_with_metadata(target_path=dataset_path)
        except ValueError:
            if enable_training:
                raise
    if not incremental_mode and dataset_path.exists():
        rows = _iter_rows(dataset_path)
    if incremental_mode:
        pass
    elif rows:
        if train_on_all_data:
            train_rows = list(rows)
            test_rows = []
        else:
            splits = load_dataset_splits()
            train_rows = select_rows_for_split(rows, "train", splits)
            test_rows = select_rows_for_split(rows, "test", splits)
            if not train_rows:
                raise ValueError(
                    "No train rows were selected for training. Rebuild dataset splits or pass --train-on-all-data explicitly."
                )
    elif enable_training:
        raise ValueError(f"No rows available for SLM training: {dataset_path}")
    if enable_training and not train_on_all_data and not test_rows:
        raise ValueError(
            "No test rows were selected for training. Rebuild dataset splits or pass --train-on-all-data explicitly."
        )
    model_dir.mkdir(parents=True, exist_ok=True)
    if incremental_mode and paths["label_vocab"].exists():
        if not paths["state"].exists():
            raise FileNotFoundError(
                f"Incremental training requires existing trained weights: {paths['state']}"
            )
        label_vocab = json.loads(paths["label_vocab"].read_text(encoding="utf-8"))
        _validate_rows_against_label_vocab(train_rows, label_vocab)
    elif incremental_mode:
        raise FileNotFoundError(
            f"Incremental training requires an existing model label vocab: {paths['label_vocab']}"
        )
    else:
        ensure_label_vocab(model_dir=model_dir, core=resolved_core)
    config = _training_defaults(resolved_core)
    if epochs is not None:
        config["epochs"] = int(epochs)
    if batch_size is not None:
        config["batch_size"] = int(batch_size)
    if max_length is not None:
        config["max_length"] = int(max_length)
    if device is not None:
        config["device"] = str(device)
    if freeze_backbone is not None:
        config["freeze_backbone"] = bool(freeze_backbone)
    if unfreeze_top_layers is not None:
        config["unfreeze_top_layers"] = max(int(unfreeze_top_layers), 0)
    if learning_rate is not None:
        config["learning_rate"] = float(learning_rate)
    if head_learning_rate is not None:
        config["head_learning_rate"] = float(head_learning_rate)
    if g1_loss_weight is not None:
        config["g1_loss_weight"] = float(g1_loss_weight)
    if g2_loss_weight is not None:
        config["g2_loss_weight"] = float(g2_loss_weight)
    if flag_loss_weight is not None:
        config["flag_loss_weight"] = float(flag_loss_weight)
    if flag_max_pos_weight is not None:
        config["flag_max_pos_weight"] = float(flag_max_pos_weight)
    if intent_family_max_pos_weight is not None:
        config["intent_family_max_pos_weight"] = float(intent_family_max_pos_weight)
    if intent_family_loss_weight is not None:
        config["intent_family_loss_weight"] = float(intent_family_loss_weight)
    if intent_phrase_max_pos_weight is not None:
        config["intent_phrase_max_pos_weight"] = float(intent_phrase_max_pos_weight)
    if intent_phrase_loss_weight is not None:
        config["intent_phrase_loss_weight"] = float(intent_phrase_loss_weight)
    if g2_focal_gamma is not None:
        config["g2_focal_gamma"] = float(g2_focal_gamma)
    if intent_family_focal_gamma is not None:
        config["intent_family_focal_gamma"] = float(intent_family_focal_gamma)
    if intent_phrase_focal_gamma is not None:
        config["intent_phrase_focal_gamma"] = float(intent_phrase_focal_gamma)
    if train_intent_heads is not None:
        config["train_intent_heads"] = bool(train_intent_heads)
    if resume_if_available is not None:
        config["resume_if_available"] = bool(resume_if_available)
    if checkpoint_every_batches is not None:
        config["checkpoint_every_batches"] = int(checkpoint_every_batches)
    if balanced_sampling is not None:
        config["balanced_sampling"] = bool(balanced_sampling)
    if incremental_mode:
        config["resume_if_available"] = True if resume_if_available is None else bool(resume_if_available)
        config["train_on_all_data"] = True
        config["incremental_training"] = True
        config["incremental_source_path"] = str(incremental_source_path)
    log_prefix = f"[SLM:{resolved_core}]"
    if bool(config.get("balanced_sampling", False)):
        max_balanced_epochs = int(config.get("balanced_sampling_max_epochs", 4) or 4)
        if int(config["epochs"]) > max_balanced_epochs:
            print(
                f"{log_prefix} config: balanced_sampling_epoch_cap "
                f"requested_epochs={config['epochs']} capped_epochs={max_balanced_epochs}"
            )
            config["epochs"] = max_balanced_epochs
        if bool(config.get("balanced_sampling_force_frozen_backbone", True)):
            if not bool(config.get("freeze_backbone", False)) or int(config.get("unfreeze_top_layers", 0) or 0) > 0:
                print(
                    f"{log_prefix} config: balanced_sampling_freeze_backbone "
                    "forcing freeze_backbone=true unfreeze_top_layers=0"
                )
            config["freeze_backbone"] = True
            config["unfreeze_top_layers"] = 0
    config["train_on_all_data"] = bool(train_on_all_data)
    config["incremental_training"] = bool(incremental_mode)
    if incremental_source_path is not None:
        config["incremental_source_path"] = str(incremental_source_path)
    paths["training_config"].write_text(json.dumps(config, indent=2), encoding="utf-8")

    trained = False
    training_backend = "metadata_only"
    metadata = _build_training_metadata(rows, train_rows, test_rows, trained=False, training_backend=training_backend, core=resolved_core)

    if enable_training:
        if not (AutoModel and AutoTokenizer and torch and nn and DataLoader):
            raise RuntimeError("Transformers/Torch dependencies are not available for SLM training.")
        startup_time = time.perf_counter()
        device = _device(config["model_name"], config.get("device", "auto"))
        print(f"{log_prefix} init: selected_device={device.type} requested_device={config.get('device', 'auto')}")
        label_vocab = json.loads(paths["label_vocab"].read_text(encoding="utf-8"))
        tokenizer_start = time.perf_counter()
        print(f"{log_prefix} init: loading_tokenizer model={config['model_name']}")
        tokenizer = _load_training_tokenizer(config["model_name"], model_dir)
        print(f"{log_prefix} init: tokenizer_ready elapsed={time.perf_counter() - tokenizer_start:.2f}s")
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        dataset_start = time.perf_counter()
        print(f"{log_prefix} init: building_datasets")
        test_dataset = CanonicalSLMDataset(test_rows, tokenizer, label_vocab, config["max_length"])
        batch_debug_path = paths["batch_debug"]
        if bool(config.get("write_batch_debug", True)):
            batch_debug_path.write_text("", encoding="utf-8")
        if bool(config.get("balanced_sampling", True)):
            print(f"{log_prefix} init: balanced_sampler_ready samples={len(train_rows)}")
        train_loader = _build_epoch_train_loader(train_rows, tokenizer, label_vocab, config, epoch_index=0)
        test_loader = DataLoader(test_dataset, batch_size=config["batch_size"], shuffle=False)
        print(
            f"{log_prefix} init: dataloaders_ready train_batches={len(train_loader)} "
            f"test_batches={len(test_loader)} elapsed={time.perf_counter() - dataset_start:.2f}s"
        )
        model_start = time.perf_counter()
        print(f"{log_prefix} init: loading_model model={config['model_name']}")
        print(f"{log_prefix} init: constructing_model_backbone")
        intent_head_enabled = bool(config.get("train_intent_heads", False))
        model = MultiHeadSLMClassifier(
            config["model_name"],
            num_g1_labels=len(label_vocab["g1"]),
            num_g2_labels=len(label_vocab["g2"]),
            num_flags=len(label_vocab["flags"]),
            num_intent_families=len(label_vocab.get("intent_families", [])) if intent_head_enabled else 0,
            num_intent_phrases=len(label_vocab.get("intent_phrases", [])) if intent_head_enabled else 0,
            num_intent_rules=len(label_vocab.get("intent_families", [])),
            num_phrase_triggers=len(label_vocab.get("g2", [])),
            local_files_only=bool(config.get("local_files_only", True)),
        )
        _apply_tokenizer_padding_to_model(model, tokenizer)
        print(f"{log_prefix} init: backbone_ready elapsed={time.perf_counter() - model_start:.2f}s")
        device_move_start = time.perf_counter()
        print(f"{log_prefix} init: moving_model_to_device device={device.type}")
        model = model.float().to(device)
        print(f"{log_prefix} init: model_on_device_ready elapsed={time.perf_counter() - device_move_start:.2f}s")
        print(f"{log_prefix} init: model_ready total_elapsed={time.perf_counter() - model_start:.2f}s")
        resumed_from_existing = False
        previous_metadata = _existing_training_metadata(model_dir)
        if bool(config.get("resume_if_available", True)) and paths["state"].exists():
            state_dict = torch.load(paths["state"], map_location=device)
            if _checkpoint_is_compatible(state_dict):
                filtered_state_dict, skipped_state_keys = _filter_compatible_state_dict(model, state_dict)
                model.load_state_dict(filtered_state_dict, strict=False)
                resumed_from_existing = True
                print(f"{log_prefix} init: resumed_from_checkpoint path={paths['state']}")
                if skipped_state_keys:
                    print(f"{log_prefix} init: skipped_mismatched_checkpoint_keys count={len(skipped_state_keys)}")
            else:
                print(f"{log_prefix} init: skipped_resume_incompatible_checkpoint path={paths['state']}")
        actual_unfrozen_top_layers = 0
        requested_unfreeze_top_layers = int(config.get("unfreeze_top_layers", 0) or 0)
        if requested_unfreeze_top_layers > 0:
            actual_unfrozen_top_layers = _unfreeze_top_layers(model, requested_unfreeze_top_layers)
            print(
                f"{log_prefix} init: backbone_partially_unfrozen=true "
                f"requested_top_layers={requested_unfreeze_top_layers} "
                f"actual_top_layers={actual_unfrozen_top_layers}"
            )
        elif bool(config.get("freeze_backbone", True)):
            _freeze_backbone(model)
            print(f"{log_prefix} init: backbone_frozen=true")
        else:
            _unfreeze_backbone(model)
            print(f"{log_prefix} init: backbone_frozen=false")
        g2_weights = None
        if bool(config.get("use_class_weights", False)):
            g2_weights = torch.tensor(
                _compute_class_weights(train_rows, "g2", label_vocab["g2"]),
                dtype=torch.float32,
                device=device,
            )
        g1_weights = None
        if bool(config.get("use_class_weights", False)):
            g1_weights = torch.tensor(
                _compute_class_weights(train_rows, "g1", label_vocab["g1"]),
                dtype=torch.float32,
                device=device,
            )
        flag_weights = torch.tensor(
            _compute_list_multilabel_pos_weight(
                train_rows,
                label_vocab["flags"],
                "flags",
                max_pos_weight=config.get("flag_max_pos_weight"),
            ),
            dtype=torch.float32,
            device=device,
        ) if label_vocab.get("flags") else None
        g1_loss_fn = torch.nn.CrossEntropyLoss(weight=g1_weights)
        g2_loss_fn = MulticlassFocalLoss(gamma=float(config.get("g2_focal_gamma", 2.0)), weight=g2_weights)
        flag_loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=flag_weights)
        intent_family_weights = torch.tensor(
            _compute_list_multilabel_pos_weight(
                train_rows,
                label_vocab.get("intent_families", []),
                "intent_families",
                max_pos_weight=config.get("intent_family_max_pos_weight"),
            ),
            dtype=torch.float32,
            device=device,
        ) if intent_head_enabled and label_vocab.get("intent_families") else None
        intent_family_loss_fn = (
            BinaryFocalLoss(gamma=float(config.get("intent_family_focal_gamma", 2.0)), pos_weight=intent_family_weights)
            if intent_head_enabled and label_vocab.get("intent_families") else None
        )
        intent_phrase_weights = torch.tensor(
            _compute_list_multilabel_pos_weight(
                train_rows,
                label_vocab.get("intent_phrases", []),
                "intent_phrases",
                max_pos_weight=config.get("intent_phrase_max_pos_weight"),
            ),
            dtype=torch.float32,
            device=device,
        ) if intent_head_enabled and label_vocab.get("intent_phrases") else None
        intent_phrase_loss_fn = (
            BinaryFocalLoss(gamma=float(config.get("intent_phrase_focal_gamma", 2.0)), pos_weight=intent_phrase_weights)
            if intent_head_enabled and label_vocab.get("intent_phrases") else None
        )
        backbone_parameters = [
            parameter for parameter in _model_backbone(model).parameters()
            if parameter.requires_grad
        ]
        head_modules = [
            model.g1_classifier,
            model.g2_classifier,
            model.flag_classifier,
        ]
        if getattr(model, "intent_family_classifier", None) is not None:
            head_modules.append(model.intent_family_classifier)
        if getattr(model, "intent_phrase_classifier", None) is not None:
            head_modules.append(model.intent_phrase_classifier)
        head_parameters = [
            parameter
            for module in head_modules
            for parameter in module.parameters()
            if parameter.requires_grad
        ]
        optimizer_param_groups: list[dict[str, Any]] = []
        if backbone_parameters:
            optimizer_param_groups.append(
                {
                    "params": backbone_parameters,
                    "lr": float(config["learning_rate"]),
                }
            )
        if head_parameters:
            optimizer_param_groups.append(
                {
                    "params": head_parameters,
                    "lr": float(config.get("head_learning_rate", config["learning_rate"])),
                }
            )
        optimizer = torch.optim.AdamW(
            optimizer_param_groups,
            weight_decay=config["weight_decay"],
        )
        trainable_parameters = backbone_parameters + head_parameters

        best_dev_loss = None
        resume_epoch_index = 0
        resume_batch_index = 0
        print(
            f"{log_prefix} training start: device={device.type} train_rows={len(train_rows)} "
            f"test_rows={len(test_rows)} batch_size={config['batch_size']} "
            f"max_length={config['max_length']} requested_device={config.get('device', 'auto')} "
            f"backbone_learning_rate={config['learning_rate']} "
            f"head_learning_rate={config.get('head_learning_rate', config['learning_rate'])} "
            f"freeze_backbone={config.get('freeze_backbone', True)} "
            f"unfreeze_top_layers={config.get('unfreeze_top_layers', 0)} "
            f"resume_if_available={config.get('resume_if_available', True)} "
            f"balanced_sampling={config.get('balanced_sampling', True)} "
            f"checkpoint_every_batches={config.get('checkpoint_every_batches', 0)}"
        )
        print(
            f"{log_prefix} dataset summary: total_rows={len(rows)} "
            f"train_rows={len(train_rows)} test_rows={len(test_rows)} "
            f"dataset_fingerprint={metadata['dataset_fingerprint']}"
        )
        if bool(config.get("resume_if_available", True)) and paths["checkpoint"].exists():
            checkpoint_payload = torch.load(paths["checkpoint"], map_location=device)
            if _checkpoint_payload_is_compatible(checkpoint_payload):
                filtered_state_dict, skipped_state_keys = _filter_compatible_state_dict(model, checkpoint_payload["model_state"])
                model.load_state_dict(filtered_state_dict, strict=False)
                optimizer_state = checkpoint_payload.get("optimizer_state")
                if isinstance(optimizer_state, dict):
                    print(
                        f"{log_prefix} init: skipped_optimizer_state_restore "
                        "model weights were resumed, but optimizer state restore is disabled for compatibility."
                    )
                best_dev_loss = checkpoint_payload.get("best_test_loss")
                checkpoint_dataset_fingerprint = str(checkpoint_payload.get("dataset_fingerprint", ""))
                current_dataset_fingerprint = str(metadata["dataset_fingerprint"])
                if checkpoint_dataset_fingerprint and checkpoint_dataset_fingerprint != current_dataset_fingerprint:
                    resume_epoch_index = 0
                    resume_batch_index = 0
                    print(
                        f"{log_prefix} init: checkpoint_dataset_changed "
                        f"saved_fingerprint={checkpoint_dataset_fingerprint} "
                        f"current_fingerprint={current_dataset_fingerprint} "
                        "reusing model weights but resetting epoch/batch progress."
                    )
                else:
                    resume_epoch_index = int(checkpoint_payload.get("epoch_index", 0))
                    resume_batch_index = int(checkpoint_payload.get("batch_index", 0))
                resumed_from_existing = True
                print(
                    f"{log_prefix} init: resumed_from_training_checkpoint path={paths['checkpoint']} "
                    f"epoch={resume_epoch_index + 1} batch={resume_batch_index}"
                )
                if skipped_state_keys:
                    print(f"{log_prefix} init: skipped_mismatched_checkpoint_keys count={len(skipped_state_keys)}")
            else:
                print(f"{log_prefix} init: skipped_resume_incompatible_training_checkpoint path={paths['checkpoint']}")
        print(f"{log_prefix} init: startup_complete elapsed={time.perf_counter() - startup_time:.2f}s")
        for epoch_index in range(resume_epoch_index, config["epochs"]):
            train_loader = _build_epoch_train_loader(train_rows, tokenizer, label_vocab, config, epoch_index=epoch_index)
            model.train()
            epoch_start = time.perf_counter()
            running_loss = 0.0
            print(f"{log_prefix} epoch {epoch_index + 1}/{config['epochs']} start")
            for batch_index, batch in enumerate(train_loader, start=1):
                if epoch_index == resume_epoch_index and resume_batch_index and batch_index <= resume_batch_index:
                    continue
                batch_start = time.perf_counter()
                tensor_batch, meta_batch = _split_batch_for_training(batch)
                tensor_batch = {key: value.to(device) for key, value in tensor_batch.items()}
                optimizer.zero_grad()
                outputs = model(
                    input_ids=tensor_batch["input_ids"],
                    attention_mask=tensor_batch["attention_mask"],
                    intent_rule_features=tensor_batch["intent_rule_features"],
                    phrase_trigger_features=tensor_batch["phrase_trigger_features"],
                )
                loss = _compute_loss(
                    outputs,
                    tensor_batch,
                    g1_loss_fn,
                    g2_loss_fn,
                    flag_loss_fn,
                    intent_family_loss_fn,
                    intent_phrase_loss_fn,
                    g1_loss_weight=float(config.get("g1_loss_weight", 0.2)),
                    g2_loss_weight=float(config.get("g2_loss_weight", 2.0)),
                    flag_loss_weight=float(config.get("flag_loss_weight", 0.45)),
                    intent_family_loss_weight=float(config.get("intent_family_loss_weight", 0.15)),
                    intent_phrase_loss_weight=float(config.get("intent_phrase_loss_weight", 0.10)),
                )
                if not torch.isfinite(loss):
                    logits = outputs["g2_logits"].detach()
                    labels = tensor_batch["g2_labels"].detach()
                    print(
                        f"{log_prefix} epoch {epoch_index + 1} batch {batch_index}/{len(train_loader)} "
                        f"non_finite_loss_detected loss={loss.item()}"
                    )
                    raise RuntimeError(
                        "Non-finite loss detected during training. "
                        f"logits_finite={bool(torch.isfinite(logits).all().item())} "
                        f"logits_min={float(torch.nan_to_num(logits.float(), nan=0.0).min().item()):.6f} "
                        f"logits_max={float(torch.nan_to_num(logits.float(), nan=0.0).max().item()):.6f} "
                        f"labels_min={int(labels.min().item())} "
                        f"labels_max={int(labels.max().item())}"
                    )
                loss.backward()
                gradient_clip_norm = float(config.get("gradient_clip_norm", 0.0) or 0.0)
                if gradient_clip_norm > 0.0:
                    torch.nn.utils.clip_grad_norm_(trainable_parameters, max_norm=gradient_clip_norm)
                optimizer.step()
                running_loss += float(loss.item())
                if batch_index == 1 or batch_index % int(config.get("log_every_batches", 25)) == 0 or batch_index == len(train_loader):
                    avg_loss = running_loss / batch_index
                    batch_time = time.perf_counter() - batch_start
                    print(
                        f"{log_prefix} epoch {epoch_index + 1} batch {batch_index}/{len(train_loader)} "
                        f"loss={loss.item():.4f} avg_loss={avg_loss:.4f} "
                        f"batch_time={batch_time:.2f}s"
                    )
                    if bool(config.get("write_batch_debug", True)) and float(loss.item()) >= float(config.get("batch_debug_loss_threshold", 9.0)):
                        loss_breakdown = _compute_loss_breakdown(
                            outputs,
                            tensor_batch,
                            g1_loss_fn,
                            g2_loss_fn,
                            flag_loss_fn,
                            intent_family_loss_fn,
                            intent_phrase_loss_fn,
                        )
                        row_count = len(meta_batch.get("sample_id", []))
                        g2_logits = outputs["g2_logits"].detach().cpu()
                        g2_probs = torch.softmax(g2_logits, dim=-1).tolist()
                        g1_pred_indices = torch.argmax(outputs["g1_logits"], dim=-1).detach().cpu().tolist()
                        flag_probs = torch.sigmoid(outputs["flag_logits"].detach().cpu()).tolist()
                        g2_pred_indices = torch.argmax(outputs["g2_logits"], dim=-1).detach().cpu().tolist()
                        g2_gold_indices = tensor_batch["g2_labels"].detach().cpu().tolist()
                        g2_confusion_counter: Counter[str] = Counter()
                        debug_rows: list[dict[str, Any]] = []
                        for idx in range(row_count):
                            gold_g2 = str(meta_batch.get("g2_text", [""])[idx])
                            pred_g2 = str(label_vocab["g2"][g2_pred_indices[idx]])
                            g2_confusion_counter[f"{gold_g2}->{pred_g2}"] += 1
                            top3_indices = sorted(
                                range(len(g2_probs[idx])),
                                key=lambda item: float(g2_probs[idx][item]),
                                reverse=True,
                            )[:3]
                            top3_scores = {
                                str(label_vocab["g2"][top_idx]): float(g2_probs[idx][top_idx])
                                for top_idx in top3_indices
                            }
                            debug_rows.append(
                                {
                                    "sample_id": str(meta_batch.get("sample_id", [""])[idx]),
                                    "question": str(meta_batch.get("question", [""])[idx]),
                                    "context": str(meta_batch.get("context", [""])[idx]),
                                    "gold_g1": str(meta_batch.get("g1_text", [""])[idx]),
                                    "pred_g1": str(label_vocab["g1"][g1_pred_indices[idx]]),
                                    "gold_g2": gold_g2,
                                    "pred_g2": pred_g2,
                                    "g2_top3": top3_scores,
                                    "gold_g2_probability": float(g2_probs[idx][g2_gold_indices[idx]]),
                                    "flag_scores": {
                                        str(flag): float(flag_probs[idx][flag_idx])
                                        for flag_idx, flag in enumerate(label_vocab["flags"])
                                    },
                                    "intent_family_scores": {
                                        str(intent_family): float(score)
                                        for intent_family, score in zip(
                                            label_vocab.get("intent_families", []),
                                            torch.sigmoid(outputs["intent_family_logits"].detach().cpu())[idx].tolist(),
                                        )
                                    } if "intent_family_logits" in outputs else {},
                                    "flags": json.loads(str(meta_batch.get("flags_json", ["{}"])[idx])),
                                }
                            )
                        _append_batch_debug(
                            batch_debug_path,
                            epoch_index=epoch_index,
                            total_epochs=int(config["epochs"]),
                            batch_index=batch_index,
                            total_batches=len(train_loader),
                            loss_value=float(loss.item()),
                            avg_loss=float(avg_loss),
                            batch_time=float(batch_time),
                            loss_breakdown=loss_breakdown,
                            g2_confusion=dict(g2_confusion_counter),
                            rows=debug_rows,
                        )
                checkpoint_every_batches = int(config.get("checkpoint_every_batches", 0) or 0)
                if checkpoint_every_batches > 0 and batch_index % checkpoint_every_batches == 0:
                    _save_training_checkpoint(
                        path=paths["checkpoint"],
                        model_state=model.state_dict(),
                        optimizer_state=optimizer.state_dict(),
                        epoch_index=epoch_index,
                        batch_index=batch_index,
                        best_test_loss=best_dev_loss,
                        config=config,
                        dataset_fingerprint_value=metadata["dataset_fingerprint"],
                    )
                    torch.save(model.state_dict(), paths["state"])
                    latest_path = model_dir / "pytorch_model.latest.bin"
                    torch.save(model.state_dict(), latest_path)
                    print(
                        f"{log_prefix} checkpoint saved: batch={batch_index}/{len(train_loader)} "
                        f"path={paths['state']} latest={latest_path}"
                    )
            test_loss = _evaluate_loss(
                model,
                test_loader,
                g1_loss_fn,
                g2_loss_fn,
                flag_loss_fn,
                intent_family_loss_fn,
                intent_phrase_loss_fn,
                g1_loss_weight=float(config.get("g1_loss_weight", 0.2)),
                g2_loss_weight=float(config.get("g2_loss_weight", 2.0)),
                flag_loss_weight=float(config.get("flag_loss_weight", 0.45)),
                intent_family_loss_weight=float(config.get("intent_family_loss_weight", 0.15)),
                intent_phrase_loss_weight=float(config.get("intent_phrase_loss_weight", 0.10)),
            ) if len(test_rows) else 0.0
            print(
                f"{log_prefix} epoch {epoch_index + 1} summary "
                f"train_avg_loss={running_loss / max(len(train_loader), 1):.4f} "
                f"test_loss={test_loss:.4f} elapsed={time.perf_counter() - epoch_start:.2f}s"
            )
            should_checkpoint = not len(test_rows) or best_dev_loss is None or test_loss < best_dev_loss
            if should_checkpoint:
                best_dev_loss = test_loss
                _save_training_checkpoint(
                    path=paths["checkpoint"],
                    model_state=model.state_dict(),
                    optimizer_state=optimizer.state_dict(),
                    epoch_index=epoch_index + 1,
                    batch_index=0,
                    best_test_loss=best_dev_loss,
                    config=config,
                    dataset_fingerprint_value=metadata["dataset_fingerprint"],
                )
                torch.save(model.state_dict(), paths["state"])
                print(f"{log_prefix} checkpoint saved: {paths['state']}")

        tokenizer.save_pretrained(model_dir)
        trained = paths["state"].exists()
        training_backend = "transformers"
        metadata = _build_training_metadata(rows, train_rows, test_rows, trained=trained, training_backend=training_backend, core=resolved_core)
        metadata["test_loss"] = best_dev_loss
        metadata["device"] = device.type
        metadata["freeze_backbone"] = bool(config.get("freeze_backbone", True))
        metadata["unfreeze_top_layers"] = int(config.get("unfreeze_top_layers", 0) or 0)
        metadata["actual_unfrozen_top_layers"] = int(actual_unfrozen_top_layers)
        metadata["resume_if_available"] = bool(config.get("resume_if_available", True))
        metadata["balanced_sampling"] = bool(config.get("balanced_sampling", False))
        metadata["balanced_sampling_max_epochs"] = int(config.get("balanced_sampling_max_epochs", 4) or 4)
        metadata["train_intent_heads"] = bool(config.get("train_intent_heads", False))
        metadata["cross_feature_fusion_version"] = int(config.get("cross_feature_fusion_version", 0))
        metadata["g1_loss_weight"] = float(config.get("g1_loss_weight", 1.0))
        metadata["g2_loss_weight"] = float(config.get("g2_loss_weight", 2.0))
        metadata["flag_loss_weight"] = float(config.get("flag_loss_weight", 0.45))
        metadata["intent_family_loss_weight"] = float(config.get("intent_family_loss_weight", 0.15))
        metadata["intent_phrase_loss_weight"] = float(config.get("intent_phrase_loss_weight", 0.10))
        metadata["flag_max_pos_weight"] = float(config.get("flag_max_pos_weight", 10.0))
        metadata["intent_family_max_pos_weight"] = float(config.get("intent_family_max_pos_weight", 10.0))
        metadata["intent_phrase_max_pos_weight"] = float(config.get("intent_phrase_max_pos_weight", 10.0))
        metadata["g2_focal_gamma"] = float(config.get("g2_focal_gamma", 2.0))
        metadata["intent_family_focal_gamma"] = float(config.get("intent_family_focal_gamma", 2.0))
        metadata["intent_phrase_focal_gamma"] = float(config.get("intent_phrase_focal_gamma", 2.0))
        metadata["head_learning_rate"] = float(config.get("head_learning_rate", config["learning_rate"]))
        metadata["train_on_all_data"] = bool(config.get("train_on_all_data", False))
        metadata["incremental_training"] = bool(incremental_mode)
        if incremental_source_path is not None:
            metadata["incremental_source_path"] = str(incremental_source_path)
            metadata["incremental_rows"] = len(train_rows)
        metadata["resumed_from_existing"] = resumed_from_existing
        if len(test_rows):
            gate_eval = _evaluate_gate_accuracy(model, test_loader, label_vocab)
            metadata["test_gate_metrics"] = gate_eval
            g2_predicted = gate_eval.get("g2_predicted_indices", {})
            dominant_g2_share = 0.0
            if gate_eval.get("total_rows", 0):
                dominant_g2_share = max(g2_predicted.values(), default=0) / float(gate_eval["total_rows"])
            metadata["dominant_g2_share"] = dominant_g2_share
            if dominant_g2_share >= 0.9:
                metadata["degenerate_head_warning"] = (
                    "G2 head predictions are dominated by a single class on the dev split. "
                    "This usually indicates a bad checkpoint or collapsed training run."
                )
        if resumed_from_existing:
            metadata["previous_dataset_fingerprint"] = str(previous_metadata.get("dataset_fingerprint", "unknown"))
            metadata["previous_codebook_fingerprint"] = str(previous_metadata.get("codebook_fingerprint", "unknown"))
        print(
            f"{log_prefix} training complete: trained={trained} best_dev_loss={best_dev_loss} "
            f"trained_rows={len(train_rows)} total_rows={len(rows)}"
        )

    paths["metadata"].write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def load_slm_package(model_dir: Path | None = None, core: str | None = None) -> LoadedSLMPackage | None:
    config = load_classifier_runtime_config()
    resolved_dir = model_dir or (config.model_artifact_path if core is None else model_dir_for_core(core))
    metadata_path = resolved_dir / "training_metadata.json"
    label_vocab_path = resolved_dir / "label_vocab.json"
    training_config_path = resolved_dir / "training_config.json"
    if not metadata_path.exists() or not label_vocab_path.exists() or not training_config_path.exists():
        return None
    return LoadedSLMPackage(
        metadata=json.loads(metadata_path.read_text(encoding="utf-8")),
        label_vocab=json.loads(label_vocab_path.read_text(encoding="utf-8")),
        training_config=json.loads(training_config_path.read_text(encoding="utf-8")),
    )


def _load_trained_model(model_dir: Path, package: LoadedSLMPackage) -> tuple[Any, Any]:
    device = _device(
        package.training_config["model_name"],
        package.training_config.get("device", "auto"),
    )
    return _load_trained_model_on_device(model_dir, package, device)


def _run_model_with_device_fallback(model: Any, encoded: dict[str, Any], model_dir: Path, package: LoadedSLMPackage) -> tuple[dict[str, Any], str]:
    try:
        with torch.no_grad():
            return model(**encoded), str(encoded["input_ids"].device)
    except RuntimeError as exc:
        message = str(exc)
        if "MPSNDArrayMatrixMultiplication" not in message and "Placeholder storage has not been allocated on MPS device" not in message:
            raise
        cpu_device = _cpu_device()
        tokenizer, cpu_model = _load_trained_model_on_device(model_dir, package, cpu_device)
        encoded_cpu = {key: value.to(cpu_device) for key, value in encoded.items()}
        with torch.no_grad():
            return cpu_model(**encoded_cpu), "cpu_fallback"


def _load_trained_model_on_device(model_dir: Path, package: LoadedSLMPackage, device: Any) -> tuple[Any, Any]:
    if not (AutoTokenizer and torch and AutoModel and nn):
        raise RuntimeError("Transformers/Torch dependencies are not available for SLM inference.")
    artifact_fusion_version = min(
        int(package.training_config.get("cross_feature_fusion_version", 0)),
        int(package.metadata.get("cross_feature_fusion_version", 0)),
    )
    if artifact_fusion_version < 3:
        raise RuntimeError("SLM artifact predates cross-attention GLU feature fusion and must be retrained.")
    cache_key = (str(model_dir.resolve()), str(device.type))
    cached = _TRAINED_MODEL_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
    except Exception:
        tokenizer = _load_tokenizer(package.training_config["model_name"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    model = MultiHeadSLMClassifier(
        package.training_config["model_name"],
        num_g1_labels=len(package.label_vocab["g1"]),
        num_g2_labels=len(package.label_vocab["g2"]),
        num_flags=len(package.label_vocab["flags"]),
        num_intent_families=len(package.label_vocab.get("intent_families", [])),
        num_intent_phrases=len(package.label_vocab.get("intent_phrases", [])),
        num_intent_rules=len(package.label_vocab.get("intent_families", [])),
        num_phrase_triggers=len(package.label_vocab.get("g2", [])),
        local_files_only=True,
    )
    _apply_tokenizer_padding_to_model(model, tokenizer)
    state_dict = torch.load(model_dir / "pytorch_model.bin", map_location=device)
    filtered_state_dict, _ = _filter_compatible_state_dict(model, state_dict)
    model.load_state_dict(filtered_state_dict, strict=False)
    model = model.float().to(device)
    model.eval()
    loaded = (tokenizer, model)
    _TRAINED_MODEL_CACHE[cache_key] = loaded
    return loaded


def _decision_from_predictions(
    normalized: dict[str, object],
    package: LoadedSLMPackage,
    model_dir: Path,
    g1: str,
    primary_g2: str,
    intent_evidence: dict[str, Any],
    learned_intent: dict[str, Any],
    threshold: float,
) -> GuardrailDecision:
    child_profile = normalized.get("child_profile", {}) if isinstance(normalized.get("child_profile", {}), dict) else {}
    age_band = str(child_profile.get("age_group") or normalized.get("resolved_age_band") or "11-12")
    language = str(normalized.get("language", "en"))
    question = str(normalized.get("text", "")).strip()
    topic = heuristic_classifier.classify_topic(heuristic_classifier.normalize(question))
    recent_context_items = [str(item) for item in normalized.get("recent_context", [])]
    recent_context = " ".join(item for item in recent_context_items if item.strip()) or "none"
    g2_list = [primary_g2 or "GENERIC_INTENT"]
    classifier_output = {
        "schema_version": "2.0.0",
        "question": question,
        "language": language,
        "age_band": age_band,
        "applies_when_flags": runtime_contracts.build_applies_when_flags(question, g1, g2_list),
        "intent_lexicon": {
            **intent_evidence,
            "learned": {
                "predicted_flags": [str(flag) for flag in learned_intent.get("predicted_flags", [])],
                **learned_intent,
            },
        },
        "topic": topic,
        "g1": {"id": g1, "reason": heuristic_classifier.build_g1_reason(g1, g2_list, [], question)},
        "g2": [{"id": g2_id, "reason": heuristic_classifier.build_g2_reasons(g1, g2_list, question, intent_evidence).get(g2_id, "")} for g2_id in g2_list],
    }
    gate_output = runtime_contracts.gate_output_from_classifier(classifier_output)
    g3_packet = gate_output["g3"]
    g4_packet = gate_output["g4"]
    modifiers = list(g3_packet["modifiers"])
    g3 = g3_packet["severity"]
    g4 = g4_packet["action"]
    prompt = heuristic_classifier.build_generated_prompt(age_band, g1, g2_list, g3, modifiers, g4, question)
    contract = gate_mapper.build_prompt_contract(g4, g3, g2_list, age_band, set())
    contract["generated_prompt"] = prompt
    contract["resolved_age_band"] = age_band
    decision_fields = gate_mapper.build_decision_from_g4(g4, g3, g2_list)
    return GuardrailDecision(
        input={"question": question, "age_band": age_band, "language": language, "recent_context": recent_context},
        reason=heuristic_classifier.build_classifier_reason(g1, g2_list, [], question, intent_evidence),
        g1_reason=heuristic_classifier.build_g1_reason(g1, g2_list, [], question),
        g2_reasons=heuristic_classifier.build_g2_reasons(g1, g2_list, question, intent_evidence),
        gl_signals={},
        active_gls=[],
        gates={"G1": g1, "G2": primary_g2, "G3": g3, "G4": g4},
        decision=decision_fields,
        policy_bucket="allowed" if decision_fields["allow_llm"] else "soft_block",
        safety_category=primary_g2,
        response_mode=str(decision_fields["response_mode"]),
        risk_level=str(decision_fields["risk_level"]),
        parent_visible=bool(decision_fields["parent_visible"]),
        confidence=max(
            [float(value) for value in learned_intent.get("family_scores", {}).values()] +
            [float(value) for value in learned_intent.get("phrase_scores", {}).values()],
            default=0.0,
        ),
        guideline_tags=[],
        signals={"topic": topic, "g2_labels": ";".join(g2_list)},
        gate_values={"topic": topic, "G1": g1, "G2": primary_g2, "G3": g3, "G4": g4},
        prompt_contract=contract,
        classifier_metadata={
            "backend": "slm",
            "backend_version": package.metadata.get("model_name", model_name_for_core(package.metadata.get("core_model"))),
            "core_model": package.metadata.get("core_model", DEFAULT_CORE),
            "rollout_mode": load_classifier_runtime_config().rollout_mode,
            "g2_threshold": threshold,
            "model_fingerprint": package.metadata.get("dataset_fingerprint", "unknown"),
            "codebook_fingerprint": package.metadata.get("codebook_fingerprint", "unknown"),
            "dataset_fingerprint": package.metadata.get("dataset_fingerprint", "unknown"),
            "label_vocab_path": str(model_dir / "label_vocab.json"),
            "head_confidences": {
                "intent_lexicon": intent_evidence,
                "intent_lexicon_learned": learned_intent,
            },
            "runtime_classifier_output": classifier_output,
            "trained": bool(package.metadata.get("trained", False)),
            "flags_trained": bool(package.metadata.get("flags_trained", False)),
        },
    )


def build_decision_from_slm(
    normalized: dict[str, object],
    model_dir: Path | None = None,
    core: str | None = None,
    threshold: float = DEFAULT_CLASSIFIER_THRESHOLD,
) -> GuardrailDecision:
    resolved_core = resolve_core(core) if core is not None else None
    resolved_dir = model_dir or (load_classifier_runtime_config().model_artifact_path if resolved_core is None else model_dir_for_core(resolved_core))
    package = load_slm_package(resolved_dir, core=resolved_core)
    if package is None:
        try:
            train_slm_classifier(model_dir=resolved_dir, core=resolved_core, enable_training=False)
        except FileNotFoundError:
            heuristic = heuristic_classifier.classify_heuristic(normalized)
            return heuristic.model_copy(
                update={
                    "classifier_metadata": {
                        **heuristic.classifier_metadata,
                        "backend": "slm",
                        "backend_version": model_name_for_core(resolved_core),
                        "core_model": resolved_core or DEFAULT_CORE,
                        "rollout_mode": load_classifier_runtime_config().rollout_mode,
                        "trained": False,
                        "fallback_reason": "canonical_dataset_not_available",
                        "label_vocab_path": str(resolved_dir / "label_vocab.json"),
                        "thresholds_path": str(resolved_dir / "thresholds.json"),
                    }
                }
            )
        package = load_slm_package(resolved_dir, core=resolved_core)
    if package is None:
        raise FileNotFoundError("SLM model package not available.")
    if not package.metadata.get("trained") or not (resolved_dir / "pytorch_model.bin").exists():
        heuristic = heuristic_classifier.classify_heuristic(normalized)
        return heuristic.model_copy(
            update={
                "classifier_metadata": {
                    **heuristic.classifier_metadata,
                    "backend": "slm",
                    "backend_version": package.metadata.get("model_name", model_name_for_core(package.metadata.get("core_model"))),
                    "core_model": package.metadata.get("core_model", resolved_core or DEFAULT_CORE),
                    "rollout_mode": load_classifier_runtime_config().rollout_mode,
                    "trained": False,
                    "fallback_reason": "trained_weights_not_available",
                    "label_vocab_path": str(resolved_dir / "label_vocab.json"),
                    "thresholds_path": str(resolved_dir / "thresholds.json"),
                }
            }
        )
    try:
        tokenizer, model = _load_trained_model(resolved_dir, package)
    except Exception as exc:
        if bool(package.metadata.get("trained", False)):
            message = str(exc)
            if "must be retrained" in message or "cross-attention GLU feature fusion" in message:
                raise RuntimeError(
                    f"SLM artifact at {resolved_dir} is incompatible with the current model head: {message}"
                ) from exc
        heuristic = heuristic_classifier.classify_heuristic(normalized)
        return heuristic.model_copy(
            update={
                "classifier_metadata": {
                    **heuristic.classifier_metadata,
                    "backend": "slm",
                    "backend_version": package.metadata.get("model_name", model_name_for_core(package.metadata.get("core_model"))),
                    "core_model": package.metadata.get("core_model", resolved_core or DEFAULT_CORE),
                    "rollout_mode": load_classifier_runtime_config().rollout_mode,
                    "trained": bool(package.metadata.get("trained", False)),
                    "fallback_reason": "tokenizer_or_model_load_failed",
                    "fallback_error": str(exc),
                    "label_vocab_path": str(resolved_dir / "label_vocab.json"),
                    "thresholds_path": str(resolved_dir / "thresholds.json"),
                }
            }
        )
    text = _format_classifier_input(
        {
            "question": str(normalized.get("text", "")).strip(),
            "language": str(normalized.get("language", "en")),
            "recent_context": " ".join(str(item) for item in normalized.get("recent_context", [])) or "none",
        }
    )
    encoded = tokenizer(
        text,
        truncation=True,
        padding="max_length",
        max_length=int(package.training_config.get("max_length", 192)),
        return_tensors="pt",
    )
    usage = _classifier_token_usage(encoded)
    recent_context = " ".join(str(item) for item in normalized.get("recent_context", [])) or ""
    encoded["intent_rule_features"] = torch.tensor(
        [
            runtime_contracts.build_intent_family_rule_vector(
                str(normalized.get("text", "")).strip(),
                recent_context,
                list(package.label_vocab.get("intent_families", [])),
            )
        ],
        dtype=torch.float32,
    )
    encoded["phrase_trigger_features"] = torch.tensor(
        [
            runtime_contracts.build_g2_phrase_trigger_vector(
                str(normalized.get("text", "")).strip(),
                recent_context,
                list(package.label_vocab.get("g2", [])),
            )
        ],
        dtype=torch.float32,
    )
    inference_device = _device(
        package.training_config.get("model_name"),
        package.training_config.get("device", "auto"),
    )
    encoded = {key: value.to(inference_device) for key, value in encoded.items()}
    outputs, inference_device = _run_model_with_device_fallback(model, encoded, resolved_dir, package)
    g1_probs = torch.softmax(outputs["g1_logits"], dim=-1).squeeze(0).cpu().tolist()
    g2_primary_probs = torch.softmax(outputs["g2_logits"], dim=-1).squeeze(0).cpu().tolist()
    flag_probs = torch.sigmoid(outputs["flag_logits"]).squeeze(0).cpu().tolist()
    intent_family_probs = (
        torch.sigmoid(outputs["intent_family_logits"]).squeeze(0).cpu().tolist()
        if "intent_family_logits" in outputs else []
    )
    intent_phrase_probs = (
        torch.sigmoid(outputs["intent_phrase_logits"]).squeeze(0).cpu().tolist()
        if "intent_phrase_logits" in outputs else []
    )
    primary_g2 = _decode_g2_predictions(package.label_vocab, g2_primary_probs)
    intent_evidence = runtime_contracts.match_intent_lexicon(
        str(normalized.get("text", "")).strip(),
        recent_context,
    )
    flag_vocab = list(package.label_vocab.get("flags", []))
    predicted_g1 = package.label_vocab["g1"][max(range(len(g1_probs)), key=lambda idx: float(g1_probs[idx]))]
    active_flags = {
        flag: float(flag_probs[idx])
        for idx, flag in enumerate(flag_vocab)
        if float(flag_probs[idx]) >= threshold
    }
    learned_intent_flags = {
        "predicted_flags": [flag for flag in flag_vocab if float(active_flags.get(flag, 0.0)) >= threshold],
        "flag_scores": {flag: float(flag_probs[idx]) for idx, flag in enumerate(flag_vocab)},
        "predicted_intent_families": [
            intent_family
            for idx, intent_family in enumerate(package.label_vocab.get("intent_families", []))
            if float(intent_family_probs[idx]) >= threshold
        ],
        "intent_family_scores": {
            intent_family: float(intent_family_probs[idx])
            for idx, intent_family in enumerate(package.label_vocab.get("intent_families", []))
        },
        "predicted_phrases": [
            intent_phrase
            for idx, intent_phrase in enumerate(package.label_vocab.get("intent_phrases", []))
            if float(intent_phrase_probs[idx]) >= threshold
        ],
        "phrase_scores": {
            intent_phrase: float(intent_phrase_probs[idx])
            for idx, intent_phrase in enumerate(package.label_vocab.get("intent_phrases", []))
        },
    }
    learned_intent = {
        "predicted_families": [],
        "family_scores": {},
        **learned_intent_flags,
    }
    decision = _decision_from_predictions(
        normalized=normalized,
        package=package,
        model_dir=resolved_dir,
        g1=predicted_g1,
        primary_g2=primary_g2,
        intent_evidence=intent_evidence,
        learned_intent=learned_intent,
        threshold=threshold,
    )
    return decision.model_copy(
        update={
            "classifier_metadata": {
                **decision.classifier_metadata,
                "inference_device": inference_device,
                "usage": usage,
                "head_confidences": {
                    **decision.classifier_metadata.get("head_confidences", {}),
                    "flags": {flag: float(flag_probs[idx]) for idx, flag in enumerate(flag_vocab)},
                    "intent_families": {
                        label: float(score)
                        for label, score in zip(package.label_vocab.get("intent_families", []), intent_family_probs)
                    },
                    "intent_phrases": {
                        label: float(score)
                        for label, score in zip(package.label_vocab.get("intent_phrases", []), intent_phrase_probs)
                    },
                    "G1": {label: float(score) for label, score in zip(package.label_vocab["g1"], g1_probs)},
                    "G2_primary": {label: float(score) for label, score in zip(package.label_vocab["g2"], g2_primary_probs)},
                },
            }
        }
    )


def build_decision_from_slm_pure(
    normalized: dict[str, object],
    model_dir: Path | None = None,
    core: str | None = None,
    threshold: float = DEFAULT_CLASSIFIER_THRESHOLD,
) -> GuardrailDecision:
    resolved_core = resolve_core(core) if core is not None else None
    resolved_dir = model_dir or (
        load_classifier_runtime_config().model_artifact_path
        if resolved_core is None else model_dir_for_core(resolved_core)
    )
    package = load_slm_package(resolved_dir, core=resolved_core)
    if package is None:
        raise FileNotFoundError(f"SLM model package not available at {resolved_dir}")
    if not package.metadata.get("trained") or not (resolved_dir / "pytorch_model.bin").exists():
        raise FileNotFoundError(f"Trained SLM weights not available at {resolved_dir}")

    tokenizer, model = _load_trained_model(resolved_dir, package)

    text = _format_classifier_input(
        {
            "question": str(normalized.get("text", "")).strip(),
            "language": str(normalized.get("language", "en")),
            "recent_context": " ".join(str(item) for item in normalized.get("recent_context", [])) or "none",
        }
    )
    encoded = tokenizer(
        text,
        truncation=True,
        padding="max_length",
        max_length=int(package.training_config.get("max_length", 192)),
        return_tensors="pt",
    )
    usage = _classifier_token_usage(encoded)
    recent_context = " ".join(str(item) for item in normalized.get("recent_context", [])) or ""
    encoded["intent_rule_features"] = torch.tensor(
        [
            runtime_contracts.build_intent_family_rule_vector(
                str(normalized.get("text", "")).strip(),
                recent_context,
                list(package.label_vocab.get("intent_families", [])),
            )
        ],
        dtype=torch.float32,
    )
    encoded["phrase_trigger_features"] = torch.tensor(
        [
            runtime_contracts.build_g2_phrase_trigger_vector(
                str(normalized.get("text", "")).strip(),
                recent_context,
                list(package.label_vocab.get("g2", [])),
            )
        ],
        dtype=torch.float32,
    )
    inference_device = _device(
        package.training_config.get("model_name"),
        package.training_config.get("device", "auto"),
    )
    encoded = {key: value.to(inference_device) for key, value in encoded.items()}

    model.eval()
    with torch.no_grad():
        outputs = model(**encoded)

    g1_probs = torch.softmax(outputs["g1_logits"], dim=-1).squeeze(0).cpu().tolist()
    g2_probs = torch.softmax(outputs["g2_logits"], dim=-1).squeeze(0).cpu().tolist()
    flag_probs = torch.sigmoid(outputs["flag_logits"]).squeeze(0).cpu().tolist()
    intent_family_probs = (
        torch.sigmoid(outputs["intent_family_logits"]).squeeze(0).cpu().tolist()
        if "intent_family_logits" in outputs else []
    )
    intent_phrase_probs = (
        torch.sigmoid(outputs["intent_phrase_logits"]).squeeze(0).cpu().tolist()
        if "intent_phrase_logits" in outputs else []
    )
    g1_idx = int(torch.argmax(outputs["g1_logits"], dim=-1).item())
    g2_idx = int(torch.argmax(outputs["g2_logits"], dim=-1).item())
    g1 = package.label_vocab["g1"][g1_idx]
    g2 = package.label_vocab["g2"][g2_idx]

    return GuardrailDecision(
        input={
            "question": str(normalized.get("text", "")).strip(),
            "age_band": "11-12",
            "language": str(normalized.get("language", "en")),
            "recent_context": list(normalized.get("recent_context", [])),
        },
        gates={"G1": g1, "G2": g2},
        gate_values={"G1": g1, "G2": g2},
        policy_bucket="model_only",
        safety_category=g2,
        response_mode="model_only",
        risk_level="model_only",
        parent_visible=False,
        confidence=max((float(score) for score in g2_probs), default=0.0),
        signals={},
        classifier_metadata={
            "backend": "slm_pure",
            "backend_version": package.metadata.get(
                "model_name",
                model_name_for_core(package.metadata.get("core_model")),
            ),
            "core_model": package.metadata.get("core_model", resolved_core or DEFAULT_CORE),
            "trained": bool(package.metadata.get("trained", False)),
            "flags_trained": bool(package.metadata.get("flags_trained", False)),
            "inference_device": str(inference_device),
            "usage": usage,
            "g2_threshold": threshold,
            "label_vocab_path": str(resolved_dir / "label_vocab.json"),
            "head_confidences": {
                "G2": {
                    label: float(score)
                    for label, score in zip(package.label_vocab["g2"], g2_probs)
                },
                "G1": {
                    label: float(score)
                    for label, score in zip(package.label_vocab["g1"], g1_probs)
                },
                "flags": {
                    label: float(score)
                    for label, score in zip(package.label_vocab["flags"], flag_probs)
                },
                "intent_families": {
                    label: float(score)
                    for label, score in zip(package.label_vocab.get("intent_families", []), intent_family_probs)
                },
                "intent_phrases": {
                    label: float(score)
                    for label, score in zip(package.label_vocab.get("intent_phrases", []), intent_phrase_probs)
                },
            },
        },
    )
