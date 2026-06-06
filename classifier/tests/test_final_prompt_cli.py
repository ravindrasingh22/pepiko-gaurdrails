from training.slm_classifier.final_prompt import _final_prompt


def test_final_prompt_cli_prints_prompt_text() -> None:
    prompt = _final_prompt(
        mode="heuristic",
        question="Who is God?",
        age_band="7-8",
        language="en",
        recent_context="none",
    )

    assert "You are PikuAI, a child-safe learning assistant." in prompt
    assert "Question:" not in prompt
