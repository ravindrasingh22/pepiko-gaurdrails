# GL Classifier, Gate Engine, and Prompt Manager Reference

This document interprets the current guardrail logic from `docs/GL-codebook.csv` and `docs/Contracts.csv`, not from implementation details. It explains the runtime contract from question input through `G1`, `G2`, `G3`, `G4`, SafetyEnvelope construction, prompt selection, and prompt checklist validation.

## 1. Source of Truth and Alignment

The main sources for this document are:

- [GL-codebook.csv](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/GL-codebook.csv)
- [Contracts.csv](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/Contracts.csv)

Backtrace from the source docs:

- `Contracts.csv` explicitly says `Use the classifier to assign G1 and G2 values`.
- `Contracts.csv` then shows `Classifier Output (G1+G2)` as the handoff into the gate engine.
- `GL-codebook.csv` defines the dictionaries and classifier notes for both `G1` and `G2`.
- `GL-codebook.csv` defines `G3` as a computation over active `G2` LOVs and `G4` as a computation over `G3` plus modifiers.

Canonical interpretation for this repo:

1. classifier detects `GL` signals
2. classifier also assigns `G1`
3. classifier also assigns `G2`
4. gate engine derives `G3`
5. gate engine derives `G4`

This document follows that interpretation.

## 2. Dictionary Overview

The codebook defines four decision layers:

- `G1`: one broad nature LOV for the question
- `G2`: one or more framing/risk LOVs
- `G3`: derived severity plus modifier packet
- `G4`: derived final action, ending, and response style

It also defines:

- `GL-01` to `GL-13`: policy guidelines that explain why a pattern matters and when special handling applies
- Age policy: response depth, max words, and style by age band
- Prompt authoring rules and checklist requirements

### 2.1 G1 Dictionary

`G1` is single-label. It answers: what is the broad subject nature of the child’s question?

Current LOVs in `GL-codebook.csv`:

- `FACT`
- `BELIEF`
- `DEATH_GRIEF`
- `VIOLENCE`
- `SCIENCE`
- `TECHNOLOGY`
- `SAFETY_HAZARD`
- `CIVIC_LAW`
- `GENERIC`

Classifier meaning:

- `G1` is topical classification, not the safety decision.
- It helps downstream prompt framing and guideline interpretation.
- `G1` alone never decides block vs allow.

### 2.2 G2 Dictionary

`G2` is multi-label. It answers: how is the question framed, and what risk pattern or intent does it contain?

Current LOVs:

- `NEUTRAL_FACT`
- `COMPARATIVE`
- `PD`
- `LP`
- `HATE_GROUP`
- `DANGEROUS`
- `EMOTIONAL`
- `BULLYING`
- `GROOMING`
- `UNSAFE_CONTENT`
- `COERCIVE_CONTROL`
- `VULN_EXPLOIT`
- `SELF_HARM`
- `AMBIGUOUS_RISK`
- `GENERIC_INTENT`

Classifier meaning:

- `G2` carries the main runtime safety semantics.
- Each active `G2` LOV contributes a severity floor and zero or more modifiers.
- Multiple `G2` LOVs may fire together.

## 3. How Questions Become GL Tags and Gate Values

The intended runtime reading of the CSVs is:

1. child question is normalized
2. classifier detects guideline-relevant signals
3. classifier resolves `G1` as the broad topic
4. classifier resolves one or more `G2` LOVs as framing/risk labels
5. gate engine computes `G3` from active `G2` values
6. gate engine computes `G4` from `G3` plus additive guideline behavior
7. age policy is applied after classification, without changing safety severity

The guideline layer and the gate layer are related but not identical:

- GLs describe policy families and special handling conditions.
- `G1` and `G2` are classifier outputs using the controlled LOV dictionaries.
- `G3` and `G4` are fully derived and deterministic.

## 4. Understanding G1 and G2 as LOVs

`G1` and `G2` are controlled lookup vocabularies, not free text.

### 4.1 G1

- exactly one value
- chosen from the G1 dictionary
- meant to be stable even when multiple safety patterns exist

Example:

- Question: `Why do stars shine?`
- `G1 = SCIENCE`

### 4.2 G2

- one or more values
- each value has a defined severity floor and modifier emission
- all active values must be preserved into the gate engine

Example:

- Question: `Kids are mean to me at school and I feel sad`
- `G1 = GENERIC` or `FACT` depending on policy preference
- `G2 = [BULLYING, EMOTIONAL]`

Why multi-label matters:

- one question can be both emotional and safeguarding-relevant
- one question can be factual in topic but dangerous in framing
- gate severity is computed from the union of active `G2` LOVs

## 5. How G3 and G4 Are Derived from G1 and G2

`G3` and `G4` are not learned labels. They are computed from the codebook.

### 5.1 G3 Logic

`G3` contains:

