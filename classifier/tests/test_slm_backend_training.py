import json
from pathlib import Path

import pytest

from training.slm_classifier.data_pipeline import write_label_vocab
from training.slm_classifier.data_pipeline import DatasetSplitManifest
from training.slm_classifier.slm_backend import _checkpoint_is_compatible, _checkpoint_payload_is_compatible, _compute_list_multilabel_pos_weight, train_slm_classifier


def test_compute_list_multilabel_pos_weight_counts_only_true_flag_values() -> None:
    rows = [
        {"flags": {"has_bullying_involved": True, "has_emotional_distress": False}},
        {"flags": {"has_bullying_involved": False, "has_emotional_distress": False}},
        {"flags": {"has_bullying_involved": False, "has_emotional_distress": True}},
    ]

    weights = _compute_list_multilabel_pos_weight(
        rows,
        ["has_bullying_involved", "has_emotional_distress"],
        "flags",
    )

    assert weights == [2.0, 2.0]


def test_checkpoint_payload_requires_model_state() -> None:
    assert _checkpoint_payload_is_compatible({"model_state": {"classifier.weight": object()}}) is True
    assert _checkpoint_payload_is_compatible({"epoch_index": 1}) is False


def test_checkpoint_compatibility_accepts_multihead_keys() -> None:
    assert _checkpoint_is_compatible({"g1_classifier.weight": object()}) is True
    assert _checkpoint_is_compatible({"g2_classifier.weight": object()}) is True
    assert _checkpoint_is_compatible({"flag_classifier.weight": object()}) is True


def test_write_label_vocab_includes_intent_families(tmp_path: Path) -> None:
    target = tmp_path / "label_vocab.json"
    write_label_vocab(
        rows=[
            {"intent_families": ["what_should_i_do", "threats_and_punishment"]},
            {"intent_families": ["what_should_i_do"]},
        ],
        target_path=target,
    )
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["intent_families"] == ["what_should_i_do", "threats_and_punishment"]


def test_train_slm_classifier_requires_test_rows_unless_train_on_all_data(tmp_path: Path, monkeypatch) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "sample_id": "row-1",
                        "question": "Why is the sky blue?",
                        "context": "",
                        "topic": "Science",
                        "g1": "SCIENCE",
                        "g2": ["NEUTRAL_FACT"],
                        "flags": {"direct_intent": False},
                        "intent_families": [],
                        "intent_phrases": [],
                        "review_status": "approved",
                    }
                )
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "training.slm_classifier.slm_backend.load_dataset_splits",
        lambda: DatasetSplitManifest(train_ids=[], test_ids=[], fingerprint="test"),
    )

    with pytest.raises(ValueError, match="No (train|test) rows were selected"):
        train_slm_classifier(
            dataset_path=dataset_path,
            model_dir=tmp_path / "model",
            enable_training=False,
            train_on_all_data=False,
        )


def test_train_slm_classifier_persists_balanced_sampling_config(tmp_path: Path, monkeypatch) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    model_dir = tmp_path / "model"
    dataset_path.write_text(
        json.dumps(
            {
                "sample_id": "row-1",
                "question": "Why is the sky blue?",
                "context": "",
                "g1": "SCIENCE",
                "g2": ["NEUTRAL_FACT"],
                "flags": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "training.slm_classifier.slm_backend.load_dataset_splits",
        lambda: DatasetSplitManifest(train_ids=["row-1"], test_ids=[], fingerprint="test"),
    )

    train_slm_classifier(
        dataset_path=dataset_path,
        model_dir=model_dir,
        enable_training=False,
        train_on_all_data=True,
        balanced_sampling=True,
    )

    config = json.loads((model_dir / "training_config.json").read_text(encoding="utf-8"))
    assert config["balanced_sampling"] is True
