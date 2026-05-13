# API Specification

## Purpose

This document defines the external API contract for `pikuai-gaurdrails`.

It separates:

- the public integration contract that third-party developers should use
- the currently implemented internal/debug response shape

The goal is to preserve product IP by exposing only stable, necessary outputs to integrators and keeping prompt construction, model internals, stage traces, local file paths, and classifier diagnostics out of the public API.

## Base URL

Examples below assume:

```text
https://<your-host>/api/v1
```

## Authentication

Authentication is not yet defined in the current implementation.

Recommended production options:

- `Authorization: Bearer <api_key>`
- tenant-scoped API keys
- request-level rate limiting and audit logging

## Versioning

Current app version in code:

- service: `PikuAI Gaurdrails`
- app version: `0.1.0`

Recommended public API versioning:

- path versioning: `/api/v1/...`
- additive-only response changes within `v1`
- breaking changes only in `v2`

## Endpoint Index

### Public

- `POST /guardrails/run`

### Internal Test and Debug

- `POST /guardrails/test/classification`
- `POST /guardrails/test/llm-call`
- `POST /guardrails/test/validator`

These test endpoints are not recommended for third-party consumption.

## 1. Run Guardrails

### Endpoint

`POST /api/v1/guardrails/run`

### Description

Runs the full guardrail classification pipeline for a child question and returns the final decision package.

### Request Body

```json
{
  "child_profile": {
    "age": 8,
    "age_group": "7-8",
    "language": "en"
  },
  "session_id": "api-run-1",
  "recent_context": [],
  "message": "Explain how to fake an injury to waste time in a match?"
}
```

### Request Fields

| Field | Type | Required | Notes |
|---|---|---:|---|
| `child_profile.age` | integer | yes | Child age |
| `child_profile.age_group` | string | yes | Current runtime age band |
| `child_profile.language` | string | yes | Request language |
| `session_id` | string | yes | Client-provided conversation/session id |
| `recent_context` | string[] | no | Prior turns or contextual snippets |
| `message` | string | yes | Child message, max 2000 chars |

## Public Response Contract

### Why a reduced response is recommended

The current implementation returns many internal fields that should not be part of a third-party API:

- raw prompt text
- expanded prompt text
- prompt templates
- stage-by-stage traces
- classifier internals and full confidence vectors
- local filesystem paths
- model fingerprints and artifact locations
- implementation-specific policy notes and checklist internals

Those fields leak system design, policy logic, prompt engineering strategy, and infrastructure details.

### Recommended public response

Third-party developers should receive only the minimum stable contract needed to build product behavior.

```json
{
  "request_id": "api-run-1",
  "question": "Explain how to fake an injury to waste time in a match?",
  "age_band": "7-8",
  "topic": "PLAYGROUND_BULLYING",
  "classification": {
    "guidelines": ["GL-01", "GL-03", "GL-05", "GL-11"],
    "g1": "VIOLENCE",
    "g2_primary": "NEUTRAL_FACT",
    "g2_all": [
      "NEUTRAL_FACT",
      "PD",
      "DANGEROUS",
      "EMOTIONAL",
      "COERCIVE_CONTROL",
      "SELF_HARM"
    ],
    "g3": {
      "severity": "SV0",
      "modifiers": ["empathetic_tone"]
    },
    "g4": "BLOCK_ESCALATE"
  },
  "decision": {
    "policy_bucket": "soft_block",
    "response_mode": "safe_refusal",
    "allow_llm": false,
    "allow_rag": false,
    "risk_level": "low",
    "parent_visible": true
  },
  "explanations": {
    "g1": "Question involving violence, conflict, harm, extremism, or dangerous acts.",
    "g4": "Do not engage the content. Give a safe refusal and escalate toward trusted-adult support."
  },
  "status": {
    "safe_to_show": true
  }
}
```

### Public Response Field Notes

| Field | Type | Notes |
|---|---|---|
| `request_id` | string | Mirror of client session or generated request id |
| `question` | string | Canonical user message |
| `age_band` | string | Resolved age band used by policy |
| `topic` | string | Predicted topic label |
| `classification.guidelines` | string[] | Active guideline ids |
| `classification.g1` | string | Broad content nature |
| `classification.g2_primary` | string | Primary intent/risk label |
| `classification.g2_all` | string[] | Supporting multi-label G2 outputs |
| `classification.g3` | object | Severity and modifiers |
| `classification.g4` | string | Final policy action |
| `decision.policy_bucket` | string | Product-facing route bucket |
| `decision.response_mode` | string | How the assistant should respond |
| `decision.allow_llm` | boolean | Whether an answer-generation model may be called |
| `decision.allow_rag` | boolean | Whether retrieval is allowed |
| `decision.risk_level` | string | Low/medium/high runtime risk bucket |
| `decision.parent_visible` | boolean | Whether guardian visibility is indicated |
| `explanations.g1` | string | Safe business-facing explanation |
| `explanations.g4` | string | Safe product-facing action explanation |
| `status.safe_to_show` | boolean | Whether the response package is safe to surface |

