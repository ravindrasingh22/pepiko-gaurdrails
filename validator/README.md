# PikuAI Validator Service

The validator is a post-generation safety service. It receives the child age group and generated response text, then returns a strict `safe` / `unsafe` classification with a confidence score.

Endpoint:

```bash
POST /api/v1/guardrail/validate
```

Recommended lightweight request:

```json
{
  "message": {
    "role": "assistant",
    "content": "yes you can have sex on the beach."
  },
  "child_profile": {
    "age": 11,
    "age_group": "11-12",
    "language": "en"
  }
}
```

Lightweight response:

```json
{
  "response_validation": "UnSafe",
  "validation_score": 0.91,
  "validator_usage": {
    "prompt_tokens": 11,
    "completion_tokens": 0,
    "total_tokens": 11
  }
}
```

Chat-completion passthrough request:

```json
{
  "id": "chatcmpl-b14482420bbb4048b31efc7936dfd7d9",
  "object": "chat.completion",
  "created": 1780758292,
  "model": "gemma:2b-instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "I am unable to provide information that is sexually suggestive or inappropriate for children."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 129,
    "completion_tokens": 37,
    "total_tokens": 166
  },
  "session_id": "chat-001",
  "child_profile": {
    "age": 11,
    "age_group": "11-12",
    "language": "en"
  }
}
```

For chat-completion input, the validator extracts `choices[0].message.content` as `response_text`, extracts `child_profile.age_group`, validates the assistant message, and returns the original chat object plus:

```json
{
  "response_validation": "Safe",
  "validation_score": 0.92,
  "validator_usage": {
    "prompt_tokens": 31,
    "completion_tokens": 0,
    "total_tokens": 31
  }
}
```

The original chat `usage` object is preserved. Validator token counts are reported separately under `validator_usage`.

Compatibility request:

```json
{
  "session_id": "validate-001",
  "age_group": "5-7",
  "response_text": "The little yellow duck swam across the blue pond."
}
```

Legacy compatibility request:

```json
{
  "session_id": "validate-001",
  "child_profile": {"age_group": "5-7", "language": "en"},
  "answer": "The little yellow duck swam across the blue pond."
}
```

Detailed compatibility response shape:

```json
{
  "status": "safe",
  "score": 0.92,
  "label": 0,
  "scores": {"safe": 0.92, "unsafe": 0.08},
  "model": {
    "backend": "lexicon_fallback",
    "model_path": "validator/models/piku-validator-deberta-v3-small",
    "trained": false,
    "threshold": 0.85
  },
  "usage": {
    "prompt_tokens": 14,
    "completion_tokens": 0,
    "total_tokens": 14
  },
  "route": {
    "action": "allow",
    "delivered_text": "The little yellow duck swam across the blue pond.",
    "fallback_text": null
  }
}
```

## Dataset Schema

Training data is a JSON list:

```json
[
  {
    "text": "Age Group: 5-7 | Content: The friendly puppy chased the colorful ball across the sunny grass field.",
    "label": 0
  },
  {
    "text": "Age Group: 5-7 | Content: The dark ghost jumped out with a sharp knife and cut the lights.",
    "label": 1
  }
]
```

Labels:

- `0`: safe
- `1`: unsafe

## Prepare Dataset

```bash
python -m validator.training.prepare_dataset \
  --source validator/data/raw/validator_rows.csv \
  --output validator/data/processed/dataset.json \
  --age-group-column age_group \
  --response-text-column response_text \
  --label-column label
```

## Train

```bash
python -m validator.training.train_deberta_validator \
  --dataset validator/data/processed/dataset.json \
  --output-dir validator/models/piku-validator-deberta-v3-small \
  --model-name microsoft/deberta-v3-small \
  --epochs 3 \
  --batch-size 16 \
  --learning-rate 2e-5
```

## Runtime

The endpoint lazily loads the model only when `validator/models/piku-validator-deberta-v3-small` exists.

Optional environment:

```bash
export VALIDATOR_MODEL_PATH=validator/models/piku-validator-deberta-v3-small
export VALIDATOR_SAFETY_THRESHOLD=0.85
```

Run locally:

```bash
cd validator
uvicorn app.main:app --host 0.0.0.0 --port 4002 --reload
```
