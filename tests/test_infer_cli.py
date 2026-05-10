from training.slm_classifier.infer import _run_classifier
from training.slm_classifier.infer import _normalize_input


def test_infer_cli_returns_gates_and_contract() -> None:
    result = _run_classifier(
        mode="artifact",
        question="Who is God?",
        age_band="7-8",
        language="en",
        recent_context="none",
    )

    assert result["mode"] == "artifact"
    assert "gates" in result
    assert "prompt_contract" in result
    assert "backend" in result


def test_infer_cli_normalizes_alias_age_band_to_expected_age() -> None:
    normalized = _normalize_input(
        question="Who is God?",
        age_band="11-12",
        language="en",
        recent_context="none",
    )

    assert normalized["child_profile"]["age"] == 12
    assert normalized["child_profile"]["age_group"] == "11-12"


def test_infer_cli_falls_back_to_lower_valid_age_band_for_invalid_band() -> None:
    normalized = _normalize_input(
        question="Who is God?",
        age_band="8-10",
        language="en",
        recent_context="none",
    )

    assert normalized["child_profile"]["age"] == 8
    assert normalized["child_profile"]["age_group"] == "7-8"
