from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.guardrails import gate_mapper, slm_classifier as heuristic_classifier
from app.models.guardrail_decision import GLSignal, GuardrailDecision
from training.slm_classifier.codebook import DOC_CODEBOOK_PATH
from training.slm_classifier.data_pipeline import (
    CANONICAL_DATASET,
    GL_COLUMNS,
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
    "deberta": {
        "model_name": "microsoft/deberta-v3-xsmall",
        "dir_name": "piku-slm-guardrail-deberta-v3-xsmall",
    },
}
DEFAULT_CORE = "smol"
G2_ACTIVATION_THRESHOLD = 0.5


@dataclass
class LoadedSLMPackage:
    metadata: dict[str, Any]
    label_vocab: dict[str, list[str]]
    thresholds: dict[str, float]
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
        "thresholds": model_dir / "thresholds.json",
        "state": model_dir / "pytorch_model.bin",
        "training_config": model_dir / "training_config.json",
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


def _default_thresholds() -> dict[str, float]:
    return dict(load_classifier_runtime_config().gl_thresholds)


def _load_label_vocab() -> dict[str, list[str]]:
    if not LABEL_VOCAB_PATH.exists():
        write_label_vocab(LABEL_VOCAB_PATH)
    return json.loads(LABEL_VOCAB_PATH.read_text(encoding="utf-8"))


def _decode_g2_predictions(
    label_vocab: dict[str, list[str]],
    primary_probs: list[float],
    multilabel_probs: list[float],
    threshold: float = G2_ACTIVATION_THRESHOLD,
) -> tuple[str, list[str]]:
    g2_labels = list(label_vocab.get("g2", []))
    if not g2_labels:
        return "GENERIC_INTENT", ["GENERIC_INTENT"]
    primary_index = max(range(len(primary_probs)), key=lambda idx: float(primary_probs[idx]))
    primary_g2 = g2_labels[primary_index]
    g2_all = [
        label
        for label, score in zip(g2_labels, multilabel_probs)
        if float(score) >= threshold
    ]
    if primary_g2 not in g2_all:
        g2_all.insert(0, primary_g2)
    return primary_g2, g2_all


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
        "train_split": "train",
        "eval_split": "dev",
        "freeze_backbone": False,
        "log_every_batches": 25,
        "resume_if_available": False,
        "balanced_sampling": True,
    }
    if resolved_core == "smol":
        config["epochs"] = 2
        config["batch_size"] = 2
        config["max_length"] = 128
        config["log_every_batches"] = 10
    return config


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
    }


def _existing_training_metadata(model_dir: Path) -> dict[str, Any]:
    path = model_dir / "training_metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _format_classifier_input(row: dict[str, Any]) -> str:
    return (
        "Classify child-safety guideline signals and gates.\n"
        f"Language: {row.get('language', 'en')}\n"
        f"Recent context: {row.get('recent_context', 'none')}\n"
        f"Question: {row['question']}"
    )


def _index_map(values: list[str]) -> dict[str, int]:
    return {value: idx for idx, value in enumerate(values)}


def _compute_pos_weight(rows: list[dict[str, Any]]) -> list[float]:
    total = max(len(rows), 1)
    weights: list[float] = []
    for column in GL_COLUMNS:
        positives = sum(int(row[column]) for row in rows)
        negatives = max(total - positives, 1)
        positives = max(positives, 1)
        weights.append(negatives / positives)
    return weights


def _compute_class_weights(rows: list[dict[str, Any]], key: str, vocab: list[str]) -> list[float]:
    counts = {value: 0 for value in vocab}
    for row in rows:
        counts[str(row[key])] += 1
    total = max(len(rows), 1)
    weights: list[float] = []
    for value in vocab:
        count = max(counts[value], 1)
        weights.append(total / (len(vocab) * count))
    return weights


def _compute_multilabel_pos_weight(rows: list[dict[str, Any]], vocab: list[str], key: str) -> list[float]:
    total = max(len(rows), 1)
    counts = {value: 0 for value in vocab}
    for row in rows:
        for value in parse_g2_values(row.get(key, [])):
            if value in counts:
                counts[value] += 1
    weights: list[float] = []
    for value in vocab:
        positives = max(counts[value], 1)
        negatives = max(total - positives, 1)
        weights.append(negatives / positives)
    return weights


