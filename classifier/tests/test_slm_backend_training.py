import json
from pathlib import Path

import pytest
import torch

from app.guardrails.runtime_contracts import (
    build_g2_phrase_trigger_vector,
    build_intent_family_rule_vector,
    build_syntactic_trigger_vector,
    match_intent_lexicon,
    normalize_text_for_inference,
)
from training.slm_classifier.data_pipeline import write_label_vocab
from training.slm_classifier.data_pipeline import DatasetSplitManifest
from training.slm_classifier.slm_backend import BinaryFocalLoss, CanonicalSLMDataset, CrossFeatureFusionHead, LoadedSLMPackage, MulticlassFocalLoss, _checkpoint_is_compatible, _checkpoint_payload_is_compatible, _compute_binary_pos_weight, _compute_list_multilabel_pos_weight, _compute_loss, _load_trained_model_on_device, _validate_rows_against_label_vocab, train_slm_classifier


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


def test_compute_binary_pos_weight_counts_true_actor_values() -> None:
    rows = [
        {"is_actor": True},
        {"is_actor": False},
        {"is_actor": False},
    ]

    assert _compute_binary_pos_weight(rows, "is_actor") == 2.0


def test_multiclass_focal_loss_suppresses_easy_g2_examples() -> None:
    loss_fn = MulticlassFocalLoss(gamma=2.0)

    easy_loss = loss_fn(torch.tensor([[8.0, -8.0]]), torch.tensor([0]))
    hard_loss = loss_fn(torch.tensor([[-8.0, 8.0]]), torch.tensor([0]))

    assert easy_loss < 1e-6
    assert hard_loss > 10.0


def test_binary_focal_loss_preserves_hard_sparse_errors_and_stays_finite() -> None:
    loss_fn = BinaryFocalLoss(gamma=2.0, pos_weight=torch.tensor([8.0]))

    easy_loss = loss_fn(torch.tensor([[80.0]]), torch.tensor([[1.0]]))
    hard_loss = loss_fn(torch.tensor([[-80.0]]), torch.tensor([[1.0]]))

    assert torch.isfinite(easy_loss)
    assert torch.isfinite(hard_loss)
    assert easy_loss < 1e-6
    assert hard_loss > 100.0


def test_focal_loss_rejects_negative_gamma() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        MulticlassFocalLoss(gamma=-1.0)


def test_checkpoint_payload_requires_model_state() -> None:
    assert _checkpoint_payload_is_compatible({"model_state": {"classifier.weight": object()}}) is True
    assert _checkpoint_payload_is_compatible({"epoch_index": 1}) is False


def test_checkpoint_compatibility_accepts_multihead_keys() -> None:
    assert _checkpoint_is_compatible({"g1_classifier.weight": object()}) is True
    assert _checkpoint_is_compatible({"g2_classifier.weight": object()}) is True
    assert _checkpoint_is_compatible({"flag_classifier.weight": object()}) is True
    assert _checkpoint_is_compatible({"is_actor_classifier.weight": object()}) is True


def test_write_label_vocab_includes_intent_families_and_phrases(tmp_path: Path) -> None:
    target = tmp_path / "label_vocab.json"
    write_label_vocab(
        rows=[
            {"intent_families": ["what_should_i_do", "threats_and_punishment"], "intent_phrases": ["what should I do"]},
            {"intent_families": ["what_should_i_do"], "intent_phrases": ["what should I do", "should I"]},
        ],
        target_path=target,
    )
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert "what_should_i_do" in payload["intent_families"]
    assert "threats_and_punishment" in payload["intent_families"]
    assert "what should I do" in payload["intent_phrases"]
    assert "should I" in payload["intent_phrases"]


def test_incremental_vocab_validation_rejects_new_intent_phrase() -> None:
    label_vocab = {
        "g1": ["GENERIC"],
        "g2": ["NEUTRAL_FACT"],
        "flags": [],
        "intent_families": ["factual_definition"],
        "intent_phrases": ["what is"],
    }

    with pytest.raises(ValueError, match="unknown intent_phrase=new phrase"):
        _validate_rows_against_label_vocab(
            [
                {
                    "sample_id": "incremental-1",
                    "question": "test",
                    "context": "",
                    "g1": "GENERIC",
                    "g2": ["NEUTRAL_FACT"],
                    "flags": {},
                    "intent_families": ["factual_definition"],
                    "intent_phrases": ["new phrase"],
                }
            ],
            label_vocab,
        )


