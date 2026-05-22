from training.slm_classifier.base_model_cli import _build_prompt


def test_base_model_cli_builds_direct_prompt() -> None:
    prompt = _build_prompt(
        question="Who is God?",
        age_band="7-8",
        language="en",
    )

    assert "age band 7-8" in prompt
    assert "Question: Who is God?" in prompt
    assert prompt.endswith("Answer:")
