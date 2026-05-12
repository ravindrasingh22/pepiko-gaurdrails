from training.slm_classifier.evaluate import evaluate_classifier
from training.slm_classifier.artifact_backend import train_artifact
from training.slm_classifier.slm_backend import train_slm_classifier


def test_evaluate_classifier_returns_label_metrics() -> None:
    results = evaluate_classifier(max_rows=200)

    assert results["dataset_rows"] > 0
    assert "GL-01" in results["labels"]
    assert "f1" in results["labels"]["GL-01"]


def test_evaluate_classifier_artifact_mode_returns_label_metrics() -> None:
    train_artifact()
    results = evaluate_classifier(mode="artifact", max_rows=200)

    assert results["dataset_rows"] > 0
    assert results["mode"] == "artifact"
    assert "GL-01" in results["labels"]


def test_evaluate_classifier_slm_mode_returns_gate_metrics() -> None:
    train_slm_classifier(core="smol")
    results = evaluate_classifier(mode="slm", max_rows=200, core="smol")

    assert results["mode"] == "slm"
    assert results["core_model"] == "smol"
    assert "gate_metrics" in results
    assert "G2_accuracy" in results["gate_metrics"]
    assert "macro_f1" in results["gl_summary"]
    assert "G1" in results["confusion"]
