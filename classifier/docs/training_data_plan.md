# Synthetic Raw Training Data Plan

## Summary

This document is the single source of truth for creating synthetic raw CSV data for the `pikuai-gaurdrails` classifier. It defines the dataset contract, required row balance, per-`G2` authoring notes, flag usage rules, naming convention, and QA checks.

The goal is to create one raw CSV per `G2` label under `pikuai-gaurdrails/data/raw/`, with each file containing both positive and adjacent negative rows so the model learns separation, not just recall.

Current repo fact: `data/raw` is empty in this workspace except for `.gitkeep`, so this plan assumes new synthetic raw sources will be created from scratch.

## Raw File Contract

### File naming

Each raw source file must be named:

`synthetic_data_{G2_LABEL}_{YYYYMMDD_HHMMSS}.csv`

Examples:

- `synthetic_data_VIOLENCE_20260517_143000.csv`
- `synthetic_data_SELF_HARM_20260517_143500.csv`

### Required columns

Each CSV must use this header exactly:

`Topic,Question,G1,G2,flags,intent_families,intent_phrases,review_status`

### Column meaning

- `Topic`: human-readable topic bucket such as `Safety`, `Belief & Religion`, `Technology`, `School`, `General Learning`
- `Question`: the user utterance to classify
- `G1`: single primary `G1` label
- `G2`: primary `G2` label for training
- `flags`: JSON object containing only allowed boolean flags
- `intent_families`: JSON list or comma-separated list when relevant. When omitted, canonical normalization may backfill these from Block J LOV lookup based on primary `G2`.
- `intent_phrases`: JSON list or comma-separated list when relevant
- `review_status`: use `approved` unless a later workflow introduces another fixed value

### Allowed flags only

Only these flags may appear in `flags`:

- `direct_intent`
- `has_ambiguous_risk`
- `has_bullying_involved`
- `has_coercive_control`
- `has_dangerous_context`
- `has_emotional_distress`
- `has_grooming_involved`
- `has_hate_group_language`
- `has_personal_direction`
- `has_safety_hazard`
- `has_self_harm`
- `has_unsafe_sexual_content`
- `has_violence_possibility`
- `has_vuln_exploit`
- `indirect_intent`
- `needs_clarification`

Rules:

- Every `flags` value must be a JSON object.
- Every listed flag value must be a JSON boolean.
- Unknown flags are not allowed.
- Omitted known flags should still be present in the authored JSON where possible to keep rows explicit and reviewable.

### `G2` authoring rule

Training should use only one primary `G2` label per row.

Rules:

- Author `G2` as a single label whenever possible.
- If a raw row contains multiple labels in the `G2` column for compatibility with existing data, training uses only the first label in raw order.
- Do not depend on `G2_all` for training normalization.
- Training uses only the primary `G2`.
- `G2_all` is not part of the active runtime classifier output contract.

Examples:

- If `G2` is `VIOLENCE`, training uses `VIOLENCE`.
- If `G2` is `VIOLENCE,BULLYING`, training uses `VIOLENCE` only.
- If `G2` is `["VIOLENCE","BULLYING"]`, training uses `VIOLENCE` only.

### Example row shape

```csv
Topic,Question,G1,G2,flags,intent_families,intent_phrases,review_status
Safety,"My cousin says I should punch a kid who keeps taking my lunch.",VIOLENCE,VIOLENCE,"{""direct_intent"": false, ""has_ambiguous_risk"": false, ""has_bullying_involved"": true, ""has_coercive_control"": false, ""has_dangerous_context"": true, ""has_emotional_distress"": true, ""has_grooming_involved"": false, ""has_hate_group_language"": false, ""has_personal_direction"": true, ""has_safety_hazard"": false, ""has_self_harm"": false, ""has_unsafe_sexual_content"": false, ""has_violence_possibility"": true, ""has_vuln_exploit"": false, ""indirect_intent"": false, ""needs_clarification"": false}","[""advice_seeking"",""peer_conflict""]","[""should punch"",""taking my lunch""]",approved
```

## Dataset Composition Rules

### Per-file target size

Every `G2` file must contain at least `150` rows.

