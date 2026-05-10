from training.slm_classifier.base_encoder_cli import _build_text


def test_base_encoder_cli_builds_structured_input() -> None:
    text = _build_text(
        question="Who is God?",
        age_band="7-8",
        language="en",
    )

    assert "Age band: 7-8" in text
    assert "Language: en" in text
    assert "Question: Who is God?" in text
