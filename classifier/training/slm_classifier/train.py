import argparse
from pathlib import Path

from training.slm_classifier.codebook import codebook_latest_mtime
from training.slm_classifier.data_pipeline import CANONICAL_DATASET, LABEL_VOCAB_PATH, write_manifest
from training.slm_classifier.slm_backend import available_cores, model_dir_for_core, resolve_core, train_slm_classifier
from training.slm_classifier.source_normalizer import write_canonical_jsonl


def _parse_bool_flag(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected true/false, got: {value}")


def _dataset_is_stale(dataset_path: Path = CANONICAL_DATASET) -> bool:
    if not dataset_path.exists():
        return True
    raw_dir = dataset_path.parents[1] / "raw"
    dataset_mtime = dataset_path.stat().st_mtime
    if codebook_latest_mtime() > dataset_mtime:
        return True
    for path in raw_dir.glob("*.csv"):
        if path.name.startswith(".") or path.name.lower() == "gl-codebook.csv":
            continue
        if path.stat().st_mtime > dataset_mtime:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the SLM classifier for a selected core model.")
    parser.add_argument("--core", choices=available_cores(), default="deberta")
    parser.add_argument("--device", choices=["auto", "cpu", "mps"], default="auto")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--max-length", type=int, default=None)
    parser.add_argument("--freeze-backbone", type=_parse_bool_flag, default=None)
    parser.add_argument("--unfreeze-top-layers", type=int, default=None)
    parser.add_argument("--learning-rate", type=float, default=None)
    parser.add_argument("--head-learning-rate", type=float, default=None)
    parser.add_argument("--g1-loss-weight", type=float, default=None)
    parser.add_argument("--g2-loss-weight", type=float, default=None)
    parser.add_argument("--flag-loss-weight", type=float, default=None)
    parser.add_argument("--flag-max-pos-weight", type=float, default=None)
    parser.add_argument("--intent-family-max-pos-weight", type=float, default=None)
    parser.add_argument("--intent-phrase-max-pos-weight", type=float, default=None)
    parser.add_argument("--g2-focal-gamma", type=float, default=None)
    parser.add_argument("--intent-family-focal-gamma", type=float, default=None)
    parser.add_argument("--intent-phrase-focal-gamma", type=float, default=None)
    parser.add_argument("--train-intent-heads", type=_parse_bool_flag, default=None)
    parser.add_argument(
        "--balanced-sampling",
        type=_parse_bool_flag,
        default=None,
        help="Oversample rare G2 labels during training (WeightedRandomSampler).",
    )
    parser.add_argument("--checkpoint-every-batches", type=int, default=None)
    parser.add_argument("--resume", action="store_true", help="Resume from an existing checkpoint if present.")
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Rebuild the canonical dataset from current raw files and continue training from the latest compatible checkpoint.",
    )
    parser.add_argument(
        "--train-on-all-data",
        action="store_true",
        help="Use all canonical dataset rows for training instead of reserving dev/test splits.",
    )
    parser.add_argument(
        "--rebuild-dataset",
        action="store_true",
        help="Force canonical dataset regeneration from raw files before training.",
    )
    args = parser.parse_args()
    core = resolve_core(args.core)
    model_dir = model_dir_for_core(core)
    manifest = write_manifest()
    rebuild_dataset = bool(args.rebuild_dataset or args.continuous or _dataset_is_stale())
    resume_training = bool(args.resume or args.continuous)
    if rebuild_dataset:
        write_canonical_jsonl()
    else:
        print(f"Using existing canonical dataset: {CANONICAL_DATASET}")
    if args.continuous:
        print("Continuous training enabled: rebuilding dataset from data/raw and resuming from the latest compatible checkpoint.")
    elif resume_training:
        print("Checkpoint resume enabled: existing model weights may be reused.")
    else:
        print("Checkpoint resume disabled: training starts from a fresh model initialization.")
    slm_metadata = train_slm_classifier(
        enable_training=True,
        core=core,
        model_dir=model_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        max_length=args.max_length,
        device=args.device,
        freeze_backbone=args.freeze_backbone,
        unfreeze_top_layers=args.unfreeze_top_layers,
        learning_rate=args.learning_rate,
        head_learning_rate=args.head_learning_rate,
        g1_loss_weight=args.g1_loss_weight,
        g2_loss_weight=args.g2_loss_weight,
        flag_loss_weight=args.flag_loss_weight,
        flag_max_pos_weight=args.flag_max_pos_weight,
        intent_family_max_pos_weight=args.intent_family_max_pos_weight,
        intent_phrase_max_pos_weight=args.intent_phrase_max_pos_weight,
        g2_focal_gamma=args.g2_focal_gamma,
        intent_family_focal_gamma=args.intent_family_focal_gamma,
        intent_phrase_focal_gamma=args.intent_phrase_focal_gamma,
        train_intent_heads=args.train_intent_heads,
        balanced_sampling=args.balanced_sampling,
        resume_if_available=resume_training,
        train_on_all_data=args.train_on_all_data,
        checkpoint_every_batches=args.checkpoint_every_batches,
    )
    print("SLM classifier training complete.")
    print(f"Core model: {core}")
    print(f"Canonical dataset: {CANONICAL_DATASET}")
    print(f"Label vocab: {LABEL_VOCAB_PATH}")
    print(f"Pending raw sources: {len(manifest.pending_sources)}")
    for path in manifest.pending_sources:
        print(f" - source: {path}")
    print(f"SLM model package: {model_dir}")
    print(f"Requested device: {args.device}")
    print(f"Train on all data: {args.train_on_all_data}")
    print(f"Balanced sampling: {slm_metadata.get('balanced_sampling', args.balanced_sampling)}")
    print(f"Balanced sampling max epochs: {slm_metadata.get('balanced_sampling_max_epochs', 'n/a')}")
    print(f"Freeze backbone: {slm_metadata.get('freeze_backbone', args.freeze_backbone)}")
    print(f"Unfreeze top layers: {slm_metadata.get('unfreeze_top_layers', args.unfreeze_top_layers)}")
    print(f"Continuous training: {args.continuous}")
    print(f"Checkpoint every batches: {args.checkpoint_every_batches}")
    print(f"SLM training backend: {slm_metadata['training_backend']}")
    print(f"SLM resumed from existing checkpoint: {slm_metadata.get('resumed_from_existing', False)}")
    if "test_gate_metrics" in slm_metadata:
        print(f"Test G1 accuracy: {slm_metadata['test_gate_metrics'].get('g1_accuracy', 0.0):.4f}")
        print(f"Test G1 macro F1: {slm_metadata['test_gate_metrics'].get('g1_macro_f1', 0.0):.4f}")
        print(f"Test G1 weighted F1: {slm_metadata['test_gate_metrics'].get('g1_weighted_f1', 0.0):.4f}")
        print(f"Test G2 accuracy: {slm_metadata['test_gate_metrics'].get('g2_accuracy', 0.0):.4f}")
        print(f"Test G2 macro F1: {slm_metadata['test_gate_metrics'].get('g2_macro_f1', 0.0):.4f}")
        print(f"Test G2 weighted F1: {slm_metadata['test_gate_metrics'].get('g2_weighted_f1', 0.0):.4f}")
        flag_metrics = slm_metadata["test_gate_metrics"].get("flags", {})
        print(f"Test flags exact-match accuracy: {flag_metrics.get('exact_match_accuracy', 0.0):.4f}")
        print(f"Test flags micro precision: {flag_metrics.get('micro_precision', 0.0):.4f}")
        print(f"Test flags micro recall: {flag_metrics.get('micro_recall', 0.0):.4f}")
        print(f"Test flags micro F1: {flag_metrics.get('micro_f1', 0.0):.4f}")
        print(f"Test flags macro F1: {flag_metrics.get('macro_f1', 0.0):.4f}")
        intent_family_metrics = slm_metadata["test_gate_metrics"].get("intent_families", {})
        print(f"Test intent-family exact-match accuracy: {intent_family_metrics.get('exact_match_accuracy', 0.0):.4f}")
        print(f"Test intent-family micro precision: {intent_family_metrics.get('micro_precision', 0.0):.4f}")
        print(f"Test intent-family micro recall: {intent_family_metrics.get('micro_recall', 0.0):.4f}")
        print(f"Test intent-family micro F1: {intent_family_metrics.get('micro_f1', 0.0):.4f}")
        print(f"Test intent-family macro F1: {intent_family_metrics.get('macro_f1', 0.0):.4f}")
        intent_phrase_metrics = slm_metadata["test_gate_metrics"].get("intent_phrases", {})
        print(f"Test intent-phrase exact-match accuracy: {intent_phrase_metrics.get('exact_match_accuracy', 0.0):.4f}")
        print(f"Test intent-phrase micro precision: {intent_phrase_metrics.get('micro_precision', 0.0):.4f}")
        print(f"Test intent-phrase micro recall: {intent_phrase_metrics.get('micro_recall', 0.0):.4f}")
        print(f"Test intent-phrase micro F1: {intent_phrase_metrics.get('micro_f1', 0.0):.4f}")
        print(f"Test intent-phrase macro F1: {intent_phrase_metrics.get('macro_f1', 0.0):.4f}")
        print(f"Dominant G2 share: {slm_metadata.get('dominant_g2_share', 0.0):.4f}")
    if slm_metadata.get("degenerate_head_warning"):
        print(f"WARNING: {slm_metadata['degenerate_head_warning']}")


if __name__ == "__main__":
    main()
