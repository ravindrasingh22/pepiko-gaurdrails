from training.slm_classifier.evaluate import evaluate_classifier
from training.slm_classifier.artifact_backend import train_artifact


def test_evaluate_classifier_returns_label_metrics() -> None:
    results = evaluate_classifier()

    assert results["dataset_rows"] > 0
    assert "GL-01" in results["labels"]
    assert "f1" in results["labels"]["GL-01"]


def test_evaluate_classifier_artifact_mode_returns_label_metrics() -> None:
    train_artifact()
    results = evaluate_classifier(mode="artifact")

    assert results["dataset_rows"] > 0
    assert results["mode"] == "artifact"
    assert "GL-01" in results["labels"]
