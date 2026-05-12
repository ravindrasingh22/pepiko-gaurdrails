import argparse

from training.slm_classifier.data_pipeline import CANONICAL_DATASET, GL_COLUMNS, LABEL_VOCAB_PATH, write_manifest
from training.slm_classifier.slm_backend import available_cores, model_dir_for_core, resolve_core, train_slm_classifier
from training.slm_classifier.source_normalizer import write_canonical_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the SLM classifier for a selected core model.")
    parser.add_argument("--core", choices=available_cores(), default="smol")
    parser.add_argument("--device", choices=["auto", "cpu", "mps"], default="auto")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--max-length", type=int, default=None)
    parser.add_argument("--resume", action="store_true", help="Resume from an existing checkpoint if present.")
    parser.add_argument(
        "--train-on-all-data",
        action="store_true",
        help="Use all canonical dataset rows for training instead of reserving dev/test splits.",
    )
    args = parser.parse_args()
    core = resolve_core(args.core)
    model_dir = model_dir_for_core(core)
    manifest = write_manifest()
    write_canonical_jsonl()
    slm_metadata = train_slm_classifier(
        enable_training=True,
        core=core,
        model_dir=model_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        max_length=args.max_length,
        device=args.device,
        resume_if_available=args.resume,
        train_on_all_data=args.train_on_all_data,
    )
    print("SLM classifier training complete.")
    print(f"Core model: {core}")
    print(f"Canonical dataset: {CANONICAL_DATASET}")
    print(f"Multi-label outputs: {', '.join(GL_COLUMNS)}")
    print(f"Label vocab: {LABEL_VOCAB_PATH}")
    print(f"Pending raw sources: {len(manifest.pending_sources)}")
    for path in manifest.pending_sources:
        print(f" - source: {path}")
    print(f"SLM model package: {model_dir}")
    print(f"Requested device: {args.device}")
    print(f"Train on all data: {args.train_on_all_data}")
    print(f"SLM training backend: {slm_metadata['training_backend']}")
    print(f"SLM resumed from existing checkpoint: {slm_metadata.get('resumed_from_existing', False)}")


if __name__ == "__main__":
    main()