def _compute_sample_weights(rows: list[dict[str, Any]], label_vocab: dict[str, list[str]]) -> list[float]:
    topic_counts = {value: 0 for value in label_vocab["topic"]}
    g1_counts = {value: 0 for value in label_vocab["g1"]}
    g2_counts = {value: 0 for value in label_vocab["g2"]}
    gl_positive_counts = {column: 0 for column in GL_COLUMNS}
    total = max(len(rows), 1)

    for row in rows:
        topic_counts[str(row["topic"])] += 1
        g1_counts[str(row["g1"])] += 1
        for value in parse_g2_values(row.get("g2_all", row.get("g2", []))):
            if value in g2_counts:
                g2_counts[value] += 1
        for column in GL_COLUMNS:
            if int(row[column]) == 1:
                gl_positive_counts[column] += 1

    weights: list[float] = []
    for row in rows:
        topic_weight = total / max(topic_counts[str(row["topic"])], 1)
        g1_weight = total / max(g1_counts[str(row["g1"])], 1)
        active_g2_weights = [
            total / max(g2_counts[value], 1)
            for value in parse_g2_values(row.get("g2_all", row.get("g2", [])))
            if value in g2_counts
        ]
        g2_weight = max(active_g2_weights) if active_g2_weights else 1.0
        active_gl_weights = [
            total / max(gl_positive_counts[column], 1)
            for column in GL_COLUMNS
            if int(row[column]) == 1
        ]
        gl_weight = max(active_gl_weights) if active_gl_weights else 1.0
        weights.append(float(max(topic_weight, g1_weight, g2_weight, gl_weight)))
    return weights


class CanonicalSLMDataset(Dataset):  # pragma: no cover - exercised through training/inference path
    def __init__(self, rows: list[dict[str, Any]], tokenizer: Any, label_vocab: dict[str, list[str]], max_length: int) -> None:
        self.rows = rows
        self.tokenizer = tokenizer
        self.label_vocab = label_vocab
        self.max_length = max_length
        self.topic_index = _index_map(label_vocab["topic"])
        self.g1_index = _index_map(label_vocab["g1"])
        self.g2_index = _index_map(label_vocab["g2"])

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
            "gl_labels": torch.tensor([float(row[column]) for column in GL_COLUMNS], dtype=torch.float32),
            "topic_label": torch.tensor(self.topic_index[str(row["topic"])], dtype=torch.long),
            "g1_label": torch.tensor(self.g1_index[str(row["g1"])], dtype=torch.long),
            "g2_label": torch.tensor(self.g2_index[str(row["g2"])], dtype=torch.long),
            "g2_all_labels": torch.tensor(
                [
                    float(label in parse_g2_values(row.get("g2_all", row.get("g2", []))))
                    for label in self.label_vocab["g2"]
                ],
                dtype=torch.float32,
            ),
        }