Default composition per file:

- `120` positive rows where `G2` is the target label
- `30` adjacent negative rows where `G2` is not the target label

Allowed range:

- positives: `115-125`
- negatives: `25-35`
- total: `150-160`

### Positive and negative definition

For a target file such as `VIOLENCE`:

- Positive rows: `G2` is `VIOLENCE`
- Negative rows: `G2` is not `VIOLENCE`

Primary-label rule:

- In positive rows, the target file label should be the first and primary label in `G2`.
- If additional labels are present in raw `G2`, they must not replace the first raw `G2` label for training.

Negative rows must be hard negatives:

- close neighboring classes
- ambiguous but non-target cases
- surface-similar rows that could fool the model
- same-domain non-target cases

Do not fill negatives with easy unrelated trivia.

### Diversity rules

Each file must contain:

- at least `4-6` positive sub-pattern clusters
- at least `3-5` negative confuser groups
- mixed sentence length
- mixed directness
- mixed emotional tone
- mixed explicitness vs implication
- child-like and teen-like phrasing variation
- mixed topic contexts where valid

### Duplicate policy

Do not allow:

- exact duplicate `Question` strings within a file
- exact duplicate `Question` strings across files
- near-duplicate template rewrites with only one noun or verb swapped
- repeated scaffolds such as `"What if..."` or `"Should I..."` used excessively in one cluster

Recommended uniqueness checks:

- normalize case and whitespace before duplicate checks
- strip punctuation for secondary duplicate checks
- manually review clusters for paraphrase overuse

## Label Priority and Adjacency

Target labels to author:

- `UNSAFE_SEXUAL_CONTENT`
- `GROOMING`
- `COERCIVE_CONTROL`
- `VULN_EXPLOIT`
- `SELF_HARM`
- `DANGEROUS`
- `HATE_GROUP`
- `VIOLENCE`
- `PERSONAL_DIRECTION`
- `SAFETY_HAZARD`
- `AMBIGUOUS_RISK`
- `EMOTIONAL`
- `BULLYING`
- `NEUTRAL_FACT`
- `GENERIC_INTENT`

Recommended adjacency map for negatives:

| Target G2 | Main adjacent negative classes |
| --- | --- |
| `UNSAFE_SEXUAL_CONTENT` | `GROOMING`, `VULN_EXPLOIT`, `PERSONAL_DIRECTION`, `NEUTRAL_FACT` |
| `GROOMING` | `VULN_EXPLOIT`, `COERCIVE_CONTROL`, `UNSAFE_SEXUAL_CONTENT`, `EMOTIONAL` |
| `COERCIVE_CONTROL` | `VULN_EXPLOIT`, `GROOMING`, `BULLYING`, `EMOTIONAL` |
| `VULN_EXPLOIT` | `GROOMING`, `COERCIVE_CONTROL`, `BULLYING`, `EMOTIONAL` |
| `SELF_HARM` | `EMOTIONAL`, `AMBIGUOUS_RISK`, `PERSONAL_DIRECTION`, `NEUTRAL_FACT` |
| `DANGEROUS` | `VIOLENCE`, `SAFETY_HAZARD`, `AMBIGUOUS_RISK`, `PERSONAL_DIRECTION` |
| `HATE_GROUP` | `BULLYING`, `VIOLENCE`, `EMOTIONAL`, `NEUTRAL_FACT` |
| `VIOLENCE` | `DANGEROUS`, `BULLYING`, `AMBIGUOUS_RISK`, `PERSONAL_DIRECTION` |
| `PERSONAL_DIRECTION` | every stronger risk class above it, especially `VIOLENCE`, `SELF_HARM`, `UNSAFE_SEXUAL_CONTENT`, `GROOMING`, `DANGEROUS` |
| `SAFETY_HAZARD` | `AMBIGUOUS_RISK`, `DANGEROUS`, `NEUTRAL_FACT`, `PERSONAL_DIRECTION` |
| `AMBIGUOUS_RISK` | `SAFETY_HAZARD`, `EMOTIONAL`, `DANGEROUS`, `NEUTRAL_FACT` |
| `EMOTIONAL` | `BULLYING`, `SELF_HARM`, `VULN_EXPLOIT`, `GENERIC_INTENT` |
| `BULLYING` | `EMOTIONAL`, `VULN_EXPLOIT`, `VIOLENCE`, `HATE_GROUP` |
| `NEUTRAL_FACT` | `GENERIC_INTENT`, `AMBIGUOUS_RISK`, `SAFETY_HAZARD`, `PERSONAL_DIRECTION` |
| `GENERIC_INTENT` | `NEUTRAL_FACT`, `EMOTIONAL`, `AMBIGUOUS_RISK`, `PERSONAL_DIRECTION` |

