from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from datasets import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)


LABEL2ID = {"safe": 0, "unsafe": 1}
ID2LABEL = {0: "safe", 1: "unsafe"}


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("dataset JSON must be a list of {text, label} objects")
    for idx, row in enumerate(rows):
        if not isinstance(row, dict) or "text" not in row or "label" not in row:
            raise ValueError(f"row {idx} must contain text and label")
        row["label"] = int(row["label"])
        if row["label"] not in {0, 1}:
            raise ValueError(f"row {idx} label must be 0 or 1")
    return rows


def train(
    *,
    dataset_path: Path,
    output_dir: Path,
    model_name: str,
    epochs: float,
    batch_size: int,
    learning_rate: float,
    max_length: int,
) -> None:
    rows = _load_rows(dataset_path)
    dataset = Dataset.from_list(rows).train_test_split(test_size=0.1, seed=42)
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    def tokenize(batch: dict[str, list[Any]]) -> dict[str, Any]:
        return tokenizer(batch["text"], truncation=True, max_length=max_length)

    tokenized = dataset.map(tokenize, batched=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=2,
        label2id=LABEL2ID,
        id2label=ID2LABEL,
    )
    args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=learning_rate,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        report_to=[],
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["test"],
        tokenizer=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer=tokenizer),
    )
    trainer.train()
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the response validator DeBERTa sequence classifier.")
    parser.add_argument("--dataset", default=Path("validator/data/processed/dataset.json"), type=Path)
    parser.add_argument("--output-dir", default=Path("validator/models/piku-validator-deberta-v3-small"), type=Path)
    parser.add_argument("--model-name", default="microsoft/deberta-v3-small")
    parser.add_argument("--epochs", default=3.0, type=float)
    parser.add_argument("--batch-size", default=16, type=int)
    parser.add_argument("--learning-rate", default=2e-5, type=float)
    parser.add_argument("--max-length", default=512, type=int)
    args = parser.parse_args()

    train(
        dataset_path=args.dataset,
        output_dir=args.output_dir,
        model_name=args.model_name,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        max_length=args.max_length,
    )


if __name__ == "__main__":
    main()
