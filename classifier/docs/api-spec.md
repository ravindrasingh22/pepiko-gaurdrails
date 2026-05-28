# API Specification

## Purpose

This document defines the external API contract for `pikuai-gaurdrails` and separates:

- the recommended public integration contract
- the current internal/debug response shape

## Base URL

Examples assume:

```text
https://<your-host>/api/v1
```

## Public endpoint

- `POST /guardrails/run`

## Request

```json
{
  "child_profile": {
    "age": 8,
    "age_group": "7-8",
    "language": "en"
  },
  "session_id": "api-run-1",
  "recent_context": [],
  "message": "A classmate threatens to ruin my project if I tell a teacher."
}
```

## Recommended public response

The public response should expose only stable product-facing fields.

```json
{
  "request_id": "api-run-1",
  "question": "A classmate threatens to ruin my project if I tell a teacher.",
  "age_band": "7-8",
  "classification": {
    "g1": "GENERIC",
    "g2_primary": "BULLYING",
    "flags": [
      "has_bullying_involved",
      "has_coercive_control"
    ],
    "intent_families": [
      "forced_compliance",
      "threats_and_punishment"
    ],
    "g3": {
      "severity": "SV2",
      "modifiers": ["empathetic_tone"]
    },
    "g4": "TRANSFORM"
  },
  "decision": {
    "policy_bucket": "allowed",
    "response_mode": "safe_support",
    "allow_llm": true,
    "allow_rag": false,
    "risk_level": "medium",
    "parent_visible": false
  }
}
```

## Public response field notes

| Field | Type | Notes |
|---|---|---|
| `request_id` | string | Mirror of client session or generated request id |
| `question` | string | Canonical user message |
| `age_band` | string | Resolved age band used by policy |
| `classification.g1` | string | Broad content class |
| `classification.g2_primary` | string | Primary runtime `G2` |
| `classification.flags` | string[] | High-confidence auxiliary flags |
| `classification.intent_families` | string[] | High-confidence Block J families |
| `classification.g3` | object | Deterministic severity and modifiers |
| `classification.g4` | string | Deterministic action |
| `decision.policy_bucket` | string | Product-facing route bucket |
| `decision.response_mode` | string | How the assistant should respond |
| `decision.allow_llm` | boolean | Whether generation is allowed |
| `decision.allow_rag` | boolean | Whether retrieval is allowed |
| `decision.risk_level` | string | Runtime risk bucket |
| `decision.parent_visible` | boolean | Guardian visibility signal |

## Current classifier-facing debug shape

The internal/debug paths may expose more fields than the public API.

For `infer.py --mode slm` and `--mode slm_pure`, the current classifier-oriented shape is closer to:

```json
{
  "question": "A classmate threatens to ruin my project if I tell a teacher.",
  "user_input": "A classmate threatens to ruin my project if I tell a teacher.",
  "context": "",
  "language": "en",
  "backend": "slm",
  "core_model": "deberta",
  "trained": true,
  "threshold": 0.8,
  "g1": {
    "id": "GENERIC"
  },
  "g2": {
    "id": "BULLYING",
    "scores": {}
  },
  "flags": {},
  "intent_families": {
    "active": []
  },
  "intent_phrases": {
    "active": []
  }
}
```

Notes:

- `user_input` is an alias of `question`
- `g2_all` is no longer part of the active classifier response contract
- `intent_family` scores and `intent_phrase` scores are intentionally omitted from the current CLI output

## Public vs internal fields

### Safe to expose publicly

- `question`
- `age_band`
- primary `G1`
- primary `G2`
- selected high-confidence flags
- selected high-confidence `intent_families`
- deterministic `G3`
- deterministic `G4`
- high-level decision flags

### Do not expose publicly by default

- prompt text
- prompt templates
- stage traces
- full classifier metadata
- local paths
- dataset/model fingerprints
- full per-label score vectors unless explicitly needed for enterprise debugging

## Recommended mapping from internal runtime output

| Internal field | Public field |
|---|---|
| `question` | `question` |
| `age_band` | `age_band` |
| `g1` or `classifier.gates.G1` | `classification.g1` |
| `g2` or `classifier.gates.G2` | `classification.g2_primary` |
| `flags.active` or filtered runtime flags | `classification.flags` |
| `intent_families.active` | `classification.intent_families` |
| deterministic gate output `G3` | `classification.g3` |
| deterministic gate output `G4` | `classification.g4` |
| policy bucket | `decision.policy_bucket` |
| response mode | `decision.response_mode` |
| `allow_llm` | `decision.allow_llm` |
| `allow_rag` | `decision.allow_rag` |
| `risk_level` | `decision.risk_level` |
| `parent_visible` | `decision.parent_visible` |

## Error contract

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