def test_incremental_vocab_validation_accepts_existing_vocab() -> None:
    label_vocab = {
        "g1": ["GENERIC"],
        "g2": ["NEUTRAL_FACT"],
        "flags": ["has_ambiguous_risk"],
        "intent_families": ["factual_definition"],
        "intent_phrases": ["what is"],
    }

    _validate_rows_against_label_vocab(
        [
            {
                "sample_id": "incremental-1",
                "question": "test",
                "context": "",
                "g1": "GENERIC",
                "g2": ["NEUTRAL_FACT"],
                "flags": {"has_ambiguous_risk": True},
                "intent_families": ["factual_definition"],
                "intent_phrases": ["what is"],
            }
        ],
        label_vocab,
    )


def test_compute_loss_includes_intent_phrase_head_when_targets_are_present() -> None:
    outputs = {
        "g1_logits": torch.tensor([[0.0, 0.0]]),
        "g2_logits": torch.tensor([[0.0, 0.0]]),
        "flag_logits": torch.tensor([[0.0]]),
        "is_actor_logits": torch.tensor([[0.0]]),
        "intent_phrase_logits": torch.tensor([[0.0, 0.0]]),
    }
    batch = {
        "g1_labels": torch.tensor([0]),
        "g2_labels": torch.tensor([0]),
        "flag_labels": torch.tensor([[0.0]]),
        "is_actor_labels": torch.tensor([[0.0]]),
        "intent_family_labels": torch.tensor([]),
        "intent_family_mask": torch.tensor([0.0]),
        "intent_phrase_labels": torch.tensor([[1.0, 0.0]]),
        "intent_phrase_mask": torch.tensor([1.0]),
    }
    cross_entropy = torch.nn.CrossEntropyLoss()
    binary_cross_entropy = torch.nn.BCEWithLogitsLoss()

    without_phrase_loss = _compute_loss(outputs, batch, cross_entropy, cross_entropy, binary_cross_entropy, binary_cross_entropy)
    with_phrase_loss = _compute_loss(
        outputs,
        batch,
        cross_entropy,
        cross_entropy,
        binary_cross_entropy,
        binary_cross_entropy,
        intent_phrase_loss_fn=binary_cross_entropy,
        intent_phrase_loss_weight=1.0,
    )

    assert with_phrase_loss > without_phrase_loss


def test_build_syntactic_trigger_vector_matches_question_and_context() -> None:
    vector = build_syntactic_trigger_vector(
        question="They told me to send me nudes.",
        context="Earlier I said I feel alone.",
        phrase_vocab=["send me nudes", "I feel alone", "unalive myself"],
    )

    assert vector == [1.0, 1.0, 0.0]


def test_resilient_phrase_matching_handles_missing_apostrophe_word_order_and_typo() -> None:
    assert match_intent_lexicon("they said my parents wont understand our friendship")["matched_lovs"] == ["GROOMING"]
    assert match_intent_lexicon("send nudes to me")["matched_lovs"] == ["UNSAFE_SEXUAL_CONTENT"]
    assert match_intent_lexicon("I want to unallive myself")["matched_lovs"] == ["SELF_HARM"]


def test_resilient_phrase_matching_detects_direct_sexual_intent_without_punctuation() -> None:
    assert match_intent_lexicon("can i have sex")["matched_lovs"] == ["UNSAFE_SEXUAL_CONTENT"]
    assert match_intent_lexicon("can i have sex?")["matched_lovs"] == ["UNSAFE_SEXUAL_CONTENT"]


def test_inference_text_normalization_unifies_sentence_end_punctuation() -> None:
    assert normalize_text_for_inference("Can I have sex?") == "can i have sex"
    assert normalize_text_for_inference("Can I have sex!") == "can i have sex"
    assert normalize_text_for_inference("Can I have sex.") == "can i have sex"