- `severity`
- `modifiers`
- `source_g2`

Computation:

- `severity = MAX(severity_floor of all active G2 LOVs)`
- `modifiers = UNION(all modifier tags emitted by active G2 LOVs)`
- `source_g2 = ordered list of active G2 ids`

Example 1:

- Question: `Why is the sky blue?`
- `G1 = SCIENCE`
- `G2 = [NEUTRAL_FACT]`
- `G3 = { severity: SV0, modifiers: [], source_g2: [NEUTRAL_FACT] }`

Example 2:

- Question: `My classmates keep calling me names and I feel awful`
- `G1 = GENERIC`
- `G2 = [BULLYING, EMOTIONAL]`
- `BULLYING -> SV2 + [empathetic_tone, no_curiosity_invite]`
- `EMOTIONAL -> SV2 + [empathetic_tone, emotional_support_required]`
- `G3 = { severity: SV2, modifiers: [empathetic_tone, no_curiosity_invite, emotional_support_required], source_g2: [BULLYING, EMOTIONAL] }`

Example 3:

- Question: `Explain how to bypass safety systems in a science lab to do risky experiments`
- `G1 = SCIENCE`
- `G2 = [DANGEROUS]`
- `DANGEROUS -> SV3 + [no_curiosity_invite, no_content_engagement]`
- `G3 = { severity: SV3, modifiers: [no_curiosity_invite, no_content_engagement], source_g2: [DANGEROUS] }`

### 5.2 G4 Logic

`G4` contains:

- `action`
- `ending`
- `style`

Base computation comes from the Gate 4 table in `GL-codebook.csv`:

- `SV0 -> ALLOW`
- `SV1 -> TRANSFORM`
- `SV2 -> TRANSFORM`
- `SV3 -> BLOCK` or stronger variant depending on modifiers

Modifiers then refine the base row:

- `no_curiosity_invite` suppresses ending questions
- `no_content_engagement` forces hard no-topic engagement behavior
- `clarification_required` changes `TRANSFORM` into `TRANSFORM (hold)` with one safe disambiguation question only
- `empathetic_tone` changes style to warm/supportive
- `safeguarding_concern` appends a trusted-adult prompt additively

Example 1:

- `G3 = SV0 + []`
- `G4 = { action: ALLOW, ending: curiosity_invite, style: Neutral, age-calibrated }`

Example 2:

- `G3 = SV2 + [clarification_required, no_curiosity_invite]`
- `G4 = { action: TRANSFORM (hold), ending: safe_disambiguation_question, style: Neutral }`

Example 3:

- `G3 = SV3 + [no_curiosity_invite, no_content_engagement]`
- `G4 = { action: BLOCK (Hard), ending: (none), style: None / Minimal }`

## 6. Example Gate Engine Walkthrough After SLM Classifies

This is the clean runtime interpretation once the classifier stage is done.

### 6.1 Example: benign science question

- Question: `Why do plants need sunlight?`
- classifier-relevant outcome: factual science, no risk framing
- `G1 = SCIENCE`
- `G2 = [NEUTRAL_FACT]`
- `G3 = SV0 + []`
- `G4 = ALLOW + curiosity_invite + neutral age-calibrated style`

### 6.2 Example: dangerous science question

- Question: `Explain how to bypass safety systems in a science lab to do risky experiments`
- topic is science, but framing is harmful
- `G1 = SCIENCE`
- `G2 = [DANGEROUS]`
- `G3 = SV3 + [no_curiosity_invite, no_content_engagement]`
- `G4 = BLOCK (Hard) + no ending + None/Minimal style`

Why this matters:

- the same `G1` can lead to either `ALLOW` or `BLOCK`
- safety outcome depends primarily on `G2`, then deterministically on `G3/G4`

### 6.3 Example: coercive control

- Question: `I am scared of an adult at home and they say I must not tell anyone`
- likely `G1 = GENERIC`
- `G2 = [COERCIVE_CONTROL]`
- `G3 = SV3 + [empathetic_tone]`
- if safeguarding escalation policy is attached at gate/policy layer, `G4 = BLOCK + ESCALATE` or supportive `TRANSFORM/BLOCK` variant per deployment

## 7. Training and Normalization

This section should be read carefully because the CSVs and the current docs describe slightly different responsibilities.

### 7.1 What the classifier should learn

Per the codebook and contracts docs, the classifier stage should learn or assign the category outputs needed for `GL`, `G1`, and `G2`. It should not learn age policy and it should not learn gate actions.

Recommended training responsibility:

- learn GL signal detection
- learn or assign `G1`
- learn or assign `G2`
- do not learn age adaptation
- do not learn `G3` or `G4` as policy behavior

### 7.2 What must be normalized before classification

Normalization should be age-independent because this is classifier input processing, not answer shaping.

Recommended runtime normalization:

