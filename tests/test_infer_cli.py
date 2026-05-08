from training.slm_classifier.infer import _run_classifier


def test_infer_cli_returns_gates_and_contract() -> None:
    result = _run_classifier(
        mode="artifact",
        question="Who is God?",
        age_band="5-8",
        language="en",
        recent_context="none",
    )

    assert result["mode"] == "artifact"
    assert "gates" in result
    assert "prompt_contract" in result
    assert "backend" in result