## Flag Grounding Rules

Flags are evidence, not final classes. Do not collapse a label into one repeated flag pattern.

Use only flag patterns grounded in `flag-solution-logic.md`:

- `SELF_HARM`: emphasize combinations across `direct_intent`, `indirect_intent`, `has_emotional_distress`, `has_self_harm`, `needs_clarification`
- `SAFETY_HAZARD`: emphasize `has_dangerous_context` with `has_safety_hazard`
- `AMBIGUOUS_RISK`: emphasize `has_ambiguous_risk`, `has_dangerous_context`, and some `needs_clarification`
- `GROOMING`: use overlap between `has_grooming_involved`, `has_vuln_exploit`, `has_emotional_distress`, and occasional `has_coercive_control`
- `COERCIVE_CONTROL`: use `has_coercive_control` with overlap into `has_vuln_exploit`, `has_emotional_distress`, and some bullying-like context where justified
- `VULN_EXPLOIT`: use `has_vuln_exploit` with overlap into `has_coercive_control`, `has_grooming_involved`, `has_emotional_distress`
- `VIOLENCE`: use `has_violence_possibility` with some `has_dangerous_context`, some `has_personal_direction`, and rare overlap with `has_bullying_involved`
- `DANGEROUS`: use `has_dangerous_context` heavily, with selective `has_violence_possibility`, `has_self_harm`, or `has_emotional_distress` when grounded
- `UNSAFE_SEXUAL_CONTENT`: use `has_unsafe_sexual_content` with selective overlap into `has_grooming_involved`, `has_vuln_exploit`, `has_emotional_distress`
- `HATE_GROUP`: use `has_hate_group_language`, often with `has_bullying_involved` or `has_violence_possibility` only when supported
- `PERSONAL_DIRECTION`: use `has_personal_direction` but vary whether stronger risk evidence is absent or present

Authoring rule:

- At least `3` distinct positive flag combinations per target file
- At least `1-2` negative confuser rows per file should carry overlapping flags but still resolve to a different `G2`

## Per-G2 Authoring Notes

### `UNSAFE_SEXUAL_CONTENT`

- Positive patterns: requests about sexual material, nudity, explicit content, unsafe photo-sharing, sexualized child-risk context
- Negative confusers: grooming without explicit sexual content, manipulation without sexual content, neutral biology questions, vague embarrassment questions
- Common `G1`: `GENERIC`, sometimes `FACT` depending on topic framing
- Key flags: `has_unsafe_sexual_content`, optional `has_grooming_involved`, `has_vuln_exploit`, `has_emotional_distress`
- Required variety: explicit ask, shame-based disclosure, peer pressure, online-sharing scenario, coded slang

### `GROOMING`

- Positive patterns: secret-keeping with older person, gift-based trust building, isolation from parents, private chat pressure
- Negative confusers: manipulation by peers, coercive friendship, unsafe adult contact that is exploitative but not grooming, emotional secrecy without risk
- Common `G1`: `GENERIC`
- Key flags: `has_grooming_involved`, `has_vuln_exploit`, optional `has_coercive_control`, `has_emotional_distress`
- Required variety: secrecy, flattery, meeting requests, special-bond framing, parent-avoidance language

### `COERCIVE_CONTROL`

- Positive patterns: someone controlling movement, speech, access, clothing, messaging, friendships, or safety through threats or pressure
- Negative confusers: general bullying, exploitation without control, grooming, ordinary rule-setting by parents
- Common `G1`: `GENERIC`
- Key flags: `has_coercive_control`, optional `has_vuln_exploit`, `has_emotional_distress`, `has_bullying_involved`
- Required variety: explicit threats, guilt pressure, isolation, monitoring, forced compliance

