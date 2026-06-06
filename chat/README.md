# Chat Service

Standalone chat service scaffold for PikuAI guardrails.

## Model Selection

Local development default:

- Backend: `ollama`
- Model: `gemma:2b-instruct`

Use this locally:

```bash
export CHAT_ENV=local
export CHAT_BACKEND=ollama
export OLLAMA_CHAT_MODEL=gemma:2b-instruct
```

Make sure the local Ollama model exists:

```bash
ollama list
```

Production option:

- `google/gemma-4-12B`
- License note: Google Gemma 4 licensing model, Apache 2.0

Use this for production:

```bash
export CHAT_ENV=production
export CHAT_BACKEND=transformers
export CHAT_MODEL_SLUG=google/gemma-4-12B
```

`google/gemma-4-12B` is blocked in local mode so it does not download accidentally during development.

Larger Gemma override:

```bash
export CHAT_BACKEND=transformers
export CHAT_MODEL_SLUG=google/gemma-2-9b-it
```

Another override:

```bash
export CHAT_BACKEND=transformers
export CHAT_MODEL_SLUG=microsoft/Phi-3.5-mini-instruct
```

## Run locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 4003 --reload
```

The chat model is lazy-loaded on the first `/api/v1/guardrail/chat` request. `/health` starts immediately and does not load model weights.

The chat service calls the validator after LLM generation. Configure validator URL if needed:

```bash
export CHAT_VALIDATOR_URL=http://localhost:4002/api/v1/guardrail/validate
```

## Endpoint

- `POST /api/v1/guardrail/chat`

Standard request shape:

```json
{
  "model": "gemma:2b-instruct",
  "messages": [
    {
      "role": "system",
      "content": "You are a child-safe helpful assistant. Be calm, concise, and age-appropriate."
    },
    {
      "role": "user",
      "content": "Why do people pray?"
    }
  ],
  "temperature": 0.2,
  "max_tokens": 128,
  "validate_response": true,
  "session_id": "chat-001",
  "child_profile": {
    "age": 10,
    "age_group": "9-10",
    "language": "en"
  }
}
```

Legacy compatibility is still supported for:

- `message`
- `recent_context`
- `system_prompt`

Response includes validator output:

```json
{
  "response_validation": "Safe",
  "validation_score": 0.92,
  "validator_usage": {
    "prompt_tokens": 9,
    "completion_tokens": 0,
    "total_tokens": 9
  }
}
```

`validate_response` defaults to `false`. When omitted or `false`, chat does not call the validator and these validator fields are `null`.

If the validator service is unavailable, chat fails closed with `response_validation: "UnSafe"` and includes `validator_error`.
