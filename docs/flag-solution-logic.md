# Flag Solution Logic

This document defines a full flag-based solution for the SLM classifier pipeline.

The goal is to improve runtime quality for:

- `G1` classification
- primary `G2` classification
- calculated `G2_all`
- safety-sensitive promotion of high-risk classes
- better separation of close labels such as:
  - `SELF_HARM` vs `EMOTIONAL` vs `AMBIGUOUS_RISK`
  - `GROOMING` vs `VULN_EXPLOIT` vs `COERCIVE_CONTROL`
  - `DANGEROUS` vs `VIOLENCE` vs `SAFETY_HAZARD`
  - `BULLYING` vs `HATE_GROUP`
  - `PERSONAL_DIRECTION` vs `GENERIC_INTENT`

This design assumes:

- `G1` remains a single-label classifier output
- primary `G2` remains a single-label classifier output
- `G2_all` is calculated at inference
- flags are trained and used as supporting evidence
- `G3` and `G4` remain deterministic runtime outputs

## Problem

The current classifier can suffer from:

- heavy `G1=GENERIC` bias
- risky content collapsing into broad classes like `EMOTIONAL` or `AMBIGUOUS_RISK`
- weak recall for high-risk classes unless phrasing is very explicit
- poor separation among nearby categories
- calculated `G2_all` that lacks direct evidence beyond label scores and heuristics

Flags address this by introducing structured evidence signals that can be:

- normalized from raw authoring sheets
- trained as auxiliary targets
- reused directly at runtime
- used to promote or suppress labels

## Flag Principles

Flags must follow these rules:

1. Flags are evidence, not policy.
2. Flags do not replace `G1` or `G2`.
3. Flags should be local and interpretable.
4. Flags should be usable both in training and runtime.
5. Flags should improve recall for safety-critical cases without exploding false positives.

Good flags answer narrow questions such as:

- does this text contain direct self-harm intent?
- does this text contain secrecy pressure?
- does this text contain blackmail?
- is this safe factual explanation rather than a harmful request?
- does this text ask the assistant to choose for the child?

Bad flags are:

- too broad
- redundant with `G2`
- impossible to validate from text
- too policy-heavy

## Flag Categories

Recommended flags are grouped into four groups.

### 1. Harm intent flags

- `has_self_harm_signal`
- `has_direct_intent`
- `has_indirect_ideation`
- `has_harm_to_others`
- `has_instructional_request`
- `has_illicit_instruction_request`
- `has_violence_signal`

### 2. Manipulation and exploitation flags

- `has_secrecy_pattern`
- `has_blackmail_pattern`
- `has_dependency_pattern`
- `has_adult_child_dynamic`
- `has_vulnerability_targeting`
- `has_control_pattern`
- `has_fear_based_authority`

### 3. Disambiguation and safe-negative flags

- `is_safe_factual`
- `is_prevention_or_help_seeking`
- `is_historical_or_explanatory`
- `is_hypothetical_not_instructional`
- `is_emotional_without_self_harm`
- `is_peer_conflict`
- `is_protected_group_target`
- `is_school_rule_or_law_context`

### 4. Prompt-shaping and ambiguity flags

- `has_personal_direction`
- `has_loaded_premise`
- `has_negative_language`
- `includes_slurs`
- `needs_clarification`
- `has_harmful_comparison`

## Mapping Flags to G2

Flags should support `G2`, not duplicate it exactly.

Recommended support map:

| Flag | Strongly Supports |
|---|---|
| `has_self_harm_signal` | `SELF_HARM` |
| `has_direct_intent` | `SELF_HARM`, `DANGEROUS`, `VIOLENCE` |
| `has_indirect_ideation` | `SELF_HARM`, `AMBIGUOUS_RISK` |
| `has_harm_to_others` | `VIOLENCE`, `DANGEROUS` |
| `has_illicit_instruction_request` | `DANGEROUS` |
| `has_secrecy_pattern` | `GROOMING`, `VULN_EXPLOIT` |
| `has_blackmail_pattern` | `VULN_EXPLOIT` |
| `has_dependency_pattern` | `VULN_EXPLOIT`, `GROOMING` |
| `has_adult_child_dynamic` | `GROOMING` |
| `has_control_pattern` | `COERCIVE_CONTROL` |
| `has_fear_based_authority` | `COERCIVE_CONTROL` |
| `is_safe_factual` | `NEUTRAL_FACT` |
| `is_prevention_or_help_seeking` | `NEUTRAL_FACT`, sometimes `EMOTIONAL` |
| `is_emotional_without_self_harm` | `EMOTIONAL` |
| `is_peer_conflict` | `BULLYING` |
| `is_protected_group_target` | `HATE_GROUP` |
| `has_personal_direction` | `PERSONAL_DIRECTION` |
| `needs_clarification` | `AMBIGUOUS_RISK` |