### `VULN_EXPLOIT`

- Positive patterns: taking advantage of fear, age, loneliness, disability, confusion, or trust
- Negative confusers: grooming, coercive control, bullying, emotional upset without exploitation
- Common `G1`: `GENERIC`
- Key flags: `has_vuln_exploit`, optional `has_coercive_control`, `has_grooming_involved`, `has_emotional_distress`
- Required variety: peer exploitation, adult exploitation, social manipulation, money/resource exploitation, emotional leverage

### `SELF_HARM`

- Positive patterns: direct self-harm desire, indirect desire to disappear, hopelessness with self-harm implication, alarming self-endangering phrasing
- Negative confusers: sadness, grief, fear, vague distress, dangerous curiosity
- Common `G1`: `DEATH_GRIEF`
- Key flags: `direct_intent`, `indirect_intent`, `has_emotional_distress`, `has_self_harm`, `needs_clarification`
- Required variety: direct statements, veiled statements, conditional statements, help-seeking, shutdown language

### `DANGEROUS`

- Positive patterns: harmful how-to requests, evading detection, causing injury, risky activity instructions, malicious misuse
- Negative confusers: safety questions, accidental injury concern, neutral science curiosity, violent feelings without operational intent
- Common `G1`: `VIOLENCE`, `SAFETY_HAZARD`, `SCIENCE`, `CIVIC_LAW`
- Key flags: `has_dangerous_context`, optional `has_violence_possibility`, `has_self_harm`, `has_emotional_distress`
- Required variety: step-by-step requests, hidden-harm requests, dangerous experiments, sabotage, weaponized advice

### `HATE_GROUP`

- Positive patterns: demeaning or exclusionary language toward protected groups, rights-denial, dehumanizing talk, hate-aligned endorsement
- Negative confusers: bullying without group targeting, neutral civic questions, reporting harmful speech, confusion about stereotypes
- Common `G1`: `CIVIC_LAW`, `GENERIC`
- Key flags: `has_hate_group_language`, optional `has_bullying_involved`, `has_violence_possibility`, `has_emotional_distress`
- Required variety: direct slurs are not required; include coded hostility, exclusion, disgust framing, recruitment-adjacent tone

### `VIOLENCE`

- Positive patterns: intent to hit, injure, attack, retaliate, fight, or advise violence
- Negative confusers: bullying, dangerous operational requests, sports aggression talk, accidental harm, frustration venting
- Common `G1`: `VIOLENCE`
- Key flags: `has_violence_possibility`, optional `has_dangerous_context`, `has_personal_direction`, `has_bullying_involved`, `has_emotional_distress`
- Required variety: self-generated intent, peer advice, revenge framing, defensive framing, conflict escalation

### `PERSONAL_DIRECTION`

- Positive patterns: “what should I do” or “should I” requests where the main signal is guidance-seeking rather than a stronger risk label
- Negative confusers: stronger underlying labels that happen to be phrased as advice-seeking
- Common `G1`: varies widely by domain
- Key flags: `has_personal_direction`, sometimes overlap with nearly any other risk flag
- Required variety: school, family, belief, friendship, online, safety, moral choice
- Special rule: many negative rows should look like personal direction on the surface but resolve to stronger `G2` labels

### `SAFETY_HAZARD`

- Positive patterns: physical safety hazard identification, accidental danger, hazardous object/environment concern
- Negative confusers: explicit harmful intent, vague danger, neutral factual safety education, ambiguous household concern
- Common `G1`: `SAFETY_HAZARD`, sometimes `SCIENCE`
- Key flags: `has_dangerous_context`, `has_safety_hazard`, optional `has_emotional_distress`
- Required variety: electricity, chemicals, tools, home hazards, school hazards, outdoor hazards

### `AMBIGUOUS_RISK`

