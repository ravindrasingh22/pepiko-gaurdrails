# Flag Solution Logic

This document defines a flag-based solution that stays consistent with the current repository constraints.

Constraints:

- `G1` is trained as a single-label output.
- primary `G2` is trained as a single-label output.
- `G2_all` is not a training target.
- `G2_all` is calculated only at inference.
- only flags that already exist in the raw CSV files are allowed in this design.
- promotion logic must remain grounded in the flag semantics already present in the raw training files.

This document does not introduce new flag names.

## Scope

The purpose of flags in this repo is:

- improve separation between close `G2` classes
- improve safety recall for high-risk classes
- support calculated `G2_all`
- provide additional evidence for runtime fusion

Flags do not replace:

- `topic`
- `G1`
- primary `G2`

Important:

- flags must not be treated as one-to-one label definitions
- a flag is evidence, not a final class
- the same flag can support multiple `G2` labels
- the same `G2` label can be supported by multiple different flag combinations
- final `G2` resolution must come from fused evidence, not from a single flag firing

## Existing Raw Flags

These are the only flags currently present in the raw CSV files.

### Full union of existing flags

```text
direct_intent
has_ambiguous_risk
has_bullying_involved
has_coercive_control
has_dangerous_context
has_emotional_distress
has_grooming_involved
has_hate_group_language
has_personal_direction
has_safety_hazard
has_self_harm
has_unsafe_sexual_content
has_violence_possibility
has_vuln_exploit
indirect_intent
needs_clarification
```

### File-by-file flag usage

#### `ambiguous_risk_training_schema.csv`

- `has_ambiguous_risk`
- `has_dangerous_context`
- `has_emotional_distress`
- `has_safety_hazard`

#### `bullying_training_schema.csv`

- `has_bullying_involved`
- `has_dangerous_context`
- `has_emotional_distress`
- `has_hate_group_language`
- `has_violence_possibility`

#### `coercive_control_training_schema.csv`

- `has_bullying_involved`
- `has_coercive_control`
- `has_dangerous_context`
- `has_emotional_distress`
- `has_violence_possibility`
- `has_vuln_exploit`

#### `dangerous_training_schema.csv`

- `has_bullying_involved`
- `has_dangerous_context`
- `has_emotional_distress`
- `has_self_harm`
- `has_violence_possibility`

#### `grooming_training_schema.csv`

- `has_coercive_control`
- `has_emotional_distress`
- `has_grooming_involved`
- `has_vuln_exploit`

#### `hate_group_training_schema.csv`

- `has_bullying_involved`
- `has_dangerous_context`
- `has_emotional_distress`
- `has_hate_group_language`
- `has_violence_possibility`

#### `personal_direction_training_schema.csv`

- `has_bullying_involved`
- `has_coercive_control`
- `has_dangerous_context`
- `has_emotional_distress`
- `has_grooming_involved`
- `has_personal_direction`
- `has_self_harm`
- `has_unsafe_sexual_content`
- `has_violence_possibility`
- `has_vuln_exploit`

#### `safety_hazard_training_schema.csv`

- `has_dangerous_context`
- `has_emotional_distress`
- `has_safety_hazard`

#### `self_harm.csv`

- `direct_intent`
- `has_emotional_distress`
- `has_self_harm`
- `indirect_intent`
- `needs_clarification`

#### `unsafe_sexual_content_training_schema.csv`

- `has_bullying_involved`
- `has_coercive_control`
- `has_emotional_distress`
- `has_grooming_involved`
- `has_unsafe_sexual_content`
- `has_vuln_exploit`

#### `violence_training_schema.csv`

- `has_ambiguous_risk`
- `has_bullying_involved`
- `has_dangerous_context`
- `has_emotional_distress`
- `has_personal_direction`
- `has_self_harm`
- `has_violence_possibility`

#### `vuln_exploit_training_schema.csv`

- `has_bullying_involved`
- `has_coercive_control`
- `has_dangerous_context`
- `has_emotional_distress`
- `has_grooming_involved`
- `has_self_harm`
- `has_unsafe_sexual_content`
- `has_vuln_exploit`

## How Flags Should Be Used

Flags should be used in two places:

1. normalization for training
2. inference-time fusion

Flags should not be used to create a new training target for `G2_all`.

## Training Data Structure

The current training target remains:

- `topic`
- `g1`
- primary `g2`
- intent families
- intent phrases

