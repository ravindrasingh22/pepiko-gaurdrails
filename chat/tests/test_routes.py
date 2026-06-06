from fastapi.testclient import TestClient

import app.api.routes as routes
from app.main import app


client = TestClient(app)


def test_chat_response_skips_validator_by_default(monkeypatch) -> None:
    def fake_generate_chat_response(**kwargs):
        return {
            "model_name": "gemma:2b-instruct",
            "answer": "Safe answer.",
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5,
            },
        }

    monkeypatch.setattr(routes, "generate_chat_response", fake_generate_chat_response)
    monkeypatch.setattr(
        routes,
        "validate_assistant_response",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("validator should not be called by default")),
    )

    child_profile = {
        "age": 11,
        "age_group": "11-12",
        "language": "en",
    }
    response = client.post(
        "/api/v1/guardrail/chat",
        json={
            "session_id": "chat-001",
            "child_profile": child_profile,
            "message": "Why is the sky blue?",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "chat-001"
    assert payload["child_profile"] == child_profile
    assert payload["choices"][0]["message"]["content"] == "Safe answer."
    assert payload["response_validation"] is None
    assert payload["validation_score"] is None
    assert payload["validator_usage"] is None


def test_chat_response_includes_validation_when_requested(monkeypatch) -> None:
    def fake_generate_chat_response(**kwargs):
        return {
            "model_name": "gemma:2b-instruct",
            "answer": "Safe answer.",
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5,
            },
        }

    monkeypatch.setattr(routes, "generate_chat_response", fake_generate_chat_response)
    monkeypatch.setattr(
        routes,
        "validate_assistant_response",
        lambda **kwargs: {
            "response_validation": "Safe",
            "validation_score": 0.92,
            "validator_usage": {
                "prompt_tokens": 9,
                "completion_tokens": 0,
                "total_tokens": 9,
            },
        },
    )

    child_profile = {
        "age": 11,
        "age_group": "11-12",
        "language": "en",
    }
    response = client.post(
        "/api/v1/guardrail/chat",
        json={
            "session_id": "chat-001",
            "child_profile": child_profile,
            "message": "Why is the sky blue?",
            "validate_response": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "chat-001"
    assert payload["child_profile"] == child_profile
    assert payload["choices"][0]["message"]["content"] == "Safe answer."
    assert payload["response_validation"] == "Safe"
    assert payload["validation_score"] == 0.92
    assert payload["validator_usage"] == {
        "prompt_tokens": 9,
        "completion_tokens": 0,
        "total_tokens": 9,
    }