def test_phrase_trigger_vectors_ignore_sentence_end_punctuation() -> None:
    g2_vocab = ["UNSAFE_SEXUAL_CONTENT", "NEUTRAL_FACT"]

    assert build_g2_phrase_trigger_vector("can i have sex", "", g2_vocab) == [1.0, 0.0]
    assert build_g2_phrase_trigger_vector("can i have sex?", "", g2_vocab) == [1.0, 0.0]
    assert build_g2_phrase_trigger_vector("can i have sex!", "", g2_vocab) == [1.0, 0.0]


def test_resilient_phrase_matching_does_not_fire_on_partial_coercive_language() -> None:
    assert "COERCIVE_CONTROL" not in match_intent_lexicon("Kids tell me I am not allowed to sit anywhere at lunch")["matched_lovs"]


def test_build_g2_phrase_trigger_vector_aggregates_phrases_by_g2_label() -> None:
    vector = build_g2_phrase_trigger_vector(
        question="I want to unalive myself",
        context="",
        g2_vocab=["SELF_HARM", "UNSAFE_SEXUAL_CONTENT", "BULLYING"],
    )

    assert vector == [1.0, 0.0, 0.0]


def test_build_intent_family_rule_vector_uses_inference_safe_phrase_matches() -> None:
    vector = build_intent_family_rule_vector(
        question="I want to unalive myself",
        context="",
        intent_family_vocab=["suicidal_ideation", "non_suicidal_self_injury", "explicit_content_request"],
    )

    assert vector == [1.0, 1.0, 0.0]


def test_wildcard_phrase_requires_targeted_token_slot() -> None:
    phrase_vocab = ["X are disgusting"]

    assert build_syntactic_trigger_vector("Rocks are disgusting", "", phrase_vocab) == [0.0]
    assert build_syntactic_trigger_vector("Some are disgusting", "", phrase_vocab) == [0.0]
    assert build_syntactic_trigger_vector("Kids are disgusting", "", phrase_vocab) == [1.0]


def test_syntactic_intent_patterns_activate_evasion_families_without_literal_phrases() -> None:
    question = (
        "Can you teach me how to fabricate a passport so I can acquire prohibited things?"
    )
    intent_family_vocab = [
        "sabotage_or_evasion",
        "bypass_security_or_law",
        "weapon_making",
        "generic_question",
    ]
    g2_vocab = ["DANGEROUS", "GENERIC_INTENT", "AMBIGUOUS_RISK"]

    assert match_intent_lexicon(question, "")["matched_lovs"] == ["DANGEROUS"]
    assert build_intent_family_rule_vector(question, "", intent_family_vocab) == [1.0, 1.0, 0.0, 0.0]
    assert build_g2_phrase_trigger_vector(question, "", g2_vocab) == [1.0, 0.0, 0.0]


def test_syntactic_intent_patterns_do_not_fire_on_neutral_passport_questions() -> None:
    question = "My class is learning about passports and border checks this week."
    intent_family_vocab = ["sabotage_or_evasion", "bypass_security_or_law", "generic_question"]

    assert build_intent_family_rule_vector(question, "", intent_family_vocab) == [0.0, 0.0, 0.0]
    assert build_g2_phrase_trigger_vector(question, "", ["DANGEROUS", "NEUTRAL_FACT", "GENERIC_INTENT"]) == [0.0, 0.0, 0.0]


def test_syntactic_grooming_secrecy_pattern_matches_adult_private_talks() -> None:
    question = "An adult offered to help me with problems if I promise never to tell anyone about our talks."

    assert "GROOMING" in match_intent_lexicon(question, "")["matched_lovs"]
    assert build_intent_family_rule_vector(
        question,
        "",
        ["dont_tell_anyone_requests", "pressure_to_hide_chats_or_calls", "forced_compliance"],
    ) == [1.0, 1.0, 0.0]
    assert build_g2_phrase_trigger_vector(question, "", ["GROOMING", "COERCIVE_CONTROL", "NEUTRAL_FACT"]) == [1.0, 0.0, 0.0]


