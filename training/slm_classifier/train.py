import argparse

from training.slm_classifier.data_pipeline import CANONICAL_DATASET, GL_COLUMNS, LABEL_VOCAB_PATH, write_manifest
from training.slm_classifier.slm_backend import available_cores, model_dir_for_core, resolve_core, train_slm_classifier
from training.slm_classifier.source_normalizer import write_canonical_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the SLM classifier for a selected core model.")
    parser.add_argument("--core", choices=available_cores(), default="smol")
    args = parser.parse_args()
    core = resolve_core(args.core)
    model_dir = model_dir_for_core(core)
    manifest = write_manifest()
    write_canonical_jsonl()
    slm_metadata = train_slm_classifier(enable_training=True, core=core, model_dir=model_dir)
    print("SLM classifier training complete.")
    print(f"Core model: {core}")
    print(f"Canonical dataset: {CANONICAL_DATASET}")
    print(f"Multi-label outputs: {', '.join(GL_COLUMNS)}")
    print(f"Label vocab: {LABEL_VOCAB_PATH}")
    print(f"Pending raw sources: {len(manifest.pending_sources)}")
    for path in manifest.pending_sources:
        print(f" - source: {path}")
    print(f"SLM model package: {model_dir}")
    print(f"SLM training backend: {slm_metadata['training_backend']}")
    print(f"SLM resumed from existing checkpoint: {slm_metadata.get('resumed_from_existing', False)}")


if __name__ == "__main__":
    main()
