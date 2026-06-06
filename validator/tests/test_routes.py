from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_validate_endpoint_returns_safe_contract() -> None:
    response = client.post(
        "/api/v1/guardrail/validate",
        json={
            "session_id": "validate-001",
            "age_group": "5-7",
            "response_text": "The little yellow duck swam across the blue pond.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "safe"
    assert payload["label"] == 0
    assert payload["input"]["age_group"] == "5-7"
    assert payload["model"]["threshold"] == 0.85
    assert payload["usage"]["prompt_tokens"] > 0
    assert payload["usage"]["completion_tokens"] == 0
    assert payload["usage"]["total_tokens"] == payload["usage"]["prompt_tokens"]
    assert payload["route"]["action"] == "allow"


def test_validate_endpoint_returns_fallback_for_unsafe_contract() -> None:
    response = client.post(
        "/api/v1/guardrail/validate",
        json={
            "session_id": "validate-002",
            "age_group": "5-7",
            "response_text": "The scary dark ghost jumped out with a sharp knife.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unsafe"
    assert payload["label"] == 1
    assert payload["scores"]["unsafe"] >= 0.85
    assert payload["route"]["action"] == "fallback"
    assert payload["route"]["delivered_text"] == payload["route"]["fallback_text"]


def test_validate_endpoint_accepts_legacy_answer_payload() -> None:
    response = client.post(
        "/api/v1/guardrail/validate",
        json={
            "session_id": "validate-legacy-001",
            "child_profile": {"age_group": "8-12", "language": "en"},
            "answer": "The little yellow duck swam across the blue pond.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["input"]["age_group"] == "8-12"
    assert payload["status"] == "safe"


def test_validate_endpoint_accepts_lightweight_assistant_message_payload() -> None:
    response = client.post(
        "/api/v1/guardrail/validate",
        json={
            "message": {
                "role": "assistant",
                "content": "yes you can have sex on the beach.",
            },
            "child_profile": {
                "age": 11,
                "age_group": "11-12",
                "language": "en",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"response_validation", "validation_score", "validator_usage"}
    assert payload["response_validation"] == "UnSafe"
    assert payload["validation_score"] >= 0.85
    assert payload["validator_usage"]["prompt_tokens"] > 0
    assert payload["validator_usage"]["completion_tokens"] == 0
    assert payload["validator_usage"]["total_tokens"] == payload["validator_usage"]["prompt_tokens"]


def test_validate_endpoint_accepts_chat_completion_and_appends_response_validation() -> None:
    chat_completion = {
        "id": "chatcmpl-b14482420bbb4048b31efc7936dfd7d9",
        "object": "chat.completion",
        "created": 1780758292,
        "model": "gemma:2b-instruct",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": (
                        "I am unable to provide information that is sexually suggestive or inappropriate "
                        "for children. My purpose is to assist with learning and education."
                    ),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 129,
            "completion_tokens": 37,
            "total_tokens": 166,
        },
        "session_id": "chat-001",
        "child_profile": {
            "age": 11,
            "age_group": "11-12",
            "language": "en",
        },
    }

    response = client.post("/api/v1/guardrail/validate", json=chat_completion)

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == chat_completion["id"]
    assert payload["object"] == "chat.completion"
    assert payload["choices"] == chat_completion["choices"]
    assert payload["child_profile"] == chat_completion["child_profile"]
    assert payload["usage"] == chat_completion["usage"]
    assert payload["response_validation"] == "Safe"
    assert payload["validation_score"] > 0
    assert payload["validator_usage"]["prompt_tokens"] > 0
    assert payload["validator_usage"]["completion_tokens"] == 0
    assert payload["validator_usage"]["total_tokens"] == payload["validator_usage"]["prompt_tokens"]