class MultiTaskSLMClassifier(nn.Module):  # pragma: no cover - exercised through training/inference path
    def __init__(self, model_name: str, label_vocab: dict[str, list[str]], *, local_files_only: bool = False) -> None:
        super().__init__()
        self.backbone = AutoModel.from_pretrained(model_name, local_files_only=local_files_only)
        hidden_size = int(self.backbone.config.hidden_size)
        self.dropout = nn.Dropout(0.1)
        self.gl_head = nn.Linear(hidden_size, len(label_vocab["gl_columns"]))
        self.topic_head = nn.Linear(hidden_size, len(label_vocab["topic"]))
        self.g1_head = nn.Linear(hidden_size, len(label_vocab["g1"]))
        self.g2_head = nn.Linear(hidden_size, len(label_vocab["g2"]))
        self.g2_all_head = nn.Linear(hidden_size, len(label_vocab["g2"]))

    def freeze_backbone(self) -> None:
        for parameter in self.backbone.parameters():
            parameter.requires_grad = False

    def unfreeze_backbone(self) -> None:
        for parameter in self.backbone.parameters():
            parameter.requires_grad = True

    def _pool(self, hidden_state: Any, attention_mask: Any) -> Any:
        mask = attention_mask.unsqueeze(-1).to(hidden_state.dtype)
        summed = (hidden_state * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1.0)
        return summed / counts

    def forward(self, input_ids: Any, attention_mask: Any) -> dict[str, Any]:
        outputs = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        pooled = self._pool(outputs.last_hidden_state, attention_mask)
        pooled = pooled.to(self.gl_head.weight.dtype)
        pooled = self.dropout(pooled)
        return {
            "gl_logits": self.gl_head(pooled),
            "topic_logits": self.topic_head(pooled),
            "g1_logits": self.g1_head(pooled),
            "g2_logits": self.g2_head(pooled),
            "g2_all_logits": self.g2_all_head(pooled),
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
    gl_loss_fn: Any,
    topic_loss_fn: Any,
    g1_loss_fn: Any,
    g2_loss_fn: Any,
    g2_all_loss_fn: Any,
) -> Any:
    gl_loss = gl_loss_fn(outputs["gl_logits"], batch["gl_labels"])
    topic_loss = topic_loss_fn(outputs["topic_logits"], batch["topic_label"])
    g1_loss = g1_loss_fn(outputs["g1_logits"], batch["g1_label"])
    g2_loss = g2_loss_fn(outputs["g2_logits"], batch["g2_label"])
    g2_all_loss = g2_all_loss_fn(outputs["g2_all_logits"], batch["g2_all_labels"])
    return (1.0 * gl_loss) + (1.0 * topic_loss) + (1.0 * g1_loss) + (2.0 * g2_loss) + (0.75 * g2_all_loss)


