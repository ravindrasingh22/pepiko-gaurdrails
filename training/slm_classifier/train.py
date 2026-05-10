from training.slm_classifier.artifact_backend import ARTIFACT_PATH, train_artifact
from training.slm_classifier.data_pipeline import CANONICAL_DATASET, GL_COLUMNS, write_manifest
from training.slm_classifier.source_normalizer import write_canonical_jsonl


def main() -> None:
    manifest = write_manifest()
    write_canonical_jsonl()
    artifact = train_artifact()
    print("SLM classifier artifact training complete.")
    print(f"Canonical dataset: {CANONICAL_DATASET}")
    print(f"Multi-label outputs: {', '.join(GL_COLUMNS)}")
    print(f"Pending raw sources: {len(manifest.pending_sources)}")
    for path in manifest.pending_sources:
        print(f" - source: {path}")
    print(f"Artifact output: {ARTIFACT_PATH}")
    print(f"Trained labels: {len(artifact['labels'])}")


if __name__ == "__main__":
    main()