Flags are auxiliary evidence.

### Raw row structure

Recommended raw shape:

```csv
TOPIC,QUESTION,G1,G2,flags,lov_name,objective
Self-harm direct intent,"I want to die.",DEATH_GRIEF,SELF_HARM,"{""direct_intent"": true, ""has_emotional_distress"": true, ""has_self_harm"": true, ""indirect_intent"": false, ""needs_clarification"": false}",Self-Harm / Suicidal Ideation,Classify child text into SELF_HARM, EMOTIONAL, or AMBIGUOUS_RISK
```

### Normalized training row

`G2_all` should not be part of the training contract.

Recommended normalized row:

```json
{
  "sample_id": "self_harm_001",
  "question": "I want to die.",
  "context": "none",
  "topic": "Self-harm direct intent",
  "g1": "DEATH_GRIEF",
  "g2": ["SELF_HARM"],
  "intent_families": ["suicidal_ideation"],
  "intent_phrases": ["I want to die"],
  "review_status": "approved",
  "flags": {
    "direct_intent": true,
    "has_emotional_distress": true,
    "has_self_harm": true,
    "indirect_intent": false,
    "needs_clarification": false
  }
}
```

## Normalization Rules

Normalization should:

1. parse the `flags` JSON column
2. retain only known raw-file flags
3. fill missing known flags with `false`
4. reject unknown flags rather than silently expanding the schema
5. preserve author-provided flag values exactly

Recommended normalized flag schema:

```json
{
  "direct_intent": false,
  "has_ambiguous_risk": false,
  "has_bullying_involved": false,
  "has_coercive_control": false,
  "has_dangerous_context": false,
  "has_emotional_distress": false,
  "has_grooming_involved": false,
  "has_hate_group_language": false,
  "has_personal_direction": false,
  "has_safety_hazard": false,
  "has_self_harm": false,
  "has_unsafe_sexual_content": false,
  "has_violence_possibility": false,
  "has_vuln_exploit": false,
  "indirect_intent": false,
  "needs_clarification": false
}
```

## Training Logic

Recommended training outputs:

1. `topic` head
2. `g1` head
3. primary `g2` head
4. intent-family head
5. intent-phrase head
6. optional auxiliary flag head

Important:

- flags can be trained as auxiliary targets
- `G2_all` is not trained
- flags are not a replacement for `G2`

### Optional auxiliary flag head

If added, the flag head should predict only the existing raw flags.

Example:

```json
{
  "topic_logits": "...",
  "g1_logits": "...",
  "g2_logits": "...",
  "intent_family_logits": "...",
  "intent_phrase_logits": "...",
  "flag_logits": {
    "direct_intent": 0.91,
    "has_self_harm": 0.96,
    "has_emotional_distress": 0.88,
    "needs_clarification": 0.07
  }
}
```

## Inference Structure

At inference, the model should output:

- `topic`
- `G1`
- primary `G2`
- intent-family probabilities
- intent-phrase probabilities
- optional predicted flag probabilities

Then runtime fusion should calculate `G2_all`.

Recommended classifier-facing internal structure:

```json
{
  "question": "An older person online says our chats should stay secret.",
  "context": "They say I am special and should not tell my parents.",
  "topic": "...",
  "g1": {
    "id": "GENERIC"
  },
  "g2_primary": {
    "id": "GROOMING",
    "score": 0.63
  },
  "g2_head_scores": {
    "GROOMING": 0.63,
    "VULN_EXPLOIT": 0.52,
    "EMOTIONAL": 0.18
  },
  "flags": {
    "has_grooming_involved": {
      "score": 0.94,
      "triggered": true
    },
    "has_vuln_exploit": {
      "score": 0.61,
      "triggered": true
    },
    "has_emotional_distress": {
      "score": 0.24,
      "triggered": false
    }
  }
}
```

## How G2_all Should Be Calculated

Since `G2_all` is no longer in training, it should be calculated at inference from:

1. per-label probabilities from the primary `G2` head
2. predicted flags
3. intent lexicon evidence
4. existing heuristics

Recommended base rule:

```text
G2_all =
  classifier-head labels above threshold
  UNION labels supported by active flags
  UNION labels supported by intent lexicon
  UNION labels supported by heuristics
```

Primary `G2` must always be included in `G2_all`.

## Existing Flag-to-G2 Rules Extracted from Raw CSV

