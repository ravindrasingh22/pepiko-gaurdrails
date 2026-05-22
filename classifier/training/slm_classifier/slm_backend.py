from __future__ import annotations

import hashlib
import json
import os
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.guardrails import gate_mapper, runtime_contracts, slm_classifier as heuristic_classifier
from app.models.guardrail_decision import GuardrailDecision
from training.slm_classifier.codebook import DOC_CODEBOOK_PATH
from training.slm_classifier.data_pipeline import (
    CANONICAL_DATASET,
    LABEL_VOCAB_PATH,
    build_group_id,
    dataset_fingerprint,
    load_dataset_splits,
    parse_g2_values,
    primary_g2_label,
    select_rows_for_split,
    write_label_vocab,
)
from training.slm_classifier.runtime_config import load_classifier_runtime_config

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
    "smol": {
        "model_name": "HuggingFaceTB/SmolLM2-135M",
        "dir_name": "piku-slm-guardrail-smollm2-135m",
    },
    "llama_guard": {
        "model_name": "meta-llama/Llama-Guard-3-1B",
        "dir_name": "piku-slm-guardrail-llama-guard-3-1b",
    },
    "deberta": {
        "model_name": "microsoft/deberta-v3-xsmall",
        "dir_name": "piku-slm-guardrail-deberta-v3-xsmall",
    },
}
DEFAULT_CORE = "smol"
DEFAULT_CLASSIFIER_THRESHOLD = 0.8
G2_ACTIVATION_THRESHOLD = DEFAULT_CLASSIFIER_THRESHOLD
HIGH_PRIORITY_G2 = {
    "UNSAFE_SEXUAL_CONTENT",
    "GROOMING",
    "COERCIVE_CONTROL",
    "VULN_EXPLOIT",
    "SELF_HARM",
    "DANGEROUS",
    "HATE_GROUP",
    "VIOLENCE",
}

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
    aliases = {
        "smollm2": "smol",
        "smollm2-135m": "smol",
        "llamaguard": "llama_guard",
        "llama-guard": "llama_guard",
        "llama_guard": "llama_guard",
        "llama-guard-3": "llama_guard",
        "llama-guard-3-1b": "llama_guard",
        "deberta-v3-xsmall": "deberta",
        "deberta": "deberta",
    }
    resolved = aliases.get(normalized, normalized)
    if resolved not in CORE_MODELS:
        raise ValueError(f"Unsupported core model: {core}")
    return resolved


def model_name_for_core(core: str | None = None) -> str:
    return str(CORE_MODELS[resolve_core(core)]["model_name"])


def model_dir_for_core(core: str | None = None) -> Path:
    return MODELS_ROOT / str(CORE_MODELS[resolve_core(core)]["dir_name"])


def _paths_for_core(core: str | None = None) -> dict[str, Path]:
    model_dir = model_dir_for_core(core)
    return {
        "model_dir": model_dir,
        "metadata": model_dir / "training_metadata.json",
        "label_vocab": model_dir / "label_vocab.json",
        "state": model_dir / "pytorch_model.bin",
        "training_config": model_dir / "training_config.json",
        "batch_debug": model_dir / "training_batch_debug.jsonl",
    }

def _load_tokenizer(model_name: str) -> Any:
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

def _codebook_fingerprint() -> str:
    return hashlib.sha256(DOC_CODEBOOK_PATH.read_bytes()).hexdigest()[:16]


def _iter_rows(path: Path = CANONICAL_DATASET) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _load_label_vocab() -> dict[str, list[str]]:
    if not LABEL_VOCAB_PATH.exists():
        write_label_vocab(LABEL_VOCAB_PATH)
    return json.loads(LABEL_VOCAB_PATH.read_text(encoding="utf-8"))


def _decode_g2_predictions(
    label_vocab: dict[str, list[str]],
    primary_probs: list[float],
    threshold: float = G2_ACTIVATION_THRESHOLD,
) -> tuple[str, list[str]]:
    g2_labels = list(label_vocab.get("g2", []))
    if not g2_labels:
        return "GENERIC_INTENT", ["GENERIC_INTENT"]
    primary_index = max(range(len(primary_probs)), key=lambda idx: float(primary_probs[idx]))
    primary_g2 = g2_labels[primary_index]
    g2_all = [
        label
        for label, score in zip(g2_labels, primary_probs)
        if float(score) >= threshold
    ]
    if primary_g2 not in g2_all:
        g2_all.insert(0, primary_g2)
    return primary_g2, g2_all


