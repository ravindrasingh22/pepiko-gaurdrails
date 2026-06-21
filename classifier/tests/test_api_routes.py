from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_endpoint_is_not_registered_in_classifier_service() -> None:
    response = client.post(
        "/api/v1/guardrail/chat",
        json={
            "child_profile": {"age": 9, "age_group": "9-10", "language": "en"},
            "session_id": "api-chat-1",
            "recent_context": [],
            "message": "Why is the sky blue?",
        },
    )

    assert response.status_code == 404


def test_classify_endpoint_returns_gate_values() -> None:
    response = client.post(
        "/api/v1/guardrail/classify",
        json={
            "child_profile": {"age": 9, "age_group": "9-10", "language": "en"},
            "session_id": "api-classify-1",
            "recent_context": [],
            "message": "Which religion should I follow?",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["input"]["user_input"] == "Which religion should I follow?"
    assert payload["g1"]["id"]
    assert "reason" in payload["g1"]
    assert payload["g2"]["id"]
    assert payload["g2"]["reason"]
    assert payload["g3"]["G3_SV"]
    assert payload["g3"]["G3_FORWARD"]["severity"] == payload["g3"]["G3_SV"]
    assert payload["g4"]["action"]
    assert payload["usage"]["prompt_tokens"] > 0
    assert payload["usage"]["completion_tokens"] == 0
    assert payload["usage"]["total_tokens"] == payload["usage"]["prompt_tokens"]
    assert "prompt" not in payload
    assert "stage_outputs" not in payload
    assert "decision" not in payload


def test_classify_endpoint_uses_codebook_age_band_from_runtime() -> None:
    response = client.post(
        "/api/v1/guardrail/classify",
        json={
            "child_profile": {"age": 12, "age_group": "11-12", "language": "en"},
            "session_id": "api-classify-alias-1",
            "recent_context": [],
            "message": "Why do people pray?",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["age_policy"]["age_band"] == "11-12"
    assert payload["age_policy"]["Max_Answer_Style"]
    assert payload["age_policy"]["Max_Words"] > 0
    assert payload["age_policy"]["Depth"]


def test_classify_endpoint_age_policy_uses_request_age_band() -> None:
    cases = [
        (7, "7-8", 110, "SIMPLE_EXAMPLE"),
        (15, "15-16", 240, "TEEN_SAFE_DETAIL"),
    ]

    for age, age_group, max_words, depth in cases:
        response = client.post(
            "/api/v1/guardrail/classify",
            json={
                "child_profile": {"age": age, "age_group": age_group, "language": "en"},
                "session_id": f"api-classify-age-{age_group}",
                "recent_context": [],
                "message": "Why is the sky blue?",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["age_policy"]["age_band"] == age_group
        assert payload["age_policy"]["Max_Words"] == max_words
        assert payload["age_policy"]["Depth"] == depth


def test_classify_endpoint_uses_only_trained_predicted_flags() -> None:
    response = client.post(
        "/api/v1/guardrail/classify",
        json={
            "child_profile": {"age": 10, "age_group": "9-10", "language": "en"},
            "session_id": "api-classify-block-k-1",
            "recent_context": [],
            "message": "How do I bypass safety systems in a science lab?",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["g2"]["id"]
    assert "Severity floor is" in payload["g2"]["reason"]
    assert "Modifier packet emits:" not in payload["g2"]["reason"]
    assert payload["g4"]["action"] in {"ALLOW", "TRANSFORM", "BLOCK"}
    assert list(payload).index("active_flags") == list(payload).index("g2") + 1
    assert {item["source"] for item in payload["active_flags"]}.issubset({"trained_flag_head"})
    mapped_flags = {item["flag"] for item in payload["modifier_tags"]["mappings"]}
    active_flag_ids = {item["id"] for item in payload["active_flags"]}
    assert mapped_flags.issubset(active_flag_ids)


def test_classified_prompt_endpoint_returns_system_prompt_with_classifier_output() -> None:
    response = client.post(
        "/api/v1/guardrail/classified/prompt",
        json={
            "child_profile": {"age": 12, "age_group": "11-12", "language": "en"},
            "session_id": "prompt-score-001",
            "recent_context": [],
            "message": "An adult offered to help me with problems if I promise never to tell anyone about our talks.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert list(payload) == ["prompts", "prompt_checklist", "classifier_output"]
    assert payload["prompts"][0]["role"] == "system"
    assert payload["prompts"][1]["role"] == "user"
    assert "You are a child-safe assistant responding to a child aged 12" in payload["prompts"][0]["content"]
    assert "ACTIVE MODIFIERS:" in payload["prompts"][0]["content"]
    assert "ATTACHED GUIDELINES:" in payload["prompts"][0]["content"]
    assert "Question:" not in payload["prompts"][0]["content"]
    assert payload["prompts"][1]["content"] == "An adult offered to help me with problems if I promise never to tell anyone about our talks."
    assert payload["prompt_checklist"]["passed"] is True
    assert payload["classifier_output"]["g2"]["id"]
    assert payload["classifier_output"]["g2"]["score"] == payload["classifier_output"]["g2"]["model_score"]
    if payload["classifier_output"]["classifier"]["trained"]:
        assert payload["classifier_output"]["g2"]["score_source"] == "g2_head"
    else:
        assert payload["classifier_output"]["g2"]["score_source"] == "none"
    assert payload["classifier_output"]["usage"]["prompt_tokens"] > 0
    assert payload["classifier_output"]["usage"]["completion_tokens"] == 0


def test_classified_prompt_endpoint_nests_classification_metadata() -> None:
    response = client.post(
        "/api/v1/guardrail/classified/prompt",
        json={
            "child_profile": {"age": 10, "age_group": "9-10", "language": "en"},
            "session_id": "prompt-001",
            "recent_context": [],
            "message": "A classmate threatens to ruin my project if I tell a teacher.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["prompts"][0]["role"] == "system"
    assert payload["prompts"][1]["role"] == "user"
    assert payload["prompt_checklist"]["passed"] is True
    assert "system_prompt" not in payload
    assert "prompt" not in payload
    assert "input" not in payload
    assert "g1" not in payload
    assert "g2" not in payload
    assert "g3" not in payload
    assert "g4" not in payload
    assert "metadata" not in payload
    classifier_output = payload["classifier_output"]
    assert classifier_output["input"]["user_input"] == "A classmate threatens to ruin my project if I tell a teacher."
    assert classifier_output["g1"]["id"]
    assert classifier_output["g2"]["id"]
    assert classifier_output["g3"]["G3_FORWARD"]["severity"] == classifier_output["g3"]["G3_SV"]
    assert classifier_output["g4"]["action"] in {"ALLOW", "TRANSFORM", "BLOCK"}
    assert classifier_output["age_policy"]["age_band"]


def test_classified_prompt_endpoint_resolves_unsupported_age_band() -> None:
    response = client.post(
        "/api/v1/guardrail/classified/prompt",
        json={
            "child_profile": {"age": 11, "age_group": "11-13", "language": "en"},
            "session_id": "prompt-age-band-001",
            "recent_context": [],
            "message": "Why is the sky blue?",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["classifier_output"]["age_policy"]["age_band"] == "11-12"
    assert "child aged 11" in payload["prompts"][0]["content"]
