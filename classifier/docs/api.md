# API Job

This service owns one classifier entrypoint:

- `POST /api/v1/guardrail/classify`

Detailed API specification:

- [api-spec.md](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/api-spec.md)

Related scaffold services exist separately:

- `validator` -> `POST /api/v1/guardrail/validate`
- `chat` -> `POST /api/v1/guardrail/chat`

Request body:

```json
{
  "child_profile": {
    "age": 8,
    "age_group": "8-10",
    "language": "hinglish"
  },
  "session_id": "session-123",
  "recent_context": ["Child: I got bad marks."],
  "message": "mummy se kaise chupaun?"
}
```

Response shape includes:

- classification decision
- stage outputs

The app-facing integration for this service should use only `POST /api/v1/guardrail/classify`.
