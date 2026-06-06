# Chat Service

Standalone chat service scaffold for PikuAI guardrails.

## Default model

The default HF chat model is:

- `Qwen/Qwen2.5-0.5B-Instruct`

Override with:

```bash
export CHAT_MODEL_SLUG=Qwen/Qwen2.5-0.5B-Instruct
```

Example override for a larger model:

```bash
export CHAT_MODEL_SLUG=microsoft/Phi-3.5-mini-instruct
```

Another larger override:

```bash
export CHAT_MODEL_SLUG=Qwen/Qwen2.5-7B-Instruct
```

## Run locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 4003 --reload
```

## Endpoint

- `POST /api/v1/guardrail/chat`

Standard request shape:

```json
{
  "model": "Qwen/Qwen2.5-0.5B-Instruct",
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

The current implementation is direct HF chat generation. It is not yet integrated with classifier policy contracts or validator enforcement.
