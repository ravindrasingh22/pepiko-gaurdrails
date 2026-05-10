from training.slm_classifier.codebook import parse_codebook


def test_codebook_parses_age_policy_runtime_block() -> None:
    codebook = parse_codebook()

    assert codebook.age_bands["5-6"].max_words == 90
    assert codebook.age_bands["5-6"].max_answer_style == "Warm, concrete, one idea"
    assert codebook.age_bands["5-6"].depth == "CONCRETE_ONE_STEP"
    assert codebook.age_bands["9-10"].max_answer_style == "Clear, cause-effect, brief steps"
    assert codebook.age_bands["17"].tone == "age_calibrated"
    assert codebook.parent_visibility.force_visible_if_age_lte == 10
    assert codebook.parent_visibility.risk_levels == ["medium", "high", "critical"]