def _ordered_unique(labels: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for label in labels:
        if label not in seen:
            ordered.append(label)
            seen.add(label)
    return ordered


def _fuse_g2_predictions(
    g2_vocab: list[str],
    model_g2_values: list[str],
    primary_g2: str,
    heuristic_g2_values: list[str],
    lexicon_g2_values: list[str],
) -> list[str]:
    saturated_cutoff = max(5, int(len(g2_vocab) * 0.6))
    model_active = [label for label in model_g2_values if label in g2_vocab]
    corroborated = _ordered_unique(
        [label for label in heuristic_g2_values + lexicon_g2_values if label in g2_vocab]
    )
    is_saturated = len(model_active) >= saturated_cutoff

    if is_saturated:
        fused = [label for label in corroborated if label in model_active]
        for label in corroborated:
            if label in HIGH_PRIORITY_G2 and label not in fused:
                fused.append(label)
        if not fused:
            fused = list(corroborated)
    else:
        fused = list(model_active)
        for label in corroborated:
            if label not in fused:
                fused.append(label)

    if primary_g2 in g2_vocab and primary_g2 != "GENERIC_INTENT" and primary_g2 in corroborated and primary_g2 not in fused:
        fused.insert(0, primary_g2)

    if "PERSONAL_DIRECTION" in fused and "NEUTRAL_FACT" in fused:
        fused = [label for label in fused if label != "NEUTRAL_FACT"]

    if not fused:
        if primary_g2 in g2_vocab:
            return [primary_g2]
        return ["GENERIC_INTENT"]
    return _ordered_unique(fused)


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
        "batch_size": 2,
        "epochs": 4,
        "learning_rate": 2e-5,
        "weight_decay": 0.01,
        "g1_loss_weight": 0.0,
        "g2_loss_weight": 2.0,
        "flag_loss_weight": 0.45,
        "train_split": "train",
        "eval_split": "dev",
        "freeze_backbone": False,
        "unfreeze_top_layers": 0,
        "log_every_batches": 25,
        "checkpoint_every_batches": 1000,
        "resume_if_available": False,
        "balanced_sampling": False,
        "train_intent_heads": False,
        "write_batch_debug": True,
        "batch_debug_loss_threshold": 9.0,
    }
    if resolved_core == "smol":
        config["epochs"] = 2
        config["batch_size"] = 2
        config["max_length"] = 128
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
    required_heads = (
        "g1_head.weight",
        "g1_head.bias",
        "g2_head.weight",
        "g2_head.bias",
        "flag_head.weight",
        "flag_head.bias",
    )
    return all(key in state_dict for key in required_heads)


def _filter_compatible_state_dict(model: Any, state_dict: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    model_state = model.state_dict()
    filtered: dict[str, Any] = {}
    skipped: list[str] = []
    for key, value in state_dict.items():
        if key.startswith("applies_when_head."):
            skipped.append(key)
            continue
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
    dev_rows: list[dict[str, Any]],
    trained: bool,
    training_backend: str,
    core: str,
) -> dict[str, Any]:
    return {
        "core_model": core,
        "model_name": model_name_for_core(core),
        "model_type": "slm-multitask-classifier",
        "runtime": "transformers-local",
        "language_scope": "english-first",
        "dataset_rows": len(rows),
        "dataset_fingerprint": dataset_fingerprint(rows),
        "codebook_fingerprint": _codebook_fingerprint(),
        "group_count": len({build_group_id(row) for row in rows}),
        "train_rows": len(train_rows),
        "dev_rows": len(dev_rows),
        "transformers_available": bool(AutoModel and AutoTokenizer and torch and nn),
        "trained": trained,
        "training_backend": training_backend,
        "flags_trained": False,
    }


def _existing_training_metadata(model_dir: Path) -> dict[str, Any]:
    path = model_dir / "training_metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _format_classifier_input(row: dict[str, Any]) -> str:
    return (
        "Classify G1 and G2 for child-safety gating.\n"
        f"Recent context: {row.get('context', row.get('recent_context', 'none')) or 'none'}\n"
        f"Question: {row['question']}"
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


def _compute_list_multilabel_pos_weight(rows: list[dict[str, Any]], vocab: list[str], key: str) -> list[float]:
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
        weights.append(negatives / positives)
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


class CanonicalSLMDataset(Dataset):  # pragma: no cover - exercised through training/inference path
    def __init__(self, rows: list[dict[str, Any]], tokenizer: Any, label_vocab: dict[str, list[str]], max_length: int) -> None:
        self.rows = rows
        self.tokenizer = tokenizer
        self.label_vocab = label_vocab
        self.max_length = max_length
        self.g1_index = _index_map(label_vocab["g1"])
        self.g2_index = _index_map(label_vocab["g2"])
        self.flag_vocab = list(label_vocab.get("flags", []))

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
            "g1_label": torch.tensor(self.g1_index[str(row["g1"])], dtype=torch.long),
            "g2_label": torch.tensor(self.g2_index[primary_g2_label(row.get("g2", []))], dtype=torch.long),
            "flag_labels": torch.tensor(
                [float(bool(row.get("flags", {}).get(label, False))) for label in self.flag_vocab],
                dtype=torch.float32,
            ),
            "sample_id": str(row.get("sample_id", "")),
            "question": str(row.get("question", "")),
            "context": str(row.get("context", "")),
            "g1_text": str(row.get("g1", "")),
            "g2_text": primary_g2_label(row.get("g2", [])),
            "flags_json": json.dumps(row.get("flags", {}), sort_keys=True),
        }


