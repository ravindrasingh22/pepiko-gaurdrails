from training.slm_classifier.infer import _normalize_input
from training.slm_classifier.infer import _parse_thresholds
from training.slm_classifier.infer import _resolve_threshold
from training.slm_classifier.infer import run_infer


def test_infer_cli_normalizes_alias_age_band_to_expected_age() -> None:
    normalized = _normalize_input(
        question="Who is God?",
        age_band="11-12",
        language="en",
        context="none",
    )

    assert normalized["child_profile"]["age"] == 12
    assert normalized["child_profile"]["age_group"] == "11-12"


def test_infer_cli_falls_back_to_lower_valid_age_band_for_invalid_band() -> None:
    normalized = _normalize_input(
        question="Who is God?",
        age_band="8-10",
        language="en",
        context="none",
    )

    assert normalized["child_profile"]["age"] == 12
    assert normalized["child_profile"]["age_group"] == "8-10"


def test_infer_cli_canonicalizes_missing_question_mark_for_question_intent() -> None:
    with_question_mark = _normalize_input(
        question="can i have sex?",
        age_band="11-12",
        language="en",
        context="none",
    )
    without_question_mark = _normalize_input(
        question="can i have sex",
        age_band="11-12",
        language="en",
        context="none",
    )

    assert with_question_mark["text"] == without_question_mark["text"]


def test_run_infer_preserves_thresholded_runtime_classifier_output() -> None:
    result = run_infer(
        mode="slm",
        question="Which religion should I follow?",
        age_band="9-10",
        language="en",
        context="none",
        threshold=0.8,
    )

    assert "applies_when_flags" not in result
    assert "flag_overrides" not in result
    assert "flags" in result
    assert "predicted_families" in result
    assert "predicted_phrases" in result
    assert isinstance(result["predicted_families"], list)
    assert isinstance(result["predicted_phrases"], list)
    assert "topic" not in result
    assert isinstance(result["g2"]["id"], str)
    assert result["g2"]["id"]


def test_parse_thresholds_accepts_json_object() -> None:
    thresholds = _parse_thresholds('{"default": 0.65, "G2": 0.72}')

    assert thresholds == {"default": 0.65, "G2": 0.72}


def test_resolve_threshold_uses_thresholds_when_threshold_is_omitted() -> None:
    resolved = _resolve_threshold(None, {"default": 0.67, "G2": 0.72})

    assert resolved == 0.67


def test_resolve_threshold_prefers_explicit_threshold_over_thresholds() -> None:
    resolved = _resolve_threshold(0.81, {"default": 0.67})

    assert resolved == 0.81


def test_run_infer_returns_thresholds_when_provided() -> None:
    result = run_infer(
        mode="slm",
        question="Which religion should I follow?",
        age_band="9-10",
        language="en",
        context="none",
        thresholds={"default": 0.8, "G2": 0.75},
    )

    assert result["threshold"] == 0.8
    assert result["thresholds"] == {"default": 0.8, "G2": 0.75}


def test_run_infer_surfaces_fused_secrecy_label_for_slm_output() -> None:
    result = run_infer(
        mode="slm",
        question="Don't tell anyone about our conversations, okay?",
        age_band="9-10",
        language="en",
        context="none",
        threshold=20.0,
    )

    assert result["g2"]["id"] == "COERCIVE_CONTROL"
    assert "COERCIVE_CONTROL" in result["g2_all"]["ids"]
    assert "source=heuristic_fusion" in result["g2_all"]["selection_reasons"]["COERCIVE_CONTROL"]