## Raw Training Sheet Design

The raw CSV authoring format can include wide columns. That is fine.

Recommended columns:

```text
TOPIC
QUESTION
CONTEXT
G1
G2
G2_all
flags
intent_families
intent_phrases
review_status
objective
source_notes
```

The `flags` column should be JSON.

Example raw row:

```csv
TOPIC,QUESTION,CONTEXT,G1,G2,G2_all,flags,intent_families,intent_phrases,review_status
Self-harm direct intent,"I want to die tonight.","none",DEATH_GRIEF,SELF_HARM,"[""SELF_HARM"",""EMOTIONAL""]","{""has_self_harm_signal"":true,""has_direct_intent"":true,""has_indirect_ideation"":false,""is_emotional_without_self_harm"":false,""is_safe_factual"":false}","[""suicidal_ideation""]","[""I want to die""]",approved
```

## Normalized Training Structure

During normalization, flags should be parsed into a stable machine-readable object.

Recommended normalized row:

```json
{
  "sample_id": "self_harm_001",
  "question": "I want to die tonight.",
  "context": "none",
  "topic": "Self-harm direct intent",
  "g1": "DEATH_GRIEF",
  "g2": ["SELF_HARM"],
  "g2_all": ["SELF_HARM", "EMOTIONAL"],
  "intent_families": ["suicidal_ideation"],
  "intent_phrases": ["I want to die"],
  "review_status": "approved",
  "flags": {
    "has_self_harm_signal": true,
    "has_direct_intent": true,
    "has_indirect_ideation": false,
    "has_instructional_request": false,
    "has_illicit_instruction_request": false,
    "has_secrecy_pattern": false,
    "has_blackmail_pattern": false,
    "has_dependency_pattern": false,
    "has_adult_child_dynamic": false,
    "has_control_pattern": false,
    "has_fear_based_authority": false,
    "is_safe_factual": false,
    "is_prevention_or_help_seeking": false,
    "is_historical_or_explanatory": false,
    "is_hypothetical_not_instructional": false,
    "is_emotional_without_self_harm": false,
    "is_peer_conflict": false,
    "is_protected_group_target": false,
    "has_personal_direction": false,
    "has_loaded_premise": false,
    "has_negative_language": false,
    "includes_slurs": false,
    "needs_clarification": false,
    "has_harmful_comparison": false
  }
}
```

## Normalization Rules

Normalization must do the following:

1. Parse `flags` from JSON if provided.
2. Fill missing flags with `false`.
3. Validate flag keys against a known schema.
4. Optionally infer a small set of obvious flags from text if absent.
5. Keep author-provided flags as source-of-truth unless they are invalid.

Recommended flag schema:

```json
{
  "has_self_harm_signal": "bool",
  "has_direct_intent": "bool",
  "has_indirect_ideation": "bool",
  "has_harm_to_others": "bool",
  "has_instructional_request": "bool",
  "has_illicit_instruction_request": "bool",
  "has_violence_signal": "bool",
  "has_secrecy_pattern": "bool",
  "has_blackmail_pattern": "bool",
  "has_dependency_pattern": "bool",
  "has_adult_child_dynamic": "bool",
  "has_vulnerability_targeting": "bool",
  "has_control_pattern": "bool",
  "has_fear_based_authority": "bool",
  "is_safe_factual": "bool",
  "is_prevention_or_help_seeking": "bool",
  "is_historical_or_explanatory": "bool",
  "is_hypothetical_not_instructional": "bool",
  "is_emotional_without_self_harm": "bool",
  "is_peer_conflict": "bool",
  "is_protected_group_target": "bool",
  "is_school_rule_or_law_context": "bool",
  "has_personal_direction": "bool",
  "has_loaded_premise": "bool",
  "has_negative_language": "bool",
  "includes_slurs": "bool",
  "needs_clarification": "bool",
  "has_harmful_comparison": "bool"
}
```