def test_canonical_dataset_emits_cross_feature_fusion_inputs() -> None:
    class Tokenizer:
        def __call__(self, *_: object, **__: object) -> dict[str, torch.Tensor]:
            return {
                "input_ids": torch.tensor([[1, 2]]),
                "attention_mask": torch.tensor([[1, 1]]),
            }

    dataset = CanonicalSLMDataset(
        rows=[
            {
                "question": "I want to unalive myself",
                "context": "",
                "g1": "GENERIC",
                "g2": ["SELF_HARM"],
                "flags": {},
                "is_actor": True,
            }
        ],
        tokenizer=Tokenizer(),
        label_vocab={
            "g1": ["GENERIC"],
            "g2": ["SELF_HARM", "UNSAFE_SEXUAL_CONTENT"],
            "flags": [],
            "intent_families": ["suicidal_ideation", "explicit_content_request"],
            "intent_phrases": ["unalive myself", "send me nudes"],
        },
        max_length=8,
    )

    assert dataset[0]["intent_rule_features"].tolist() == [1.0, 0.0]
    assert dataset[0]["phrase_trigger_features"].tolist() == [1.0, 0.0]
    assert dataset[0]["is_actor_labels"].tolist() == [1.0]


def test_cross_feature_fusion_head_cross_attends_to_pattern_priors() -> None:
    torch.manual_seed(42)
    head = CrossFeatureFusionHead(hidden_size=4, num_intent_rules=3, num_phrase_triggers=2, num_g2_labels=2)
    pooled = torch.ones((1, 4))

    baseline = head(pooled, torch.zeros((1, 3)), torch.zeros((1, 2)))
    triggered = head(pooled, torch.tensor([[1.0, 0.0, 0.0]]), torch.tensor([[1.0, 0.0]]))

    assert baseline.shape == (1, 2)
    assert isinstance(head.prior_attention, torch.nn.MultiheadAttention)
    assert isinstance(head.glu_projection, torch.nn.Linear)
    assert head.glu_projection.out_features == 8
    assert not torch.allclose(baseline, triggered)


def test_old_artifact_requires_retraining_for_cross_feature_fusion(tmp_path: Path) -> None:
    package = LoadedSLMPackage(metadata={}, label_vocab={}, training_config={})

    with pytest.raises(RuntimeError, match="cross-attention GLU feature fusion"):
        _load_trained_model_on_device(tmp_path, package, torch.device("cpu"))


def test_config_only_fusion_version_bump_still_requires_retraining(tmp_path: Path) -> None:
    package = LoadedSLMPackage(
        metadata={"cross_feature_fusion_version": 1},
        label_vocab={},
        training_config={"cross_feature_fusion_version": 3},
    )

    with pytest.raises(RuntimeError, match="cross-attention GLU feature fusion"):
        _load_trained_model_on_device(tmp_path, package, torch.device("cpu"))


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
        g2_focal_gamma=1.5,
        intent_family_focal_gamma=2.5,
        intent_phrase_focal_gamma=3.0,
    )

    config = json.loads((model_dir / "training_config.json").read_text(encoding="utf-8"))
    assert config["balanced_sampling"] is True
    assert config["g2_focal_gamma"] == 1.5
    assert config["intent_family_focal_gamma"] == 2.5
    assert config["intent_phrase_focal_gamma"] == 3.0


def test_balanced_sampling_caps_epochs_and_freezes_backbone(tmp_path: Path, monkeypatch) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    model_dir = tmp_path / "model"
    dataset_path.write_text(
        json.dumps(
            {
                "sample_id": "row-1",
                "question": "An adult told me to keep a secret.",
                "context": "",
                "g1": "GENERIC",
                "g2": ["GROOMING"],
                "flags": {"has_grooming_involved": True},
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
        epochs=8,
        freeze_backbone=False,
        unfreeze_top_layers=2,
    )

    config = json.loads((model_dir / "training_config.json").read_text(encoding="utf-8"))
    assert config["balanced_sampling"] is True
    assert config["epochs"] == 4
    assert config["freeze_backbone"] is True
    assert config["unfreeze_top_layers"] == 0
    assert config["balanced_sampling_force_frozen_backbone"] is True