This section is extracted from the raw CSVs, not invented by hand.

Interpretation rules:

- `Always flags` means the flag is true in every row for that `G2`
- `Strong observed combinations` are the most common positive-flag combinations found in raw rows for that `G2`
- these combinations are the safest basis for promotion logic
- these combinations are not exclusive definitions of the label
- overlapping combinations across labels are expected and must be resolved by fusion and priority rules

| G2 | Rows | Always flags | Strong observed combinations |
|---|---:|---|---|
| `AMBIGUOUS_RISK` | 130 | none | `has_ambiguous_risk + has_dangerous_context`, `has_dangerous_context + has_safety_hazard`, `has_emotional_distress + needs_clarification`, `has_emotional_distress + indirect_intent + needs_clarification` |
| `BULLYING` | 40 | `has_bullying_involved` | `has_bullying_involved + has_emotional_distress`, `has_bullying_involved`, `has_bullying_involved + has_dangerous_context` |
| `COERCIVE_CONTROL` | 30 | `has_coercive_control` | `has_coercive_control`, `has_coercive_control + has_emotional_distress`, `has_coercive_control + has_emotional_distress + has_violence_possibility` |
| `DANGEROUS` | 35 | `has_dangerous_context` | `has_dangerous_context`, `has_dangerous_context + has_violence_possibility` |
| `EMOTIONAL` | 74 | none | `has_emotional_distress`, `has_dangerous_context + has_emotional_distress`, `has_bullying_involved + has_emotional_distress` |
| `GENERIC_INTENT` | 40 | none | `(none)`, `has_dangerous_context`, `has_emotional_distress` |
| `GROOMING` | 32 | `has_grooming_involved` | `has_grooming_involved`, `has_grooming_involved + has_vuln_exploit`, `has_emotional_distress + has_grooming_involved` |
| `HATE_GROUP` | 35 | `has_hate_group_language` | `has_hate_group_language`, `has_bullying_involved + has_hate_group_language`, `has_hate_group_language + has_violence_possibility` |
| `NEUTRAL_FACT` | 74 | none | `(none)`, `has_dangerous_context` |
| `PERSONAL_DIRECTION` | 40 | `has_personal_direction` | `has_personal_direction`, `has_emotional_distress + has_personal_direction`, `has_dangerous_context + has_personal_direction` |
| `SAFETY_HAZARD` | 35 | `has_dangerous_context + has_safety_hazard` | `has_dangerous_context + has_safety_hazard` |
| `SELF_HARM` | 51 | `has_emotional_distress` | `has_emotional_distress + has_self_harm + indirect_intent`, `direct_intent + has_emotional_distress + has_self_harm`, `has_dangerous_context + has_emotional_distress + has_self_harm` |
| `UNSAFE_SEXUAL_CONTENT` | 30 | `has_unsafe_sexual_content` | `has_unsafe_sexual_content`, `has_grooming_involved + has_unsafe_sexual_content`, `has_emotional_distress + has_grooming_involved + has_unsafe_sexual_content` |
| `VIOLENCE` | 50 | `has_violence_possibility` | `has_violence_possibility`, `has_emotional_distress + has_violence_possibility`, `has_dangerous_context + has_violence_possibility` |
| `VULN_EXPLOIT` | 30 | `has_vuln_exploit` | `has_emotional_distress + has_vuln_exploit`, `has_dangerous_context + has_emotional_distress + has_vuln_exploit`, `has_coercive_control + has_vuln_exploit` |

### Important observations from raw data

- `SELF_HARM` is not driven by a single raw flag. The common raw patterns are:
  - `direct_intent + has_emotional_distress + has_self_harm`
  - `has_emotional_distress + has_self_harm + indirect_intent`
- there are no one-to-one flag definitions for `G2`
- several flags are shared across multiple labels, especially:
  - `has_emotional_distress`
  - `has_dangerous_context`
  - `has_violence_possibility`
- overlapping flag combinations are normal and must be expected in runtime fusion
- `NEUTRAL_FACT` is not promoted by flags. Raw rows show that it may coexist with weak background signals such as `has_dangerous_context`, but those flags do not define or promote the label.
- `GENERIC_INTENT` is not promoted by flags. It behaves as a fallback when stronger risk-label evidence is absent or insufficient.
- `SAFETY_HAZARD` always appears with both:
  - `has_dangerous_context`
  - `has_safety_hazard`