## Training Targets

Recommended training outputs:

1. `topic` head
2. `g1` head
3. primary `g2` head
4. intent-family head
5. intent-phrase head
6. flag head

The flag head should be a multi-label sigmoid output.

Example:

```json
{
  "topic_logits": "...",
  "g1_logits": "...",
  "g2_logits": "...",
  "intent_family_logits": "...",
  "intent_phrase_logits": "...",
  "flag_logits": {
    "has_self_harm_signal": 0.97,
    "has_direct_intent": 0.91,
    "is_safe_factual": 0.02
  }
}
```

Recommended loss weighting:

- `topic`: medium
- `g1`: medium
- primary `g2`: high
- intent heads: medium-low
- flag head: high for safety-critical flags

Flags that should receive extra loss weight:

- `has_self_harm_signal`
- `has_direct_intent`
- `has_harm_to_others`
- `has_illicit_instruction_request`
- `has_secrecy_pattern`
- `has_blackmail_pattern`
- `has_adult_child_dynamic`
- `has_control_pattern`

## Runtime Inference Structure

At inference, use:

- `question`
- `recent_context`
- normalized text
- classifier outputs
- predicted flags
- lexicon matches
- heuristic evidence

Recommended runtime classifier output:

```json
{
  "question": "Someone online says our friendship should stay secret from my parents.",
  "language": "en",
  "age_band": "9-10",
  "topic": "Online secrecy concern",
  "g1": {
    "id": "GENERIC",
    "reason": "The question is about a relationship and safety situation, not a factual domain like science or belief."
  },
  "g2_primary": {
    "id": "GROOMING",
    "score": 0.74
  },
  "g2_head_scores": {
    "GROOMING": 0.74,
    "VULN_EXPLOIT": 0.62,
    "COERCIVE_CONTROL": 0.14,
    "EMOTIONAL": 0.10
  },
  "flags": {
    "has_secrecy_pattern": {
      "score": 0.95,
      "triggered": true
    },
    "has_adult_child_dynamic": {
      "score": 0.81,
      "triggered": true
    },
    "has_blackmail_pattern": {
      "score": 0.09,
      "triggered": false
    }
  },
  "intent_lexicon": {
    "matched_lovs": ["GROOMING"],
    "evidence": [
      {
        "g2_id": "GROOMING",
        "matched_phrases": ["secret from my parents"]
      }
    ]
  }
}
```

## Runtime Fusion Logic

Inference should be a fusion pipeline, not a single raw argmax.

Recommended order:

1. Predict `topic`
2. Predict `G1`
3. Predict primary `G2`
4. Predict flags
5. Predict intent families and phrases
6. Collect heuristic and lexicon evidence
7. Build calculated `G2_all`
8. Promote or suppress high-risk labels based on flags
9. Resolve primary `G2` from fused set using priority rules
10. Derive `G3` and `G4`

## Calculating G2_all

`G2_all` should be calculated from:

1. per-label probabilities from the primary `G2` head
2. predicted flag evidence
3. lexicon evidence
4. heuristics

Recommended rule:

```text
G2_all =
  classifier-head labels above threshold
  UNION flag-supported labels
  UNION lexicon-supported labels
  UNION heuristic-supported labels
```

Recommended thresholds:

- default `G2` secondary threshold: `0.80`
- high-risk override threshold: `0.45` to `0.60`
- safe factual threshold: stricter when any high-risk evidence exists

Example:

```json
{
  "g2_head_scores": {
    "SELF_HARM": 0.43,
    "EMOTIONAL": 0.51,
    "AMBIGUOUS_RISK": 0.34
  },
  "flags": {
    "has_self_harm_signal": {
      "score": 0.94,
      "triggered": true
    },
    "has_direct_intent": {
      "score": 0.88,
      "triggered": true
    }
  }
}
```

Even though `SELF_HARM` is below the default secondary threshold, the flags justify adding or promoting it.

## Promotion and Suppression Rules

### Self-harm promotion

If:

- `has_self_harm_signal=true`
- and one of:
  - `has_direct_intent=true`
  - `has_indirect_ideation=true`
  - intent-family match is self-harm related

Then:

- add `SELF_HARM` to `G2_all`
- promote primary `G2` to `SELF_HARM` unless a higher-priority blocked class applies

