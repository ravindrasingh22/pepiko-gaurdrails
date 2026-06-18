from fastapi.testclient import TestClient

import app.api.routes as routes
from app.main import app
from app.text_normalization_service import apply_deterministic_cleanup, normalize_child_message


client = TestClient(app)


def test_apply_deterministic_cleanup_repairs_mojibake_and_whitespace() -> None:
    raw = '  why   do   pepol   prae\u201chello\u201d  '
    assert apply_deterministic_cleanup(raw) == 'why do pepol prae"hello"'


def test_normalize_child_message_parses_json_answer(monkeypatch) -> None:
    captured_messages = []

    def fake_generate_chat_response(**kwargs):
        captured_messages.extend(kwargs["messages"])
        return {
            "model_name": "gemma:2b-instruct",
            "answer": (
                '{"normalized_message": "Why do people pray?", '
                '"repairs": ["fixed spelling", "added punctuation"]}'
            ),
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 18,
                "total_tokens": 138,
            },
        }

    monkeypatch.setattr(
        "app.text_normalization_service.generate_chat_response",
        fake_generate_chat_response,
    )

    result = normalize_child_message(
        raw_message="y do pepol prae",
        child_profile={"age": 10, "age_group": "9-10", "language": "en"},
        system_prompt="Return normalized JSON only.",
    )

    assert captured_messages[0] == {"role": "system", "content": "Return normalized JSON only."}
    assert result["normalized_message"] == "Why do people pray?"
    assert result["repairs"] == ["fixed spelling", "added punctuation"]
    assert result["usage"]["total_tokens"] == 138


def test_text_normalization_endpoint_returns_normalized_message(monkeypatch) -> None:
    captured_kwargs = {}

    def fake_normalize_child_message(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "model_name": "gemma:2b-instruct",
            "raw_message": kwargs["raw_message"],
            "preprocessed_message": "y do pepol prae? mummy se kaise chupaun?",
            "normalized_message": "Why do people pray? How do I hide it from mummy?",
            "repairs": ["fixed spelling", "clarified Hinglish phrase"],
            "usage": {
                "prompt_tokens": 140,
                "completion_tokens": 24,
                "total_tokens": 164,
            },
        }

    monkeypatch.setattr(routes, "normalize_child_message", fake_normalize_child_message)

    child_profile = {
        "age": 10,
        "age_group": "9-10",
        "language": "hinglish",
    }
    response = client.post(
        "/api/v1/guardrail/text-normalization",
        json={
            "session_id": "normalize-001",
            "child_profile": child_profile,
            "message": "y do pepol prae? mummy se kaise chupaun?",
            "system_prompt": "Normalize the child message and return JSON.",
            "recent_context": ["Child: I got bad marks today."],
            "input_mode": "voice",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "normalize-001"
    assert payload["child_profile"] == child_profile
    assert payload["raw_message"] == "y do pepol prae? mummy se kaise chupaun?"
    assert payload["normalized_message"] == "Why do people pray? How do I hide it from mummy?"
    assert payload["repairs"] == ["fixed spelling", "clarified Hinglish phrase"]
    assert payload["usage"]["total_tokens"] == 164
    assert captured_kwargs["system_prompt"] == "Normalize the child message and return JSON."
