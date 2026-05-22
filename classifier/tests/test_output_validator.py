from app.guardrails.output_validator import validate


def test_output_validator_detects_secrecy() -> None:
    result = validate(None, "test", "Keep it secret and hide it.", None)
    assert result["safe_to_show"] is False