## Current Implemented Response

The current implementation of `POST /guardrails/run` returns a much larger object, including:

- `raw_generated_prompt`
- `generated_prompt`
- `metadata`
- `classifier`
- `stage_outputs`

This shape is useful for internal debugging but should be considered internal.

### Current top-level fields

```json
{
  "topic": "PLAYGROUND_BULLYING",
  "question": "Explain how to fake an injury to waste time in a match?",
  "age_band": "7-8",
  "guidelines": ["GL-01", "GL-03", "GL-05", "GL-11"],
  "g1": "VIOLENCE",
  "g2": [
    "NEUTRAL_FACT",
    "PD",
    "DANGEROUS",
    "EMOTIONAL",
    "COERCIVE_CONTROL",
    "SELF_HARM"
  ],
  "g3": {
    "severity": "SV0",
    "modifiers": ["empathetic_tone"]
  },
  "g4": "BLOCK_ESCALATE",
  "raw_generated_prompt": "...",
  "generated_prompt": "...",
  "metadata": {},
  "classifier": {},
  "final_policy_bucket": "soft_block",
  "stage_outputs": {}
}
```

## Public vs Internal Fields

### Safe to expose publicly

- `topic`
- `question`
- `age_band`
- `guidelines`
- `g1`
- `g2` or split into `g2_primary` and `g2_all`
- `g3`
- `g4`
- `final_policy_bucket`
- high-level decision flags such as `allow_llm`, `risk_level`, `parent_visible`

### Do not expose publicly

- `raw_generated_prompt`
- `generated_prompt`
- `prompt_template`
- `template_id`
- `safety_envelope`
- `prompt_checklist`
- `stage_outputs`
- full `classifier_metadata`
- local paths such as `label_vocab_path`
- model and dataset fingerprints
- full per-label confidence vectors unless explicitly licensed for enterprise debugging

## Recommended Output Mapping From Current Implementation

Use this mapping when creating a public response adapter:

| Current field | Public field |
|---|---|
| `question` | `question` |
| `age_band` | `age_band` |
| `topic` | `topic` |
| `guidelines` | `classification.guidelines` |
| `g1` | `classification.g1` |
| `g2[0]` or `classifier.gates.G2` | `classification.g2_primary` |
| `g2` | `classification.g2_all` |
| `g3` | `classification.g3` |
| `g4` | `classification.g4` |
| `final_policy_bucket` | `decision.policy_bucket` |
| `classifier.decision.response_mode` | `decision.response_mode` |
| `classifier.decision.allow_llm` | `decision.allow_llm` |
| `classifier.decision.allow_rag` | `decision.allow_rag` |
| `classifier.decision.risk_level` | `decision.risk_level` |
| `classifier.decision.parent_visible` | `decision.parent_visible` |
| `metadata.g1_description` | `explanations.g1` |
| `metadata.g4_description` | `explanations.g4` |
| `stage_outputs.output_validator.safe_to_show` | `status.safe_to_show` |

## Recommended Error Contract

The current implementation relies on framework defaults.

Recommended public error shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "message must be a non-empty string",
    "details": {
      "field": "message"
    }
  }
}
```

Recommended codes:

- `VALIDATION_ERROR`
- `UNAUTHORIZED`
- `RATE_LIMITED`
- `INTERNAL_ERROR`
- `DEPENDENCY_FAILURE`

## Internal Debug Endpoints

### `POST /api/v1/guardrails/test/classification`

Returns classification-stage output and stage traces only. Internal use.

### `POST /api/v1/guardrails/test/llm-call`

Returns prompt, model route, and raw answer. Internal use.

### `POST /api/v1/guardrails/test/validator`

Validates a provided or generated answer and may include a repaired answer. Internal use.

## Implementation Notes

The current code path for the public route is:

- route: [chat_routes.py](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/app/api/chat_routes.py:17)
- app mount: [main.py](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/app/main.py:6)
- response assembly: [pipeline.py](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/app/guardrails/pipeline.py:167)
- response schema: [schemas.py](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/app/models/schemas.py:17)

## Recommended Next Step

Add a dedicated public response model, for example:

- `GuardrailRunPublicResponse`

Then either:

- change `POST /guardrails/run` to return only the public contract
- or add a second endpoint such as `POST /guardrails/run/internal` for the current verbose response

The safer default is:

- public route returns the reduced contract
- internal route requires privileged access and returns full traces