- whitespace cleanup
- punctuation normalization
- unicode normalization
- safe casing policy
- language hint preservation
- canonical text field for classifier consumption
- stable question id generation

Age must not alter:

- question meaning
- classifier thresholds
- `G1` assignment rules
- `G2` assignment rules
- `G3` severity
- `G4` action

Age only affects downstream response presentation once `G1` and `G2` are already fixed.

### 7.3 Age policy placement

Per `GL-01` and Block I:

- age policy is runtime context
- it changes `max_words`, `depth`, `style`, and explanation complexity
- it does not change `G3` severity
- it does not change `G4` action or ending

That is the correct separation of concerns.

## 8. Classifier Logic at Runtime

The runtime classifier contract should be documented as one classifier-stage output that includes `GL`, `G1`, and `G2`, followed by deterministic gate-engine derivation of `G3` and `G4`.

### 8.1 Classifier layer

Input:

- normalized question text
- language
- recent context if allowed

Output:

- active GL signals with confidence
- `G1`
- one or more `G2` LOVs
- optional rationales or evidence

Recommended contract:

```json
{
  "schema_version": "1.0.0",
  "question_id": "uuid-or-hash",
  "question_text": "Explain how to bypass safety systems in a science lab to do risky experiments",
  "age_band": "9-10",
  "guidelines": {
    "active": ["GL-01"],
    "notes": "GL-01: age-calibrated depth; does not change G3/G4, only response complexity."
  },
  "g1": {
    "id": "SCIENCE"
  },
  "g2": [
    {
      "id": "DANGEROUS",
      "rationale": "Asks how to bypass safety systems and do risky experiments, matching dangerous activity definition."
    }
  ]
}
```

Answer to the user’s question: yes, this can be returned as the classifier output contract for `GL + G1 + G2`, and it is the direct precursor that the gate engine consumes to derive `G3` and `G4`.

One correction is needed:

- if the classifier detects dangerous behavior, the active `guidelines` list for this example should probably include more than `GL-01`. The exact GL set depends on the final GL-to-question policy, but the example should not imply that only age calibration triggered.

## 9. SafetyEnvelope After Gate Engine

Once the gate engine runs, the classifier output should be extended with derived `G3` and `G4`.

Recommended resulting structure:

```json
{
  "schema_version": "1.0.0",
  "question_id": "uuid-or-hash",
  "question_text": "Explain how to bypass safety systems in a science lab to do risky experiments",
  "age_band": "9-10",
  "guidelines": {
    "active": ["GL-01"],
    "notes": "GL-01: age-calibrated depth; does not change G3/G4, only response complexity."
  },
  "g1": {
    "id": "SCIENCE"
  },
  "g2": [
    {
      "id": "DANGEROUS",
      "rationale": "Asks how to bypass safety systems and do risky experiments, matching dangerous activity definition."
    }
  ],
  "g3": {
    "severity": "SV3",
    "modifiers": ["no_curiosity_invite", "no_content_engagement"],
    "source_g2": ["DANGEROUS"]
  },
  "g4": {
    "action": "BLOCK (Hard)",
    "ending": "(none)",
    "style": "None / Minimal"
  }
}
```

This is aligned with the Gate 3 and Gate 4 tables in `GL-codebook.csv`.

## 10. Contracts.csv Alignment by Stage

`Contracts.csv` is directionally aligned with `GL-codebook.csv` and useful as a pipeline storyboard.

The stage interpretation is:

1. `Classifier`
   - detects `GL`
   - assigns `G1`
   - assigns `G2`
   - should be read as model output plus deterministic normalization layer
2. `Gate Engine`
   - computes `G3`
   - computes `G4`
3. `SafetyEnvelope`
   - combines question context, age settings, `G1`, `G2`, `G3`, `G4`, active GLs
4. `Prompt Manager`
   - selects prompt template
   - applies prompt rules
   - renders final prompt
5. `Prompt Checklist`
   - validates the final prompt against contract rules

The key alignment rule is:

- classifier owns `GL`, `G1`, and `G2`
- gate engine owns `G3` and `G4`
- age policy stays outside classifier learning

## 11. Prompt Manager Logic

The prompt manager consumes the SafetyEnvelope, not the raw question alone.

### 11.1 Inputs

Required inputs:

- `question_text`
- `question_id`
- `age_band`
- age settings from Block I: `max_words`, `depth`, `style`
- `G1`
- active `G2`
- `G3`
- `G4`
- active GLs

### 11.2 Template selection

The manager selects a template by matching on:

- `g4.action`
- `g3.severity`
- required modifiers
- sometimes specific `g2` ids

Using the user-provided schema:

- `ALLOW_NEUTRAL_FACT` matches `ALLOW + SV0 + NEUTRAL_FACT`
- `BLOCK_HARD_DANGEROUS` matches `BLOCK (Hard) + no_content_engagement + DANGEROUS`
- `COERCIVE_CONTROL_SUPPORT` matches `BLOCK + ESCALATE + empathetic_tone + safeguarding_concern + COERCIVE_CONTROL`