class MultiTaskSLMClassifier(nn.Module):  # pragma: no cover - exercised through training/inference path
    def __init__(self, model_name: str, label_vocab: dict[str, list[str]], *, local_files_only: bool = False) -> None:
        super().__init__()
        self.backbone = AutoModel.from_pretrained(model_name, local_files_only=local_files_only)
        hidden_size = int(self.backbone.config.hidden_size)
        self.dropout = nn.Dropout(0.1)
        self.g1_head = nn.Linear(hidden_size, len(label_vocab["g1"]))
        self.g2_head = nn.Linear(hidden_size, len(label_vocab["g2"]))
        self.flag_head = nn.Linear(hidden_size, len(label_vocab.get("flags", [])))

    def freeze_backbone(self) -> None:
        for parameter in self.backbone.parameters():
            parameter.requires_grad = False

    def unfreeze_backbone(self) -> None:
        for parameter in self.backbone.parameters():
            parameter.requires_grad = True

    def unfreeze_top_layers(self, layer_count: int) -> int:
        self.freeze_backbone()
        requested = max(int(layer_count), 0)
        if requested <= 0:
            return 0

        layer_container = None
        if hasattr(self.backbone, "model") and hasattr(self.backbone.model, "layers"):
            layer_container = self.backbone.model.layers
        elif hasattr(self.backbone, "layers"):
            layer_container = self.backbone.layers
        elif hasattr(self.backbone, "encoder") and hasattr(self.backbone.encoder, "layer"):
            layer_container = self.backbone.encoder.layer

        if layer_container is None:
            raise RuntimeError("Backbone does not expose a supported layer stack for partial unfreezing.")

        total_layers = len(layer_container)
        actual = min(requested, total_layers)
        for layer in list(layer_container)[-actual:]:
            for parameter in layer.parameters():
                parameter.requires_grad = True
        return actual

    def _pool(self, hidden_state: Any, attention_mask: Any) -> Any:
        mask = attention_mask.unsqueeze(-1).to(hidden_state.dtype)
        summed = (hidden_state * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1.0)
        return summed / counts

    def forward(self, input_ids: Any, attention_mask: Any) -> dict[str, Any]:
        outputs = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        pooled = self._pool(outputs.last_hidden_state, attention_mask)
        pooled = pooled.to(self.g1_head.weight.dtype)
        pooled = self.dropout(pooled)
        return {
            "g1_logits": self.g1_head(pooled),
            "g2_logits": self.g2_head(pooled),
            "flag_logits": self.flag_head(pooled),
        }


def _prefers_cpu_on_mps(model_name: str | None = None) -> bool:
    normalized = str(model_name or "").strip().lower()
    return "deberta" in normalized


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


def _compute_loss(
    outputs: dict[str, Any],
    batch: dict[str, Any],
    g1_loss_fn: Any,
    g2_loss_fn: Any,
    flag_loss_fn: Any,
    g1_loss_weight: float = 1.0,
    g2_loss_weight: float = 2.0,
    flag_loss_weight: float = 0.45,
) -> Any:
    g1_loss = g1_loss_fn(outputs["g1_logits"], batch["g1_label"])
    g2_loss = g2_loss_fn(outputs["g2_logits"], batch["g2_label"])
    flag_loss = flag_loss_fn(outputs["flag_logits"], batch["flag_labels"])
    return (float(g1_loss_weight) * g1_loss) + (float(g2_loss_weight) * g2_loss) + (float(flag_loss_weight) * flag_loss)


def _compute_loss_breakdown(
    outputs: dict[str, Any],
    batch: dict[str, Any],
    g1_loss_fn: Any,
    g2_loss_fn: Any,
    flag_loss_fn: Any,
) -> dict[str, float]:
    g1_loss = float(g1_loss_fn(outputs["g1_logits"], batch["g1_label"]).item())
    g2_loss = float(g2_loss_fn(outputs["g2_logits"], batch["g2_label"]).item())
    flag_loss = float(flag_loss_fn(outputs["flag_logits"], batch["flag_labels"]).item())
    payload = {
        "g1_loss": g1_loss,
        "g2_loss": g2_loss,
        "flag_loss": flag_loss,
    }
    return payload


