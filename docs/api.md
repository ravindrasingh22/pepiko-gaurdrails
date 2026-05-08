# API Job

This service owns one orchestration entrypoint:

- `POST /api/v1/guardrails/run`

For testing and debugging, the scaffold also exposes stage-specific endpoints:

- `POST /api/v1/guardrails/test/classification`
- `POST /api/v1/guardrails/test/llm-call`
- `POST /api/v1/guardrails/test/validator`

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

- final policy decision
- final answer
- stage outputs
- audit log entries for every stage

The app-facing integration should use only `POST /api/v1/guardrails/run`.
That endpoint executes the full sequence internally and returns the complete stage trace in one response.

The test endpoints are for backend verification only:

- `classification`: returns guideline tags, signals, and `G1/G2/G3/G4` without calling the LLM.
- `llm-call`: runs classification, routing, RAG, prompt build, and the LLM stage, then returns the generated prompt and raw answer.
- `validator`: runs the same upstream sequence and validates either a provided `answer` or the scaffold-generated answer.
