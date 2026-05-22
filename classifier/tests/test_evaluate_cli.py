from training.slm_classifier.evaluate import evaluate_classifier
from training.slm_classifier.artifact_backend import train_artifact
from training.slm_classifier.slm_backend import train_slm_classifier


def test_evaluate_classifier_returns_gate_metrics() -> None:
    results = evaluate_classifier(max_rows=200)

    assert results["dataset_rows"] > 0
    assert "gate_metrics" in results
    assert "G1_accuracy" in results["gate_metrics"]


def test_evaluate_classifier_artifact_mode_returns_gate_metrics() -> None:
    train_artifact()
    results = evaluate_classifier(mode="artifact", max_rows=200)

    assert results["dataset_rows"] > 0
    assert results["mode"] == "artifact"
    assert "gate_metrics" in results


def test_evaluate_classifier_slm_mode_returns_gate_metrics() -> None:
    train_slm_classifier(core="smol")
    results = evaluate_classifier(mode="slm", max_rows=200, core="smol")

    assert results["mode"] == "slm"
    assert results["core_model"] == "smol"
    assert "gate_metrics" in results
    assert "g2_metrics" in results
    assert "G2_accuracy" in results["gate_metrics"]
    assert "macro_f1" in results["g2_metrics"]
    assert "weighted_f1" in results["g2_metrics"]
    assert "G1" in results["confusion"]


def test_evaluate_classifier_print_rows_emits_header_once(capsys) -> None:
    evaluate_classifier(max_rows=2, print_rows=True)

    output = capsys.readouterr().out.strip().splitlines()
    assert output
    assert output[0] == "row_index\tsample_id\tgold_g1\tpred_g1\tgold_g2\tpred_g2\tmatch\tquestion"
    assert len(output) == 3


def test_evaluate_classifier_writes_output_csv(tmp_path) -> None:
    output_csv = tmp_path / "eval_rows.csv"

    results = evaluate_classifier(max_rows=2, output_csv=output_csv)

    assert results["output_csv"] == str(output_csv)
    lines = output_csv.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert lines[0] == "row_index,sample_id,question,language,recent_context,g1,pred_g1,g2,pred_g2,g1_match,g2_match,exact_match"