def _evaluate_loss(
    model: Any,
    loader: Any,
    g1_loss_fn: Any,
    g2_loss_fn: Any,
    flag_loss_fn: Any,
    g1_loss_weight: float = 1.0,
    g2_loss_weight: float = 2.0,
    flag_loss_weight: float = 0.45,
) -> float:
    model.eval()
    total_loss = 0.0
    total_batches = 0
    with torch.no_grad():
        for batch in loader:
            tensor_batch, _ = _split_batch_for_training(batch)
            tensor_batch = {key: value.to(_device(getattr(model.backbone, "name_or_path", None))) for key, value in tensor_batch.items()}
            outputs = model(input_ids=tensor_batch["input_ids"], attention_mask=tensor_batch["attention_mask"])
            loss = _compute_loss(
                outputs,
                tensor_batch,
                g1_loss_fn,
                g2_loss_fn,
                flag_loss_fn,
                g1_loss_weight=g1_loss_weight,
                g2_loss_weight=g2_loss_weight,
                flag_loss_weight=flag_loss_weight,
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
    g2_predictions: Counter[str] = Counter()
    g2_counts = {
        label: {"tp": 0, "fp": 0, "fn": 0}
        for label in label_vocab.get("g2", [])
    }
    with torch.no_grad():
        for batch in loader:
            device = _device(getattr(model.backbone, "name_or_path", None))
            tensor_batch, _ = _split_batch_for_training(batch)
            tensor_batch = {key: value.to(device) for key, value in tensor_batch.items()}
            outputs = model(input_ids=tensor_batch["input_ids"], attention_mask=tensor_batch["attention_mask"])
            g1_pred = torch.argmax(outputs["g1_logits"], dim=-1)
            g2_pred = torch.argmax(outputs["g2_logits"], dim=-1)
            g1_correct += int((g1_pred == tensor_batch["g1_label"]).sum().item())
            g2_correct += int((g2_pred == tensor_batch["g2_label"]).sum().item())
            total += int(tensor_batch["g1_label"].shape[0])
            g1_pred_values = g1_pred.cpu().tolist()
            g2_pred_values = g2_pred.cpu().tolist()
            g2_gold_values = tensor_batch["g2_label"].cpu().tolist()
            for value in g1_pred_values:
                g1_predictions[str(value)] += 1
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
    g2_f1_values: list[float] = []
    weighted_f1_numerator = 0.0
    weighted_support = 0
    for label, counts in g2_counts.items():
        tp = counts["tp"]
        fp = counts["fp"]
        fn = counts["fn"]
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        support = tp + fn
        g2_f1_values.append(f1)
        weighted_f1_numerator += f1 * support
        weighted_support += support
    return {
        "g1_accuracy": (g1_correct / total) if total else 0.0,
        "g2_accuracy": (g2_correct / total) if total else 0.0,
        "g2_macro_f1": (sum(g2_f1_values) / len(g2_f1_values)) if g2_f1_values else 0.0,
        "g2_weighted_f1": (weighted_f1_numerator / weighted_support) if weighted_support else 0.0,
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
    epochs: int | None = None,
    batch_size: int | None = None,
    max_length: int | None = None,
    device: str | None = None,
    freeze_backbone: bool | None = None,
    unfreeze_top_layers: int | None = None,
    learning_rate: float | None = None,
    g1_loss_weight: float | None = None,
    g2_loss_weight: float | None = None,
    flag_loss_weight: float | None = None,
    resume_if_available: bool | None = None,
    train_on_all_data: bool = False,
    checkpoint_every_batches: int | None = None,
    balanced_sampling: bool | None = None,
) -> dict[str, Any]:
    resolved_core = resolve_core(core)
    model_dir = model_dir or model_dir_for_core(resolved_core)
    rows: list[dict[str, Any]] = []
    train_rows: list[dict[str, Any]] = []
    dev_rows: list[dict[str, Any]] = []
    if not dataset_path.exists():
        try:
            from training.slm_classifier.source_normalizer import write_canonical_jsonl_with_metadata

            write_canonical_jsonl_with_metadata(target_path=dataset_path)
        except ValueError:
            if enable_training:
                raise
    paths = _paths_for_core(resolved_core)
    if dataset_path.exists():
        rows = _iter_rows(dataset_path)
    if rows:
        if train_on_all_data:
            train_rows = list(rows)
            dev_rows = []
        else:
            splits = load_dataset_splits()
            train_rows = select_rows_for_split(rows, "train", splits)
            dev_rows = select_rows_for_split(rows, "dev", splits)
            if not train_rows:
                raise ValueError(
                    "No train rows were selected for training. Rebuild dataset splits or pass --train-on-all-data explicitly."
                )
    elif enable_training:
        raise ValueError(f"No rows available for SLM training: {dataset_path}")
    if enable_training and not train_on_all_data and not dev_rows:
        raise ValueError(
            "No dev rows were selected for training. Rebuild dataset splits or pass --train-on-all-data explicitly."
        )
    model_dir.mkdir(parents=True, exist_ok=True)
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
    if g1_loss_weight is not None:
        config["g1_loss_weight"] = float(g1_loss_weight)
    if g2_loss_weight is not None:
        config["g2_loss_weight"] = float(g2_loss_weight)
    if flag_loss_weight is not None:
        config["flag_loss_weight"] = float(flag_loss_weight)
    if resume_if_available is not None:
        config["resume_if_available"] = bool(resume_if_available)
    if checkpoint_every_batches is not None:
        config["checkpoint_every_batches"] = int(checkpoint_every_batches)
    if balanced_sampling is not None:
        config["balanced_sampling"] = bool(balanced_sampling)
    config["train_on_all_data"] = bool(train_on_all_data)
    paths["training_config"].write_text(json.dumps(config, indent=2), encoding="utf-8")

    trained = False
    training_backend = "metadata_only"
    metadata = _build_training_metadata(rows, train_rows, dev_rows, trained=False, training_backend=training_backend, core=resolved_core)

    if enable_training:
        if not (AutoModel and AutoTokenizer and torch and nn and DataLoader):
            raise RuntimeError("Transformers/Torch dependencies are not available for SLM training.")
        startup_time = time.perf_counter()
        device = _device(config["model_name"], config.get("device", "auto"))
        log_prefix = f"[SLM:{resolved_core}]"
        print(f"{log_prefix} init: selected_device={device.type} requested_device={config.get('device', 'auto')}")
        label_vocab = json.loads(paths["label_vocab"].read_text(encoding="utf-8"))
        tokenizer_start = time.perf_counter()
        print(f"{log_prefix} init: loading_tokenizer model={config['model_name']}")
        tokenizer = _load_tokenizer(config["model_name"])
        print(f"{log_prefix} init: tokenizer_ready elapsed={time.perf_counter() - tokenizer_start:.2f}s")
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        dataset_start = time.perf_counter()
        print(f"{log_prefix} init: building_datasets")
        train_dataset = CanonicalSLMDataset(train_rows, tokenizer, label_vocab, config["max_length"])
        dev_dataset = CanonicalSLMDataset(dev_rows, tokenizer, label_vocab, config["max_length"])
        batch_debug_path = paths["batch_debug"]
        if bool(config.get("write_batch_debug", True)):
            batch_debug_path.write_text("", encoding="utf-8")
        sampler = None
        if bool(config.get("balanced_sampling", True)):
            if WeightedRandomSampler is None:
                raise RuntimeError("WeightedRandomSampler is not available for balanced SLM training.")
            sample_weights = _compute_sample_weights(train_rows, label_vocab)
            sampler = WeightedRandomSampler(
                weights=torch.tensor(sample_weights, dtype=torch.double),
                num_samples=len(sample_weights),
                replacement=True,
            )
            print(f"{log_prefix} init: balanced_sampler_ready samples={len(sample_weights)}")
        train_loader = DataLoader(train_dataset, batch_size=config["batch_size"], shuffle=sampler is None, sampler=sampler)
        dev_loader = DataLoader(dev_dataset, batch_size=config["batch_size"], shuffle=False)
        print(
            f"{log_prefix} init: dataloaders_ready train_batches={len(train_loader)} "
            f"dev_batches={len(dev_loader)} elapsed={time.perf_counter() - dataset_start:.2f}s"
        )
        model_start = time.perf_counter()
        print(f"{log_prefix} init: loading_model model={config['model_name']}")
        print(f"{log_prefix} init: constructing_model_backbone")
        model = MultiTaskSLMClassifier(config["model_name"], label_vocab)
        print(f"{log_prefix} init: backbone_ready elapsed={time.perf_counter() - model_start:.2f}s")
        device_move_start = time.perf_counter()
        print(f"{log_prefix} init: moving_model_to_device device={device.type}")
        model = model.to(device)
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
            actual_unfrozen_top_layers = model.unfreeze_top_layers(requested_unfreeze_top_layers)
            print(
                f"{log_prefix} init: backbone_partially_unfrozen=true "
                f"requested_top_layers={requested_unfreeze_top_layers} "
                f"actual_top_layers={actual_unfrozen_top_layers}"
            )
        elif bool(config.get("freeze_backbone", True)):
            model.freeze_backbone()
            print(f"{log_prefix} init: backbone_frozen=true")
        else:
            model.unfreeze_backbone()
            print(f"{log_prefix} init: backbone_frozen=false")
        g1_weights = torch.tensor(_compute_class_weights(train_rows, "g1", label_vocab["g1"]), dtype=torch.float32, device=device)
        g2_weights = torch.tensor(_compute_class_weights(train_rows, "g2", label_vocab["g2"]), dtype=torch.float32, device=device)
        flag_pos_weight = torch.tensor(
            _compute_list_multilabel_pos_weight(train_rows, label_vocab.get("flags", []), "flags"),
            dtype=torch.float32,
            device=device,
        )
        g1_loss_fn = nn.CrossEntropyLoss(weight=g1_weights)
        g2_loss_fn = nn.CrossEntropyLoss(weight=g2_weights)
        flag_loss_fn = nn.BCEWithLogitsLoss(pos_weight=flag_pos_weight)
        trainable_parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
        optimizer = torch.optim.AdamW(trainable_parameters, lr=config["learning_rate"], weight_decay=config["weight_decay"])

        best_dev_loss = None
        print(
            f"{log_prefix} training start: device={device.type} train_rows={len(train_rows)} "
            f"dev_rows={len(dev_rows)} batch_size={config['batch_size']} "
            f"max_length={config['max_length']} requested_device={config.get('device', 'auto')} "
            f"freeze_backbone={config.get('freeze_backbone', True)} "
            f"unfreeze_top_layers={config.get('unfreeze_top_layers', 0)} "
            f"resume_if_available={config.get('resume_if_available', True)} "
            f"balanced_sampling={config.get('balanced_sampling', True)} "
            f"checkpoint_every_batches={config.get('checkpoint_every_batches', 0)}"
        )
        print(
            f"{log_prefix} dataset summary: total_rows={len(rows)} "
            f"train_rows={len(train_rows)} dev_rows={len(dev_rows)} "
            f"dataset_fingerprint={metadata['dataset_fingerprint']}"
        )
        print(f"{log_prefix} init: startup_complete elapsed={time.perf_counter() - startup_time:.2f}s")
        for epoch_index in range(config["epochs"]):
            model.train()
            epoch_start = time.perf_counter()
            running_loss = 0.0
            print(f"{log_prefix} epoch {epoch_index + 1}/{config['epochs']} start")
            for batch_index, batch in enumerate(train_loader, start=1):
                batch_start = time.perf_counter()
                tensor_batch, meta_batch = _split_batch_for_training(batch)
                tensor_batch = {key: value.to(device) for key, value in tensor_batch.items()}
                optimizer.zero_grad()
                outputs = model(input_ids=tensor_batch["input_ids"], attention_mask=tensor_batch["attention_mask"])
                loss = _compute_loss(
                    outputs,
                    tensor_batch,
                    g1_loss_fn,
                    g2_loss_fn,
                    flag_loss_fn,
                    g1_loss_weight=float(config.get("g1_loss_weight", 1.0)),
                    g2_loss_weight=float(config.get("g2_loss_weight", 2.0)),
                    flag_loss_weight=float(config.get("flag_loss_weight", 0.45)),
                )
                loss.backward()
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
                        )
                        row_count = len(meta_batch.get("sample_id", []))
                        g1_pred_indices = torch.argmax(outputs["g1_logits"], dim=-1).detach().cpu().tolist()
                        g2_logits = outputs["g2_logits"].detach().cpu()
                        g2_probs = torch.softmax(g2_logits, dim=-1).tolist()
                        g2_pred_indices = torch.argmax(outputs["g2_logits"], dim=-1).detach().cpu().tolist()
                        g2_gold_indices = tensor_batch["g2_label"].detach().cpu().tolist()
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
                    torch.save(model.state_dict(), paths["state"])
                    latest_path = model_dir / "pytorch_model.latest.bin"
                    torch.save(model.state_dict(), latest_path)
                    print(
                        f"{log_prefix} checkpoint saved: batch={batch_index}/{len(train_loader)} "
                        f"path={paths['state']} latest={latest_path}"
                    )
            dev_loss = _evaluate_loss(
                model,
                dev_loader,
                g1_loss_fn,
                g2_loss_fn,
                flag_loss_fn,
                g1_loss_weight=float(config.get("g1_loss_weight", 1.0)),
                g2_loss_weight=float(config.get("g2_loss_weight", 2.0)),
                flag_loss_weight=float(config.get("flag_loss_weight", 0.45)),
            ) if len(dev_rows) else 0.0
            print(
                f"{log_prefix} epoch {epoch_index + 1} summary "
                f"train_avg_loss={running_loss / max(len(train_loader), 1):.4f} "
                f"dev_loss={dev_loss:.4f} elapsed={time.perf_counter() - epoch_start:.2f}s"
            )
            should_checkpoint = not len(dev_rows) or best_dev_loss is None or dev_loss < best_dev_loss
            if should_checkpoint:
                best_dev_loss = dev_loss
                torch.save(model.state_dict(), paths["state"])
                print(f"{log_prefix} checkpoint saved: {paths['state']}")

        tokenizer.save_pretrained(model_dir)
        trained = paths["state"].exists()
        training_backend = "transformers"
        metadata = _build_training_metadata(rows, train_rows, dev_rows, trained=trained, training_backend=training_backend, core=resolved_core)
        metadata["dev_loss"] = best_dev_loss
        metadata["device"] = device.type
        metadata["freeze_backbone"] = bool(config.get("freeze_backbone", True))
        metadata["unfreeze_top_layers"] = int(config.get("unfreeze_top_layers", 0) or 0)
        metadata["actual_unfrozen_top_layers"] = int(actual_unfrozen_top_layers)
        metadata["resume_if_available"] = bool(config.get("resume_if_available", True))
        metadata["balanced_sampling"] = bool(config.get("balanced_sampling", False))
        metadata["train_intent_heads"] = False
        metadata["g1_loss_weight"] = float(config.get("g1_loss_weight", 1.0))
        metadata["g2_loss_weight"] = float(config.get("g2_loss_weight", 2.0))
        metadata["flag_loss_weight"] = float(config.get("flag_loss_weight", 0.45))
        metadata["train_on_all_data"] = bool(config.get("train_on_all_data", False))
        metadata["resumed_from_existing"] = resumed_from_existing
        metadata["flags_trained"] = True
        if len(dev_rows):
            gate_eval = _evaluate_gate_accuracy(model, dev_loader, label_vocab)
            metadata["dev_gate_metrics"] = gate_eval
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
            return model(input_ids=encoded["input_ids"], attention_mask=encoded["attention_mask"]), str(encoded["input_ids"].device)
    except RuntimeError as exc:
        message = str(exc)
        if "MPSNDArrayMatrixMultiplication" not in message and "Placeholder storage has not been allocated on MPS device" not in message:
            raise
        cpu_device = _cpu_device()
        tokenizer, cpu_model = _load_trained_model_on_device(model_dir, package, cpu_device)
        encoded_cpu = {key: value.to(cpu_device) for key, value in encoded.items()}
        with torch.no_grad():
            return cpu_model(input_ids=encoded_cpu["input_ids"], attention_mask=encoded_cpu["attention_mask"]), "cpu_fallback"