### Grooming promotion

If:

- `has_secrecy_pattern=true`
- and `has_adult_child_dynamic=true`

Then:

- add `GROOMING`
- if `GROOMING` score is moderately close to top label, promote it above lower-risk classes

### Vulnerability exploitation promotion

If:

- `has_blackmail_pattern=true`
or
- `has_dependency_pattern=true`
or
- `has_vulnerability_targeting=true`

Then:

- add `VULN_EXPLOIT`

### Coercive control promotion

If:

- `has_control_pattern=true`
or
- `has_fear_based_authority=true`

Then:

- add `COERCIVE_CONTROL`

### Dangerous promotion

If:

- `has_instructional_request=true`
- and `has_harm_to_others=true`
or
- `has_illicit_instruction_request=true`

Then:

- add `DANGEROUS`
- suppress `NEUTRAL_FACT`

### Safe factual suppression guard

If:

- `is_safe_factual=true`
- and no critical harm flags are active

Then:

- allow `NEUTRAL_FACT`

If any strong high-risk flags are active:

- do not allow `NEUTRAL_FACT` to dominate

## Primary G2 Resolution

After `G2_all` is built, choose primary `G2` using a priority order.

Recommended order:

1. `UNSAFE_SEXUAL_CONTENT`
2. `GROOMING`
3. `COERCIVE_CONTROL`
4. `VULN_EXPLOIT`
5. `SELF_HARM`
6. `DANGEROUS`
7. `HATE_GROUP`
8. `VIOLENCE`
9. `PERSONAL_DIRECTION`
10. `SAFETY_HAZARD`
11. `AMBIGUOUS_RISK`
12. `EMOTIONAL`
13. `BULLYING`
14. `NEUTRAL_FACT`
15. `GENERIC_INTENT`

This priority should apply only after fusion, not before.

## End-to-End Example 1: Self-harm

Question:

```text
I keep thinking about disappearing forever and I don't know what to do.
```

Context:

```text
none
```

Normalized flags for training:

```json
{
  "has_self_harm_signal": true,
  "has_direct_intent": false,
  "has_indirect_ideation": true,
  "has_personal_direction": true,
  "is_emotional_without_self_harm": false,
  "is_safe_factual": false
}
```

Runtime prediction:

```json
{
  "g2_head_scores": {
    "EMOTIONAL": 0.52,
    "SELF_HARM": 0.47,
    "PERSONAL_DIRECTION": 0.26,
    "AMBIGUOUS_RISK": 0.18
  },
  "flags": {
    "has_self_harm_signal": {"score": 0.96, "triggered": true},
    "has_indirect_ideation": {"score": 0.91, "triggered": true},
    "has_personal_direction": {"score": 0.72, "triggered": true}
  },
  "intent_lexicon": {
    "matched_lovs": ["SELF_HARM"]
  }
}
```

Fused output:

```json
{
  "g2_primary": "SELF_HARM",
  "g2_all": ["SELF_HARM", "EMOTIONAL", "PERSONAL_DIRECTION"]
}
```

Reason:

- raw `EMOTIONAL` score is slightly higher
- flags and intent evidence strongly support `SELF_HARM`
- safety promotion raises `SELF_HARM` to primary

## End-to-End Example 2: Grooming

Question:

```text
An older person online told me not to tell my parents about our chats.
```

Context:

```text
They say I am special and only they understand me.
```

Normalized flags:

```json
{
  "has_secrecy_pattern": true,
  "has_adult_child_dynamic": true,
  "has_dependency_pattern": true,
  "has_blackmail_pattern": false,
  "is_safe_factual": false
}
```

Runtime output:

```json
{
  "g2_head_scores": {
    "EMOTIONAL": 0.31,
    "GROOMING": 0.29,
    "VULN_EXPLOIT": 0.24
  },
  "flags": {
    "has_secrecy_pattern": {"score": 0.97, "triggered": true},
    "has_adult_child_dynamic": {"score": 0.84, "triggered": true},
    "has_dependency_pattern": {"score": 0.79, "triggered": true}
  },
  "intent_lexicon": {
    "matched_lovs": ["GROOMING", "VULN_EXPLOIT"]
  }
}
```

Fused output:

```json
{
  "g2_primary": "GROOMING",
  "g2_all": ["GROOMING", "VULN_EXPLOIT", "EMOTIONAL"]
}
```

