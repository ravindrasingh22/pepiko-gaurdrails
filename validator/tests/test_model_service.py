from app.model_service import format_validator_input, validate_response_with_score


def test_format_validator_input_uses_training_schema() -> None:
    assert (
        format_validator_input("5-7", "The little yellow duck   swam.")
        == "Age Group: 5-7 | Content: The little yellow duck swam."
    )


def test_validator_fallback_marks_safe_text_as_safe() -> None:
    result = validate_response_with_score(
        age_group="5-7",
        response_text="The little yellow duck swam across the blue pond.",
        model_path="/tmp/missing-validator-model",
    )

    assert result.status == "safe"
    assert result.label == 0
    assert result.action == "allow"
    assert result.delivered_text == "The little yellow duck swam across the blue pond."
    assert result.usage["prompt_tokens"] > 0
    assert result.usage["completion_tokens"] == 0


def test_validator_fallback_replaces_unsafe_text() -> None:
    result = validate_response_with_score(
        age_group="5-7",
        response_text="The scary dark ghost jumped out with a sharp knife.",
        model_path="/tmp/missing-validator-model",
    )

    assert result.status == "unsafe"
    assert result.label == 1
    assert result.action == "fallback"
    assert result.fallback_text
    assert result.delivered_text == result.fallback_text
    assert result.usage["total_tokens"] == result.usage["prompt_tokens"]