- `DANGEROUS` always includes `has_dangerous_context`
- `VIOLENCE` always includes `has_violence_possibility`
- `GROOMING` always includes `has_grooming_involved`
- `VULN_EXPLOIT` always includes `has_vuln_exploit`
- `COERCIVE_CONTROL` always includes `has_coercive_control`
- `HATE_GROUP` always includes `has_hate_group_language`
- `BULLYING` always includes `has_bullying_involved`
- `PERSONAL_DIRECTION` always includes `has_personal_direction`
- `UNSAFE_SEXUAL_CONTENT` always includes `has_unsafe_sexual_content`

## Promotion Logic

Promotion logic should be based on the raw combinations above, not on single-flag intuition alone.

Promotion rules must be read as:

- observed evidence patterns
- not one-to-one label definitions
- not exclusive class signatures

If the same flag or flag combination appears across multiple labels, runtime should:

1. keep all supported labels in `G2_all`
2. use classifier scores, lexicon evidence, heuristics, and priority rules to resolve primary `G2`

### 1. Single-flag candidate rules

These are allowed only where the raw data shows the flag is an `always flag` for that `G2`.

They should be interpreted as:

- strong candidate support for the label
- not sufficient by themselves to unconditionally add the label
- never sufficient by themselves to force primary `G2`

Recommended usage:

```text
If an always-flag is active,
the label becomes eligible for addition to G2_all,
but final addition should still require corroboration from at least one of:

1. classifier head score for that label above a support threshold
2. lexicon evidence
3. heuristic evidence
```

| Single flag | Runtime implication |
|---|---|
| `has_grooming_involved` | make `GROOMING` eligible for addition to `G2_all` |
| `has_vuln_exploit` | make `VULN_EXPLOIT` eligible for addition to `G2_all` |
| `has_coercive_control` | make `COERCIVE_CONTROL` eligible for addition to `G2_all` |
| `has_hate_group_language` | make `HATE_GROUP` eligible for addition to `G2_all` |
| `has_personal_direction` | make `PERSONAL_DIRECTION` eligible for addition to `G2_all` |
| `has_unsafe_sexual_content` | make `UNSAFE_SEXUAL_CONTENT` eligible for addition to `G2_all` |
| `has_bullying_involved` | make `BULLYING` eligible for addition to `G2_all` |

Example:

```text
Unsafe rule:
  if has_grooming_involved:
      add GROOMING

Safer rule:
  if has_grooming_involved and (
      g2_score[GROOMING] >= 0.35
      or lexicon_support[GROOMING] == true
      or heuristic_support[GROOMING] == true
  ):
      add GROOMING
```

Why this matters:

- raw data tells us `has_grooming_involved` is always present in `GROOMING` rows
- raw data does not prove that every future predicted `has_grooming_involved=true` case must receive `GROOMING`
- without corroboration, noisy flag predictions can inflate false positives in `G2_all`

### 2. Combination-based promotion rules

These are stronger rules derived from observed combinations in raw rows.

| Observed rule from raw files | Runtime implication |
|---|---|
| `direct_intent + has_emotional_distress + has_self_harm` | promote `SELF_HARM` |
| `has_emotional_distress + has_self_harm + indirect_intent` | add `SELF_HARM` and allow promotion if classifier score is close |
| `indirect_intent + needs_clarification` | add `AMBIGUOUS_RISK` |
| `has_dangerous_context + has_violence_possibility` | add `DANGEROUS` and `VIOLENCE` |
| `has_dangerous_context + has_safety_hazard` | add `SAFETY_HAZARD` |
| `has_grooming_involved + has_vuln_exploit` | keep both `GROOMING` and `VULN_EXPLOIT` |
| `has_coercive_control + has_vuln_exploit` | keep both `COERCIVE_CONTROL` and `VULN_EXPLOIT` |
| `has_bullying_involved + has_hate_group_language` | keep both `BULLYING` and `HATE_GROUP` |
| `has_emotional_distress + has_personal_direction` | keep both `EMOTIONAL` and `PERSONAL_DIRECTION` |
| `has_emotional_distress + has_bullying_involved` | keep `BULLYING`; allow `EMOTIONAL` as supporting secondary |
| `has_emotional_distress + has_grooming_involved` | keep `GROOMING`; allow `EMOTIONAL` as supporting secondary |
| `has_emotional_distress + has_vuln_exploit` | keep `VULN_EXPLOIT`; allow `EMOTIONAL` as supporting secondary |
| `has_emotional_distress + has_coercive_control` | keep `COERCIVE_CONTROL`; allow `EMOTIONAL` as supporting secondary |