Reason:

- secrecy + adult-child dynamic is more specific than general emotional distress
- `VULN_EXPLOIT` is retained as secondary support

## End-to-End Example 3: Dangerous vs Safe Factual

Question:

```text
How can I poison someone using things from around the house?
```

Context:

```text
none
```

Normalized flags:

```json
{
  "has_harm_to_others": true,
  "has_instructional_request": true,
  "has_illicit_instruction_request": true,
  "is_safe_factual": false,
  "is_historical_or_explanatory": false
}
```

Runtime output:

```json
{
  "g2_head_scores": {
    "DANGEROUS": 0.58,
    "VIOLENCE": 0.34,
    "NEUTRAL_FACT": 0.12
  },
  "flags": {
    "has_harm_to_others": {"score": 0.95, "triggered": true},
    "has_instructional_request": {"score": 0.92, "triggered": true},
    "has_illicit_instruction_request": {"score": 0.94, "triggered": true},
    "is_safe_factual": {"score": 0.03, "triggered": false}
  }
}
```

Fused output:

```json
{
  "g2_primary": "DANGEROUS",
  "g2_all": ["DANGEROUS", "VIOLENCE"]
}
```

Reason:

- intent is instructional and harmful
- `NEUTRAL_FACT` is suppressed

## End-to-End Example 4: Emotional but not Self-harm

Question:

```text
I feel sad because my best friend moved away.
```

Context:

```text
none
```

Normalized flags:

```json
{
  "has_self_harm_signal": false,
  "has_direct_intent": false,
  "has_indirect_ideation": false,
  "is_emotional_without_self_harm": true,
  "is_safe_factual": false
}
```

Runtime output:

```json
{
  "g2_head_scores": {
    "EMOTIONAL": 0.76,
    "SELF_HARM": 0.08,
    "AMBIGUOUS_RISK": 0.07
  },
  "flags": {
    "is_emotional_without_self_harm": {"score": 0.89, "triggered": true},
    "has_self_harm_signal": {"score": 0.04, "triggered": false}
  }
}
```

Fused output:

```json
{
  "g2_primary": "EMOTIONAL",
  "g2_all": ["EMOTIONAL"]
}
```

Reason:

- emotional distress is present
- self-harm promotion is blocked by negative evidence

## Inference Output Structure

Recommended final classifier-facing payload:

```json
{
  "question": "...",
  "language": "en",
  "topic": {
    "id": "..."
  },
  "g1": {
    "id": "...",
    "reason": "..."
  },
  "g2": {
    "id": "...",
    "reason": "...",
    "score": 0.0
  },
  "g2_all": {
    "ids": ["...", "..."],
    "scores": {
      "...": 0.0
    },
    "selection_reasons": {
      "...": [
        "Classifier head score above threshold.",
        "Added by self-harm promotion rule."
      ]
    }
  },
  "flags": {
    "has_self_harm_signal": {
      "score": 0.0,
      "triggered": true
    }
  }
}
```

## Recommended Implementation Phases

### Phase 1

- normalize `flags` from raw CSVs
- validate schema
- store flags in canonical JSONL

### Phase 2

- add auxiliary flag head to the SLM classifier
- train flags jointly with `topic`, `G1`, `G2`

### Phase 3

- add runtime fusion logic for promotion/suppression
- emit `selection_reasons` for `G2_all`

### Phase 4

- add per-flag evaluation metrics
- calibrate thresholds for high-risk promotions

## Evaluation Requirements

Track:

- primary `G2` accuracy
- `G2_all` overlap recall
- high-risk false-negative rate
- flag precision/recall
- promotion-rule activation counts
- disagreement between raw `G2` head and fused output

Most important slices:

- self-harm indirect ideation
- grooming secrecy
- blackmail / exposure threats
- violence vs dangerous
- safe factual negatives near high-risk language

## Summary

The flag solution improves inference because it gives the runtime a second layer of interpretable evidence beyond the raw `G2` argmax.

The full design is:

- normalize flags from raw data
- train flags as auxiliary targets
- predict them at inference
- fuse them with `G2` head scores, lexicon evidence, and heuristics
- use them to calculate better `G2_all`
- use them to safely promote high-risk labels

This preserves the classifier contract while materially improving recall, disambiguation, and safety quality.