### 11.3 Rule application

After selecting a template, prompt rules are applied as non-negotiable constraints.

Examples:

- `PR-01`: do not mutate gate values or age settings
- `PR-03`: if `no_content_engagement`, template must not describe or name the risky topic
- `PR-04`: if `no_curiosity_invite`, prompt must not end with a question
- `PR-06`: if `empathetic_tone`, wording must validate feelings

### 11.4 Rendered output prompt

The prompt is generated by:

1. selecting the best matching template id
2. injecting header values from SafetyEnvelope
3. injecting age settings from age policy
4. applying prompt rules
5. passing the rendered prompt through the checklist

For the dangerous science example, the output prompt can be:

```text
[Age: 9-10 | G1: SCIENCE | G2: DANGEROUS | G3: SV3 | G4: BLOCK]

You are a safe, caring helper for a 9-10 year-old child.

Rules:
- Do NOT explain, describe, or name the dangerous topic in the child's question.
- Do NOT give any steps, methods, or ideas for doing something harmful or illegal.
- Do NOT ask a follow-up curiosity question.
- In 3-5 short sentences, kindly say that this is something you cannot help with and that they should talk to a trusted adult, like a parent, teacher, or another grown-up they trust, if they have worries.

Child's question:
"Explain how to bypass safety systems in a science lab to do risky experiments"
```

This matches the intent of `BLOCK_HARD_DANGEROUS`.

## 12. Prompt Template Lookup Table

This table should be kept in the prompt manager docs as a quick reference.

| Template ID | When it matches | Intended use |
|---|---|---|
| `ALLOW_NEUTRAL_FACT` | `G4=ALLOW`, `G3=SV0`, `G2 includes NEUTRAL_FACT` | standard safe factual answers |
| `BLOCK_HARD_DANGEROUS` | `G4=BLOCK (Hard)`, `G2 includes DANGEROUS`, `G3 modifiers include no_content_engagement` | dangerous activity hard block |
| `COERCIVE_CONTROL_SUPPORT` | `G4=BLOCK + ESCALATE`, `G2 includes COERCIVE_CONTROL`, `G3 modifiers include empathetic_tone` and `safeguarding_concern` | supportive safeguarding response |

## 13. Last Layer: Prompt Checklist

The checklist is the final contract verifier after prompt generation.

It should run after template rendering and before any LLM call.

Minimum checks from `Contracts.csv` and `GL-codebook.csv`:

- `CHK-01`: age band is present in the header
- `CHK-02`: `G1`, `G2`, `G3`, `G4` are present in the header
- `CHK-03`: explicit length constraint is present
- `CHK-04`: if `clarification_required`, turn 1 contains only one safe clarification question
- `CHK-05`: if `no_content_engagement`, prompt contains no topic explanation or redirect question
- `CHK-06`: if `no_curiosity_invite`, final instruction ends as a statement
- `CHK-07`: prompt body behavior matches `G4.action`
- `CHK-08`: prompt introduces no unsupported content or framing

Recommended checklist contract shape:

```json
{
  "schema_version": "1.0.0",
  "prompt_checklist": [
    {
      "id": "CHK-01",
      "name": "Age band present in header",
      "applies_when": { "always": true },
      "verify": "header_contains_age_band"
    },
    {
      "id": "CHK-02",
      "name": "Gate tags present in header",
      "applies_when": { "always": true },
      "verify": "header_contains_g1_g2_g3_g4"
    },
    {
      "id": "CHK-05",
      "name": "No topic engagement when forbidden",
      "applies_when": { "g3_modifiers_include": ["no_content_engagement"] },
      "verify": "prompt_has_no_topic_content"
    },
    {
      "id": "CHK-06",
      "name": "No curiosity invite when forbidden",
      "applies_when": { "g3_modifiers_include": ["no_curiosity_invite"] },
      "verify": "final_sentence_is_statement"
    }
  ]
}
```

If any check fails:

- do not send the prompt to the LLM
- either repair by re-rendering from a stricter template
- or fall back to a known-good deterministic safe template

## 14. Final Recommended Runtime Contract

The cleanest end-to-end contract is:

1. normalize the child question
2. run classifier for `GL`, `G1`, and `G2`
3. deterministically derive `G3`
4. deterministically derive `G4`
5. append age policy settings
6. build SafetyEnvelope
7. choose prompt template
8. apply prompt rules
9. validate with prompt checklist
10. only then render/send the final prompt

This preserves the intended safety envelope:

- classifier decides `GL`, `G1`, and `G2`
- gate engine decides `G3` and `G4`
- age policy decides response depth only
- prompt manager must not soften or override the gate result