### 3. Never single-flag promote rules

These flags overlap too broadly across labels and must not be used alone to promote a primary `G2`.

| Flag | Why not |
|---|---|
| `has_emotional_distress` | appears across `SELF_HARM`, `EMOTIONAL`, `BULLYING`, `GROOMING`, `VULN_EXPLOIT`, `COERCIVE_CONTROL`, `PERSONAL_DIRECTION`, `VIOLENCE`, `AMBIGUOUS_RISK` |
| `has_dangerous_context` | appears across `DANGEROUS`, `SAFETY_HAZARD`, `VIOLENCE`, `AMBIGUOUS_RISK`, and even some `NEUTRAL_FACT` / `GENERIC_INTENT` rows |
| `has_violence_possibility` | appears across `VIOLENCE`, `DANGEROUS`, `HATE_GROUP`, `COERCIVE_CONTROL`, `BULLYING` |
| `has_ambiguous_risk` | is inherently broad and not tied to a single `G2` |

These flags may still:

- add weak support
- add secondary labels
- participate inside multi-flag patterns

But they should not alone force primary `G2`.

Boolean form example:

```text
SELF_HARM_PROMOTE =
  (
    direct_intent
    AND has_emotional_distress
    AND has_self_harm
  )
  OR
  (
    has_emotional_distress
    AND has_self_harm
    AND indirect_intent
  )
  OR
  (
    has_dangerous_context
    AND has_emotional_distress
    AND has_self_harm
  )
```

Interpretation:

- each parenthesized group is an observed positive pattern from raw rows
- terms inside one group are `AND`
- different groups are connected by `OR`
- if any one group is satisfied, `SELF_HARM` should be added or promoted at inference

### Co-occurrence rules

| Observed raw combination | Runtime implication |
|---|---|
| `has_dangerous_context + has_violence_possibility` | keep both `DANGEROUS` and `VIOLENCE` in `G2_all` |
| `has_grooming_involved + has_vuln_exploit` | keep both `GROOMING` and `VULN_EXPLOIT` in `G2_all` |
| `has_coercive_control + has_vuln_exploit` | keep both `COERCIVE_CONTROL` and `VULN_EXPLOIT` in `G2_all` |
| `has_bullying_involved + has_hate_group_language` | keep both `BULLYING` and `HATE_GROUP` in `G2_all` |
| `has_emotional_distress + has_personal_direction` | keep both `PERSONAL_DIRECTION` and `EMOTIONAL` in `G2_all` |
| `has_emotional_distress + has_grooming_involved` | keep `GROOMING`; allow `EMOTIONAL` as supporting secondary |
| `has_emotional_distress + has_vuln_exploit` | keep `VULN_EXPLOIT`; allow `EMOTIONAL` as supporting secondary |
| `has_emotional_distress + has_coercive_control` | keep `COERCIVE_CONTROL`; allow `EMOTIONAL` as supporting secondary |
| `has_emotional_distress + has_bullying_involved` | keep `BULLYING`; allow `EMOTIONAL` as supporting secondary |

### Absence-based rules

The raw files also show:

- `GENERIC_INTENT` is often associated with no positive flags
- `NEUTRAL_FACT` is often associated with no positive flags

Runtime implication:

- no active positive flags can support `GENERIC_INTENT` or `NEUTRAL_FACT`
- but these labels should not override stronger promoted risk labels

Explicit fallback definitions:

```text
NEUTRAL_FACT is not promoted by flags.
It is selected only when no stronger risk promotion fires
and classifier or phrasing evidence supports safe factual framing.
```

```text
GENERIC_INTENT is not promoted by flags.
It is a fallback outcome used when no stronger risk promotion fires
and no specific G2 has enough support to win.
```

## Priority Resolution

After building `G2_all`, resolve primary `G2` using risk-first priority.

Recommended runtime order:

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

This priority should be applied after:

- classifier-head thresholding
- flag promotions
- lexicon additions
- heuristic additions

## Detailed Examples

### Example 1: Self-harm

Question:

```text
I want to die tonight.
```

Context:

```text
none
```

Raw flags:

```json
{
  "direct_intent": true,
  "has_emotional_distress": true,
  "has_self_harm": true,
  "indirect_intent": false,
  "needs_clarification": false
}
```

Model output:

```json
{
  "g2_head_scores": {
    "EMOTIONAL": 0.46,
    "SELF_HARM": 0.42,
    "AMBIGUOUS_RISK": 0.11
  }
}
```

Runtime fusion:

- base threshold may keep only `EMOTIONAL`
- `direct_intent=true` and `has_self_harm=true`
- add `SELF_HARM`
- promote `SELF_HARM` over `EMOTIONAL`

Final:

```json
{
  "g2": "SELF_HARM",
  "g2_all": ["SELF_HARM", "EMOTIONAL"]
}
```

### Example 2: Grooming plus vulnerability exploitation

Question:

```text
Someone older online told me our chats are secret and says they will get upset if I tell anyone.
```

Context:

```text
They say I am special and only they understand me.
```

Raw flags:

```json
{
  "has_grooming_involved": true,
  "has_vuln_exploit": true,
  "has_emotional_distress": true,
  "has_coercive_control": false
}
```

Model output:

```json
{
  "g2_head_scores": {
    "GROOMING": 0.58,
    "VULN_EXPLOIT": 0.44,
    "EMOTIONAL": 0.22
  }
}
```

Runtime fusion:

- threshold keeps `GROOMING`
- flags add `VULN_EXPLOIT`
- `has_emotional_distress=true` adds `EMOTIONAL` only if score or heuristics support it

Final:

```json
{
  "g2": "GROOMING",
  "g2_all": ["GROOMING", "VULN_EXPLOIT"]
}
```

### Example 3: Dangerous plus violence

Question:

```text
How can I poison someone using things from around the house?
```

Context:

```text
none
```

Raw flags:

```json
{
  "has_dangerous_context": true,
  "has_violence_possibility": true,
  "has_emotional_distress": false,
  "has_self_harm": false,
  "has_bullying_involved": false
}
```

Model output:

```json
{
  "g2_head_scores": {
    "DANGEROUS": 0.61,
    "VIOLENCE": 0.39,
    "NEUTRAL_FACT": 0.12
  }
}
```

Runtime fusion:

- threshold keeps `DANGEROUS`
- `has_violence_possibility=true` adds `VIOLENCE`

Final:

```json
{
  "g2": "DANGEROUS",
  "g2_all": ["DANGEROUS", "VIOLENCE"]
}
```

### Example 4: Ambiguous self-harm

Question:

```text
Sometimes I want to disappear forever.
```

Context:

```text
none
```

Raw flags:

```json
{
  "direct_intent": false,
  "has_emotional_distress": true,
  "has_self_harm": true,
  "indirect_intent": true,
  "needs_clarification": true
}
```

Model output:

```json
{
  "g2_head_scores": {
    "EMOTIONAL": 0.48,
    "SELF_HARM": 0.41,
    "AMBIGUOUS_RISK": 0.29
  }
}
```

Runtime fusion:

- `has_self_harm=true` adds `SELF_HARM`
- `indirect_intent=true` and `needs_clarification=true` add `AMBIGUOUS_RISK`
- `has_emotional_distress=true` supports `EMOTIONAL`

Final:

```json
{
  "g2": "SELF_HARM",
  "g2_all": ["SELF_HARM", "EMOTIONAL", "AMBIGUOUS_RISK"]
}
```

## Output Structure at Inference

Recommended classifier-facing structure:

```json
{
  "question": "...",
  "context": "...",
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
    "reason": "..."
  },
  "g2_all": {
    "ids": ["...", "..."],
    "scores": {
      "...": 0.0
    },
    "selection_reasons": {
      "...": [
        "Classifier head score above threshold.",
        "Added because raw-flag-equivalent evidence supports the label."
      ]
    }
  },
  "flags": {
    "has_dangerous_context": {
      "score": 0.0,
      "triggered": true
    }
  }
}
```

## Summary

The consistent design for this repo is:

- train only primary `G2`
- do not train `G2_all`
- retain and normalize only the flags that already exist in the raw sheets
- optionally train those flags as auxiliary outputs
- calculate `G2_all` at inference from:
  - primary `G2` head scores
  - existing raw-flag semantics
  - intent lexicon
  - heuristics

This keeps the implementation aligned with the raw training files and avoids schema drift.
