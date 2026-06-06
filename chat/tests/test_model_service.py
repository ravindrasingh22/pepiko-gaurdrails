from app.model_service import _chat_backend, _messages_for_chat_template, _resolve_ollama_model_name, warm_chat_model


def test_local_default_backend_is_ollama(monkeypatch) -> None:
    monkeypatch.delenv("CHAT_BACKEND", raising=False)
    monkeypatch.delenv("CHAT_MODEL_SLUG", raising=False)
    monkeypatch.delenv("OLLAMA_CHAT_MODEL", raising=False)

    assert _chat_backend() == "ollama"
    assert _resolve_ollama_model_name() == "gemma:2b-instruct"
    assert warm_chat_model() == {"backend": "ollama", "model_name": "gemma:2b-instruct", "status": "lazy"}


def test_hf_slug_selects_transformers_backend_when_backend_unset(monkeypatch) -> None:
    monkeypatch.delenv("CHAT_BACKEND", raising=False)

    assert _chat_backend("google/gemma-2-2b-it") == "transformers"


def test_gemma_merges_system_message_into_first_user_message() -> None:
    messages = [
        {"role": "system", "content": "Follow child-safe rules."},
        {"role": "user", "content": "Why is the sky blue?"},
    ]

    adapted = _messages_for_chat_template(messages, "google/gemma-2-2b-it")

    assert adapted == [
        {
            "role": "user",
            "content": "Follow child-safe rules.\n\nUser request:\nWhy is the sky blue?",
        }
    ]


def test_gemma_preserves_non_system_turns_after_first_user() -> None:
    messages = [
        {"role": "system", "content": "Follow child-safe rules."},
        {"role": "user", "content": "First question"},
        {"role": "assistant", "content": "First answer"},
        {"role": "user", "content": "Second question"},
    ]

    adapted = _messages_for_chat_template(messages, "google/gemma-4-12B")

    assert [item["role"] for item in adapted] == ["user", "assistant", "user"]
    assert adapted[0]["content"].startswith("Follow child-safe rules.")
    assert adapted[1]["content"] == "First answer"
    assert adapted[2]["content"] == "Second question"


def test_non_gemma_keeps_system_message() -> None:
    messages = [
        {"role": "system", "content": "Follow child-safe rules."},
        {"role": "user", "content": "Why is the sky blue?"},
    ]

    adapted = _messages_for_chat_template(messages, "microsoft/Phi-3.5-mini-instruct")

    assert adapted == messages