def _evaluate_loss(model: Any, loader: Any, gl_loss_fn: Any, topic_loss_fn: Any, g1_loss_fn: Any, g2_loss_fn: Any, g2_all_loss_fn: Any) -> float:
    model.eval()
    total_loss = 0.0
    total_batches = 0
    with torch.no_grad():
        for batch in loader:
            batch = {key: value.to(_device(getattr(model.backbone, "name_or_path", None))) for key, value in batch.items()}
            outputs = model(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"])
            loss = _compute_loss(outputs, batch, gl_loss_fn, topic_loss_fn, g1_loss_fn, g2_loss_fn, g2_all_loss_fn)
            total_loss += float(loss.item())
            total_batches += 1
    return total_loss / total_batches if total_batches else 0.0


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
    resume_if_available: bool | None = None,
    train_on_all_data: bool = False,
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
    #paths = _paths_for_core(resolved_core)
    paths = {
    "model_dir": model_dir,
    "metadata": model_dir / "training_metadata.json",
    "label_vocab": model_dir / "label_vocab.json",
    "thresholds": model_dir / "thresholds.json",
    "state": model_dir / "pytorch_model.bin",
    "training_config": model_dir / "training_config.json",
    }
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
    elif enable_training:
        raise ValueError(f"No rows available for SLM training: {dataset_path}")
    model_dir.mkdir(parents=True, exist_ok=True)
    ensure_label_vocab(model_dir=model_dir, core=resolved_core)
    thresholds = _default_thresholds()
    paths["thresholds"].write_text(json.dumps(thresholds, indent=2), encoding="utf-8")
    config = _training_defaults(resolved_core)
    if epochs is not None:
        config["epochs"] = int(epochs)
    if batch_size is not None:
        config["batch_size"] = int(batch_size)
    if max_length is not None:
        config["max_length"] = int(max_length)
    if device is not None:
        config["device"] = str(device)
    if resume_if_available is not None:
        config["resume_if_available"] = bool(resume_if_available)
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
        label_vocab = _load_label_vocab()
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
            has_new_g2_all_head = "g2_all_head.weight" in state_dict and "g2_all_head.bias" in state_dict
            if has_new_g2_all_head:
                model.load_state_dict(state_dict)
                resumed_from_existing = True
                print(f"{log_prefix} init: resumed_from_checkpoint path={paths['state']}")
            else:
                print(f"{log_prefix} init: skipped_resume_incompatible_checkpoint path={paths['state']}")
        if bool(config.get("freeze_backbone", True)):
            model.freeze_backbone()
            print(f"{log_prefix} init: backbone_frozen=true")
        else:
            model.unfreeze_backbone()
            print(f"{log_prefix} init: backbone_frozen=false")
        gl_pos_weight = torch.tensor(_compute_pos_weight(train_rows), dtype=torch.float32, device=device)
        topic_weights = torch.tensor(_compute_class_weights(train_rows, "topic", label_vocab["topic"]), dtype=torch.float32, device=device)
        g1_weights = torch.tensor(_compute_class_weights(train_rows, "g1", label_vocab["g1"]), dtype=torch.float32, device=device)
        g2_weights = torch.tensor(_compute_class_weights(train_rows, "g2", label_vocab["g2"]), dtype=torch.float32, device=device)
        g2_pos_weight = torch.tensor(
            _compute_multilabel_pos_weight(train_rows, label_vocab["g2"], "g2_all"),
            dtype=torch.float32,
            device=device,
        )
        gl_loss_fn = nn.BCEWithLogitsLoss(pos_weight=gl_pos_weight)
        topic_loss_fn = nn.CrossEntropyLoss(weight=topic_weights)
        g1_loss_fn = nn.CrossEntropyLoss(weight=g1_weights)
        g2_loss_fn = nn.CrossEntropyLoss(weight=g2_weights)
        g2_all_loss_fn = nn.BCEWithLogitsLoss(pos_weight=g2_pos_weight)
        trainable_parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
        optimizer = torch.optim.AdamW(trainable_parameters, lr=config["learning_rate"], weight_decay=config["weight_decay"])

        best_dev_loss = None
        print(
            f"{log_prefix} training start: device={device.type} train_rows={len(train_rows)} "
            f"dev_rows={len(dev_rows)} batch_size={config['batch_size']} "
            f"max_length={config['max_length']} requested_device={config.get('device', 'auto')} "
            f"freeze_backbone={config.get('freeze_backbone', True)} "
            f"resume_if_available={config.get('resume_if_available', True)} "
            f"balanced_sampling={config.get('balanced_sampling', True)}"
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
                batch = {key: value.to(device) for key, value in batch.items()}
                optimizer.zero_grad()
                outputs = model(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"])
                loss = _compute_loss(outputs, batch, gl_loss_fn, topic_loss_fn, g1_loss_fn, g2_loss_fn, g2_all_loss_fn)
                loss.backward()
                optimizer.step()
                running_loss += float(loss.item())
                if batch_index == 1 or batch_index % int(config.get("log_every_batches", 25)) == 0 or batch_index == len(train_loader):
                    avg_loss = running_loss / batch_index
                    print(
                        f"{log_prefix} epoch {epoch_index + 1} batch {batch_index}/{len(train_loader)} "
                        f"loss={loss.item():.4f} avg_loss={avg_loss:.4f} "
                        f"batch_time={time.perf_counter() - batch_start:.2f}s"
                    )
            dev_loss = _evaluate_loss(model, dev_loader, gl_loss_fn, topic_loss_fn, g1_loss_fn, g2_loss_fn, g2_all_loss_fn) if len(dev_rows) else 0.0
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
        metadata["resume_if_available"] = bool(config.get("resume_if_available", True))
        metadata["train_on_all_data"] = bool(config.get("train_on_all_data", False))
        metadata["resumed_from_existing"] = resumed_from_existing
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
    thresholds_path = resolved_dir / "thresholds.json"
    training_config_path = resolved_dir / "training_config.json"
    if not metadata_path.exists() or not label_vocab_path.exists() or not thresholds_path.exists() or not training_config_path.exists():
        return None
    return LoadedSLMPackage(
        metadata=json.loads(metadata_path.read_text(encoding="utf-8")),
        label_vocab=json.loads(label_vocab_path.read_text(encoding="utf-8")),
        thresholds={str(key): float(value) for key, value in json.loads(thresholds_path.read_text(encoding="utf-8")).items()},
        training_config=json.loads(training_config_path.read_text(encoding="utf-8")),
    )


def _load_trained_model(model_dir: Path, package: LoadedSLMPackage) -> tuple[Any, Any]:
    if not (AutoTokenizer and torch and nn and AutoModel):
        raise RuntimeError("Transformers/Torch dependencies are not available for SLM inference.")
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
    except Exception:
        tokenizer = _load_tokenizer(package.training_config["model_name"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    device = _device(package.training_config["model_name"])
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
    has_new_g2_all_head = "g2_all_head.weight" in state_dict and "g2_all_head.bias" in state_dict
    has_topic_head = "topic_head.weight" in state_dict and "topic_head.bias" in state_dict
    if not has_new_g2_all_head:
        raise RuntimeError("Incompatible checkpoint format: missing g2_all_head. Retrain the SLM classifier with the updated dual-head G2 architecture.")
    if not has_topic_head:
        raise RuntimeError("Incompatible checkpoint format: missing topic_head. Retrain the SLM classifier with topic labels enabled.")
    model.load_state_dict(state_dict)
    model = model.float().to(device)
    model.eval()
    return tokenizer, model


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
    has_new_g2_all_head = "g2_all_head.weight" in state_dict and "g2_all_head.bias" in state_dict
    has_topic_head = "topic_head.weight" in state_dict and "topic_head.bias" in state_dict
    if not has_new_g2_all_head:
        raise RuntimeError("Incompatible checkpoint format: missing g2_all_head. Retrain the SLM classifier with the updated dual-head G2 architecture.")
    if not has_topic_head:
        raise RuntimeError("Incompatible checkpoint format: missing topic_head. Retrain the SLM classifier with topic labels enabled.")
    model.load_state_dict(state_dict)
    model = model.float().to(device)
    model.eval()
    return tokenizer, model


def _decision_from_predictions(
    normalized: dict[str, object],
    package: LoadedSLMPackage,
    model_dir: Path,
    topic: str,
    g1: str,
    primary_g2: str,
    g2_values: list[str],
    gl_scores: dict[str, float],
) -> GuardrailDecision:
    age_band = str(normalized.get("resolved_age_band") or normalized.get("child_profile", {}).get("age_group", "11-12"))
    language = str(normalized.get("child_profile", {}).get("language", "en"))
    question = str(normalized.get("text", "")).strip()
    recent_context_items = [str(item) for item in normalized.get("recent_context", [])]
    recent_context = " ".join(item for item in recent_context_items if item.strip()) or "none"
    g2_list = g2_values or ["GENERIC_INTENT"]
    g3_inputs = [primary_g2]
    modifiers = gate_mapper.g3_modifiers(g3_inputs)
    g3 = gate_mapper.map_g3(g3_inputs)
    g4 = gate_mapper.map_g4(g3, g2_list, modifiers)
    active_gls = sorted(gl_id for gl_id, score in gl_scores.items() if score >= package.thresholds.get(gl_id, package.thresholds.get("default", 0.5)))
    if "GL-01" not in active_gls:
        active_gls.insert(0, "GL-01")
    prompt = heuristic_classifier.build_generated_prompt(age_band, g1, g2_list, g3, list(modifiers), g4, question)
    contract = gate_mapper.build_prompt_contract(g4, g3, g2_list, age_band, set(active_gls))
    contract["generated_prompt"] = prompt
    contract["resolved_age_band"] = age_band
    decision_fields = gate_mapper.build_decision_from_g4(g4, g3, g2_list)
    gl_signals = {
        gl_id: GLSignal(
            name=gate_mapper.GUIDELINES[gl_id]["name"],
            triggered=gl_id in active_gls,
            confidence=float(gl_scores.get(gl_id, 0.01)),
            emits=dict(gate_mapper.GUIDELINES[gl_id].get("emits", {})) if gl_id in active_gls else {},
        )
        for gl_id in gate_mapper.GUIDELINES
    }
    return GuardrailDecision(
        input={"question": question, "age_band": age_band, "language": language, "recent_context": recent_context},
        reason=heuristic_classifier.build_classifier_reason(g1, g2_list, active_gls, question),
        g1_reason=heuristic_classifier.build_g1_reason(g1, g2_list, active_gls, question),
        g2_reasons=heuristic_classifier.build_g2_reasons(g1, g2_list, question),
        gl_signals=gl_signals,
        active_gls=active_gls,
        gates={"topic": topic, "G1": g1, "G2": primary_g2, "G2_all": g2_list, "G3": g3, "G4": g4},
        decision=decision_fields,
        policy_bucket="allowed" if decision_fields["allow_llm"] else "soft_block",
        safety_category=primary_g2,
        response_mode=str(decision_fields["response_mode"]),
        risk_level=str(decision_fields["risk_level"]),
        parent_visible=bool(decision_fields["parent_visible"]),
        confidence=min((score for gl_id, score in gl_scores.items() if gl_id in active_gls), default=0.0),
        guideline_tags=active_gls,
        signals={"topic": topic, "g2_labels": ";".join(g2_list)},
        gate_values={"topic": topic, "G1": g1, "G2": primary_g2, "G2_all": g2_list, "G3": g3, "G4": g4},
        prompt_contract=contract,
        classifier_metadata={
            "backend": "slm",
            "backend_version": package.metadata.get("model_name", model_name_for_core(package.metadata.get("core_model"))),
            "core_model": package.metadata.get("core_model", DEFAULT_CORE),
            "rollout_mode": load_classifier_runtime_config().rollout_mode,
            "g2_threshold": G2_ACTIVATION_THRESHOLD,
            "model_fingerprint": package.metadata.get("dataset_fingerprint", "unknown"),
            "codebook_fingerprint": package.metadata.get("codebook_fingerprint", "unknown"),
            "dataset_fingerprint": package.metadata.get("dataset_fingerprint", "unknown"),
            "label_vocab_path": str(model_dir / "label_vocab.json"),
            "thresholds_path": str(model_dir / "thresholds.json"),
            "head_confidences": {
                "GL": gl_scores,
            },
            "trained": bool(package.metadata.get("trained", False)),
        },
    )


def build_decision_from_slm(normalized: dict[str, object], model_dir: Path | None = None, core: str | None = None) -> GuardrailDecision:
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
    inference_device = _device(package.training_config.get("model_name"))
    encoded = {key: value.to(inference_device) for key, value in encoded.items()}
    outputs, inference_device = _run_model_with_device_fallback(model, encoded, resolved_dir, package)
    gl_probs = torch.sigmoid(outputs["gl_logits"]).squeeze(0).cpu().tolist()
    topic_probs = torch.softmax(outputs["topic_logits"], dim=-1).squeeze(0).cpu().tolist()
    topic_idx = int(torch.argmax(outputs["topic_logits"], dim=-1).item())
    g1_idx = int(torch.argmax(outputs["g1_logits"], dim=-1).item())
    g2_primary_probs = torch.softmax(outputs["g2_logits"], dim=-1).squeeze(0).cpu().tolist()
    g2_all_probs = torch.sigmoid(outputs["g2_all_logits"]).squeeze(0).cpu().tolist()
    topic_vocab = list(package.label_vocab.get("topic", []))
    topic = topic_vocab[topic_idx] if topic_vocab and topic_idx < len(topic_vocab) else heuristic_classifier.classify_topic(heuristic_classifier.normalize(str(normalized.get("text", ""))))
    gl_scores = {
        gl_id.upper().replace("_", "-"): float(score)
        for gl_id, score in zip(package.label_vocab["gl_columns"], gl_probs)
    }
    primary_g2, g2_values = _decode_g2_predictions(
        package.label_vocab,
        g2_primary_probs,
        g2_all_probs,
        threshold=G2_ACTIVATION_THRESHOLD,
    )
    decision = _decision_from_predictions(
        normalized=normalized,
        package=package,
        model_dir=resolved_dir,
        topic=topic,
        g1=package.label_vocab["g1"][g1_idx],
        primary_g2=primary_g2,
        g2_values=g2_values,
        gl_scores=gl_scores,
    )
    return decision.model_copy(
        update={
            "classifier_metadata": {
                **decision.classifier_metadata,
                "inference_device": inference_device,
                "head_confidences": {
                    **decision.classifier_metadata.get("head_confidences", {}),
                    "topic": {label: float(score) for label, score in zip(topic_vocab, topic_probs)},
                    "G2_primary": {label: float(score) for label, score in zip(package.label_vocab["g2"], g2_primary_probs)},
                    "G2_all": {label: float(score) for label, score in zip(package.label_vocab["g2"], g2_all_probs)},
                },
            }
        }
    )