- Positive patterns: potentially risky situations lacking enough detail, confusing danger, mixed emotional and hazard cues
- Negative confusers: clear safety hazard, clear emotional distress, neutral fact, clear dangerous intent
- Common `G1`: `SAFETY_HAZARD`, `GENERIC`
- Key flags: `has_ambiguous_risk`, `has_dangerous_context`, optional `needs_clarification`, `has_emotional_distress`
- Required variety: objects with unknown danger, unclear online situations, vague household risk, incomplete disclosures

### `EMOTIONAL`

- Positive patterns: sadness, fear, loneliness, grief, crying, shame, overwhelm without stronger self-harm or abuse signal
- Negative confusers: self-harm, bullying, exploitation, generic venting without emotional signal
- Common `G1`: `DEATH_GRIEF`, `GENERIC`
- Key flags: `has_emotional_distress`
- Required variety: grief, school stress, friendship pain, fear, embarrassment, loneliness

### `BULLYING`

- Positive patterns: repeated meanness, exclusion, teasing, social targeting, humiliation, harassment by peers
- Negative confusers: emotional upset without bullying, hate-group targeting, exploitation, physical violence
- Common `G1`: `GENERIC`
- Key flags: `has_bullying_involved`, optional `has_emotional_distress`, `has_violence_possibility`, `has_hate_group_language`
- Required variety: online bullying, school bullying, group exclusion, rumor spreading, mockery, intimidation

### `NEUTRAL_FACT`

- Positive patterns: factual questions, explanatory curiosity, neutral learning, non-advisory knowledge seeking
- Negative confusers: risky-topic questions that are actually operational or advisory, emotionally-loaded “why” questions, ambiguous safety asks
- Common `G1`: `FACT`, `SCIENCE`, `BELIEF`, `TECHNOLOGY`
- Key flags: usually all false or weak background-only flags
- Required variety: science, religion, technology, body, daily life, emotions as neutral explanation

### `GENERIC_INTENT`

- Positive patterns: short generic asks, incomplete prompts, broad non-factual non-risk requests, low-signal conversation starters
- Negative confusers: neutral fact questions, emotional disclosures, advisory asks, ambiguous danger
- Common `G1`: `GENERIC`
- Key flags: usually none
- Required variety: incomplete asks, broad curiosity, non-specific chat openers, context-poor questions

## Per-File Coverage Template

Every generated CSV should have an accompanying internal coverage note using this template:

| Field | Requirement |
| --- | --- |
| Target `G2` | one of the 15 labels |
| File name | `synthetic_data_{G2_LABEL}_{datetime}.csv` |
| Total rows | `150-160` |
| Positive rows | `115-125` |
| Negative rows | `25-35` |
| Positive clusters | at least `4` |
| Negative confuser groups | at least `3` |
| Duplicate check | exact + normalized + manual paraphrase review |
| Flag review | only allowed flags, booleans only |

## QA and Validation

Before considering a file complete, verify:

- file name matches the required pattern
- header matches the required schema
- every row has non-empty `Question`, `G1`, and `G2`
- every positive row has the target label as its primary `G2`
- if `G2` has multiple labels in raw form, training uses only the first label
- every negative row excludes the target label from primary `G2`
- every `G2` label is supported by the repo vocabulary
- every `flags` object parses and uses only allowed booleans
- the positive and negative counts meet the required range
- there are no exact duplicate questions within the file
- there are no cross-file duplicate questions
- the file contains multiple sub-pattern clusters rather than one prompt template repeated many times

Recommended validation pass after a batch of files:

- run source discovery against `data/raw`
- normalize all files through `source_normalizer.py`
- inspect rejected rows
- compute per-file class balance
- compute per-file flag distribution
- spot-check boundary rows where adjacent classes overlap

## Implementation Defaults

- Use `approved` as the default `review_status`.
- Favor explicit full-flag JSON objects rather than sparse flag objects.
- Keep negatives in the same target file.
- Prefer hard negatives over easy negatives.
- Do not introduce new flags.
- Do not treat flags as one-to-one class definitions.
- When a row clearly belongs to a stronger risk class, do not force it into `PERSONAL_DIRECTION`, `GENERIC_INTENT`, or `NEUTRAL_FACT`.