def _load_trained_model_on_device(model_dir: Path, package: LoadedSLMPackage, device: Any) -> tuple[Any, Any]:
    if not (AutoTokenizer and torch and nn and AutoModel):
        raise RuntimeError("Transformers/Torch dependencies are not available for SLM inference.")
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
    previous_hf_offline = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        model = MultiTaskSLMClassifier(package.training_config["model_name"], package.label_vocab, local_files_only=True)
    finally:
        if previous_hf_offline is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous_hf_offline
    state_dict = torch.load(model_dir / "pytorch_model.bin", map_location=device)
    filtered_state_dict, _ = _filter_compatible_state_dict(model, state_dict)
    model.load_state_dict(filtered_state_dict, strict=False)
    if "flag_head.weight" not in state_dict:
        with torch.no_grad():
            model.flag_head.weight.zero_()
            model.flag_head.bias.zero_()
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
    g2_values: list[str],
    intent_evidence: dict[str, Any],
    learned_intent: dict[str, Any],
    threshold: float,
) -> GuardrailDecision:
    age_band = str(normalized.get("resolved_age_band") or normalized.get("child_profile", {}).get("age_group", "11-12"))
    language = str(normalized.get("child_profile", {}).get("language", "en"))
    question = str(normalized.get("text", "")).strip()
    topic = heuristic_classifier.classify_topic(heuristic_classifier.normalize(question))
    recent_context_items = [str(item) for item in normalized.get("recent_context", [])]
    recent_context = " ".join(item for item in recent_context_items if item.strip()) or "none"
    g2_list = g2_values or ["GENERIC_INTENT"]
    classifier_output = {
        "schema_version": "2.0.0",
        "question": question,
        "language": language,
        "age_band": age_band,
        "applies_when_flags": runtime_contracts.build_applies_when_flags(question, g1, g2_list),
        "intent_lexicon": {
            **intent_evidence,
            "learned": learned_intent,
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
        gates={"G1": g1, "G2": primary_g2, "G2_all": g2_list, "G3": g3, "G4": g4},
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
        gate_values={"topic": topic, "G1": g1, "G2": primary_g2, "G2_all": g2_list, "G3": g3, "G4": g4},
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
            "language": str(normalized.get("child_profile", {}).get("language", "en")),
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
    inference_device = _device(
        package.training_config.get("model_name"),
        package.training_config.get("device", "auto"),
    )
    encoded = {key: value.to(inference_device) for key, value in encoded.items()}
    outputs, inference_device = _run_model_with_device_fallback(model, encoded, resolved_dir, package)
    flag_probs = torch.sigmoid(outputs["flag_logits"]).squeeze(0).cpu().tolist()
    g1_idx = int(torch.argmax(outputs["g1_logits"], dim=-1).item())
    g2_primary_probs = torch.softmax(outputs["g2_logits"], dim=-1).squeeze(0).cpu().tolist()
    primary_g2, g2_values = _decode_g2_predictions(
        package.label_vocab,
        g2_primary_probs,
        threshold=threshold,
    )
    recent_context = " ".join(str(item) for item in normalized.get("recent_context", [])) or ""
    intent_evidence = runtime_contracts.match_intent_lexicon(
        str(normalized.get("text", "")).strip(),
        recent_context,
    )
    heuristic_g2_values = heuristic_classifier.classify_g2(
        heuristic_classifier.normalize(str(normalized.get("text", "")).strip()),
        recent_context,
    ) or ["GENERIC_INTENT"]
    flag_vocab = list(package.label_vocab.get("flags", []))
    learned_intent = {
        "predicted_families": [],
        "predicted_phrases": [],
        "family_scores": {},
        "phrase_scores": {},
    }
    g2_values = _fuse_g2_predictions(
        list(package.label_vocab.get("g2", [])),
        g2_values,
        primary_g2,
        heuristic_g2_values,
        list(intent_evidence.get("matched_lovs", [])),
    )
    primary_g2 = primary_g2_label(g2_values) or primary_g2
    decision = _decision_from_predictions(
        normalized=normalized,
        package=package,
        model_dir=resolved_dir,
        g1=package.label_vocab["g1"][g1_idx],
        primary_g2=primary_g2,
        g2_values=g2_values,
        intent_evidence=intent_evidence,
        learned_intent=learned_intent,
        threshold=threshold,
    )
    return decision.model_copy(
        update={
            "classifier_metadata": {
                **decision.classifier_metadata,
                "inference_device": inference_device,
                "head_confidences": {
                    **decision.classifier_metadata.get("head_confidences", {}),
                    "flags": {label: float(score) for label, score in zip(flag_vocab, flag_probs)},
                    "G2_primary": {label: float(score) for label, score in zip(package.label_vocab["g2"], g2_primary_probs)},
                    "G2_all": {
                        label: float(score)
                        for label, score in zip(package.label_vocab["g2"], g2_primary_probs)
                        if label in g2_values
                    },
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
            "language": str(normalized.get("child_profile", {}).get("language", "en")),
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

    g1_idx = int(torch.argmax(outputs["g1_logits"], dim=-1).item())
    g2_idx = int(torch.argmax(outputs["g2_logits"], dim=-1).item())

    g1 = package.label_vocab["g1"][g1_idx]
    g2 = package.label_vocab["g2"][g2_idx]
    flag_vocab = list(package.label_vocab.get("flags", []))
    active_flags = {
        label: bool(float(score) >= threshold)
        for label, score in zip(flag_vocab, flag_probs)
    }

    return GuardrailDecision(
        input={
            "question": str(normalized.get("text", "")).strip(),
            "age_band": str(normalized.get("resolved_age_band", "")),
            "language": str(normalized.get("child_profile", {}).get("language", "en")),
            "recent_context": list(normalized.get("recent_context", [])),
        },
        gates={"G1": g1, "G2": g2},
        gate_values={"G1": g1, "G2": g2},
        policy_bucket="model_only",
        safety_category=g2,
        response_mode="model_only",
        risk_level="model_only",
        parent_visible=False,
        confidence=max(
            max((float(score) for score in g1_probs), default=0.0),
            max((float(score) for score in g2_probs), default=0.0),
            max((float(score) for score in flag_probs), default=0.0),
        ),
        signals=active_flags,
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
            "g2_threshold": threshold,
            "label_vocab_path": str(resolved_dir / "label_vocab.json"),
            "head_confidences": {
                "G1": {
                    label: float(score)
                    for label, score in zip(package.label_vocab["g1"], g1_probs)
                },
                "G2": {
                    label: float(score)
                    for label, score in zip(package.label_vocab["g2"], g2_probs)
                },
                "flags": {
                    label: float(score)
                    for label, score in zip(flag_vocab, flag_probs)
                },
            },
        },
    )
