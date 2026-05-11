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

Operational summary:

- `G3` is derived from `G2`, not from `G1`
- `G1` helps explain topic/nature
- `G2` determines severity floor and emitted modifiers
- if multiple `G2` LOVs fire, `G3` keeps the highest severity and the full combined modifier set

### 5.2 G4 Logic

`G4` contains:

- `action`
- `ending`
- `style`

`G4` is derived from `G3`, not directly from raw question text and not directly from `G1`.

The Gate 4 table in `GL-codebook.csv` must be read exactly this way:

1. Find the row matching `G3_SV`.
2. Inspect `G3_MOD` for any special modifiers.
3. If a modifier-specific variant row exists for that severity, use that variant row instead of the plain base row.
4. Apply the row outputs: `Action`, `Base Ending`, and `Style`.
5. Then apply additive rules such as `safeguarding_concern`, which may append extra child-safety language without replacing the base action.

This is the key rule from the codebook:

- Gate 4 reads `G3_SV` to determine the base action row.
- Gate 4 then reads `G3_MOD` to select the matching modifier variant.
- Both must be checked.
- The outputs are `Action + Base Ending + Style`.
- Ending overrides apply on top of the base ending.

Base action lookup comes from the Gate 4 table in `GL-codebook.csv`:

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

### 5.3 How to read the G4 table

Use this reading order every time:

1. Start with `G3.severity`.
2. Locate the base Gate 4 row for that severity.
3. Check whether `G3.modifiers` match a more specific row for that same severity.
4. If yes, take the more specific row.
5. Output `action`, `ending`, and `style`.
6. Apply any additive post-rules such as `safeguarding_concern`.

Example A: no modifiers

- `G3 = { severity: SV0, modifiers: [] }`
- Step 1: read `SV0`
- Step 2: matching row is `SV0, (none), ALLOW, curiosity_invite, Neutral age-calibrated`
- Step 3: there are no modifiers, so no variant row applies
- Result:
  - `action = ALLOW`
  - `ending = curiosity_invite`
  - `style = Neutral, age-calibrated`

Example B: severity plus clarification modifier

- `G3 = { severity: SV2, modifiers: [clarification_required, no_curiosity_invite] }`
- Step 1: read `SV2`
- Step 2: base row would normally be `TRANSFORM + curiosity_invite`
- Step 3: modifier `clarification_required` matches the `SV2 + clarification_required` variant row
- Step 4: that row overrides normal transform behavior
- Result:
  - `action = TRANSFORM (hold)`
  - `ending = safe_disambiguation_question`
  - `style = Neutral`
- Runtime meaning:
  - Turn 1 must ask exactly one safe clarification question
  - no substantive answer is allowed yet

Example C: severity plus no-content-engagement modifier

- `G3 = { severity: SV3, modifiers: [no_curiosity_invite, no_content_engagement] }`
- Step 1: read `SV3`
- Step 2: base row would normally be `BLOCK + neutral_alternate_question`
- Step 3: modifier combination matches the hard-block variant row for `SV3`
- Step 4: variant row replaces the softer `SV3` block behavior
- Result:
  - `action = BLOCK (Hard)`
  - `ending = (none)`
  - `style = None / Minimal`
- Runtime meaning:
  - no topic engagement
  - no alternate curiosity question
  - no explanatory discussion of the blocked topic

Example D: additive safeguarding rule

- `G3 = { severity: SV3, modifiers: [empathetic_tone, safeguarding_concern, no_curiosity_invite] }`
- Step 1: read `SV3`
- Step 2: match the `SV3` empathetic block variant if present
- Step 3: because `safeguarding_concern` is additive, inherit the chosen row first
- Step 4: append trusted-adult prompt behavior after the chosen row’s base ending logic
- Result:
  - `action` stays inherited from the matched `SV3` row
  - `style` becomes empathetic if the matched row says so
  - trusted-adult guidance is appended additively, not used as a replacement for the base row

### 5.4 Worked G4 examples from `G2 -> G3 -> G4`

Example 1:

- `G3 = SV0 + []`
- `G4 = { action: ALLOW, ending: curiosity_invite, style: Neutral, age-calibrated }`

Example 2:

- `G3 = SV2 + [clarification_required, no_curiosity_invite]`
- `G4 = { action: TRANSFORM (hold), ending: safe_disambiguation_question, style: Neutral }`

Example 3:

- `G3 = SV3 + [no_curiosity_invite, no_content_engagement]`
- `G4 = { action: BLOCK (Hard), ending: (none), style: None / Minimal }`

Example 4:

- `G2 = [EMOTIONAL]`
- `EMOTIONAL -> SV2 + [empathetic_tone, emotional_support_required]`
- `G3 = { severity: SV2, modifiers: [empathetic_tone, emotional_support_required] }`
- Gate 4 reads:
  - base row `SV2`
  - then the `SV2 + empathetic_tone + emotional_support_required` variant row
- `G4 = { action: TRANSFORM, ending: curiosity_invite or omitted if distress is high, style: Empathetic, warm }`

## 6. How GLs are read after G1 and G2 are present

After the classifier has already assigned `GL`, `G1`, and `G2`, each active guideline should be interpreted using the columns in Block E of `GL-codebook.csv`.

Read each GL row in this order:

1. `Applies_When`
2. `Uses_G1_LOVs`
3. `Uses_G2_LOVs`
4. `Special Rules on G3 or G4`

### 6.0 Runtime procedure for a GL row

A single GL row should be interpreted as a policy rule with four parts:

1. trigger
2. expected classifier shape
3. gate effect
4. prompt effect

At runtime, the system should evaluate a GL like this:

1. Check whether the GL is active from classifier output or rule activation logic.
2. Read `Applies_When` to understand the trigger condition that made it active.
3. Compare classifier output `G1` against `Uses_G1_LOVs`.
4. Compare classifier output `G2` against `Uses_G2_LOVs`.
5. If the expected `G1` and `G2` pattern matches, treat the GL as semantically consistent.
6. Compute normal `G3` from active `G2`.
7. Compute normal `G4` from `G3`.
8. Read `Special Rules on G3 or G4`.
9. Convert those special rules into downstream policy notes.
10. Pass those notes into the SafetyEnvelope or prompt contract so the prompt manager can enforce them.

This means a GL row does not directly replace the gate system. It sits on top of it:

- classifier says what was detected
- gate engine says what the base safety action is
- GL special rules explain how that base action must be constrained or extended

### 6.0.1 What a GL row does not do

A GL row does not:

- create free-form prompt text by itself
- bypass `G2 -> G3 -> G4`
- replace the classifier output contract
- replace template matching in the prompt manager

Instead, it provides structured policy meaning for the already-detected case.

### 6.1 What `Applies_When` means

`Applies_When` tells you the trigger condition for that guideline family.

Examples:

- `GL-01` applies when age calibration is needed and `age_band` is set
- `GL-02` applies when comparative belief ranking is detected
- `GL-10` applies when grooming indicators are detected

This answers:

- why the GL is active
- what policy family is in play
- whether the system should expect special handling beyond base Gate 4 behavior

Runtime use:

- treat `Applies_When` as the activation reason
- if the GL is active but the trigger reason is not satisfied, flag it as an inconsistency for review
- if the trigger reason is satisfied, continue to validate the expected `G1` and `G2` shape

### 6.2 What `Uses_G1_LOVs` means

This column tells you which `G1` nature categories the guideline expects or is most relevant to.

Example:

- `GL-02` uses `BELIEF`
- so if classifier output has `G1 = BELIEF`, that is consistent with a comparative belief guideline

`Uses_G1_LOVs` is not itself the final action. It is a validation and interpretation aid.

Runtime use:

- if classifier output `G1` matches one of the LOVs in this column, the GL is topically aligned
- if it does not match, that can mean:
  - classifier drift
  - an ambiguous case
  - a codebook mismatch that needs review
- this column helps confirm that the active GL and the assigned `G1` tell a coherent story

### 6.3 What `Uses_G2_LOVs` means

This column tells you which `G2` framing/risk LOVs the guideline expects.

Example:

- `GL-03` uses `PD`
- `GL-04` uses `LP`
- `GL-10` uses `GROOMING`
- `GL-11` uses `UNSAFE_CONTENT`

This is the most direct bridge between the classifier output and the gate engine because `G2` is what feeds `G3`.

Runtime use:

- this is the strongest semantic check for whether the active GL is supported by the classifier result
- if the GL expects `PD` but `G2` does not contain `PD`, the system should treat that as a mismatch
- if the GL expects `GROOMING` and `G2` contains `GROOMING`, the GL is strongly validated by classifier output

### 6.4 What `Special Rules` means

This column does not define classifier output. It defines downstream policy notes that must be applied after classifier output is already known.

Correct ownership is:

- classifier outputs `GL`, `G1`, and `G2`
- gate engine derives `G3` and `G4`
- gate engine also interprets active GL `Special Rules on G3 or G4`
- prompt manager turns those special-rule notes into final prompt instructions

That means:

- first compute normal `G3` from `G2`
- then compute normal `G4` from `G3`
- then read the active GL’s special rules
- if the GL says to override, extend, suppress, or append something, the gate engine records that as prompt-facing policy notes
- the prompt manager must then include those notes in the final prompt contract and rendered prompt

This is how the codebook expresses policy nuance without making those notes part of classifier prediction.

Runtime use:

- interpret `Special Rules` only after base `G4` is known
- convert each rule into structured prompt-policy instructions, not raw prose
- examples of derived note types:
  - `suppress_curiosity_invite`
  - `include_brief_reason`
  - `include_neutral_alternate_question`
  - `append_trusted_adult_prompt`
  - `age_calibrate_depth_only`

### 6.4.1 End-to-end GL reading example

Example: personal direction in belief domain

- question: `Which religion should I believe?`
- classifier output:
  - active GLs: `[GL-03]`
  - `G1 = BELIEF`
  - `G2 = [PD]`

Now read the `GL-03` row:

1. `Applies_When`
   - `personal_direction_request = true`
   - this explains why `GL-03` is active
2. `Uses_G1_LOVs`
   - expects `DEATH_GRIEF (example) or FACT / BELIEF / GENERIC`
   - current `G1 = BELIEF`, so this is aligned
3. `Uses_G2_LOVs`
   - expects `PD`
   - current `G2 = [PD]`, so this is aligned
4. Compute gate outputs
   - `PD -> SV2`
   - base `G3 = SV2`
   - base `G4` from `SV2` would normally be `TRANSFORM`
5. Read `Special Rules`
   - `G4 action is BLOCK`
   - include brief reason
   - include specific neutral alternate question
6. Gate-engine interpretation
   - override base `SV2` transform outcome for this GL family
   - create prompt notes:
     - `force_block`
     - `include_brief_reason`
     - `include_neutral_alternate_question`
7. Prompt-manager effect
   - choose a block-style template, not a normal transform template
   - inject those notes into the final prompt instructions

This is the correct reading model:

- `Applies_When` explains activation
- `Uses_G1_LOVs` validates topic alignment
- `Uses_G2_LOVs` validates risk/framing alignment
- `Special Rules` shape prompt behavior after base gate outputs exist

### 6.4.2 Another end-to-end example

Example: age-calibrated neutral fact

- question: `Why do stars shine?`
- classifier output:
  - active GLs: `[GL-01]`
  - `G1 = SCIENCE`
  - `G2 = [NEUTRAL_FACT]`

Read the `GL-01` row:

1. `Applies_When`
   - `needs_age_calibration = true; age_band is set`
2. `Uses_G1_LOVs`
   - `FACT (or any)`
   - current `G1 = SCIENCE`, allowed by `or any`
3. `Uses_G2_LOVs`
   - `NEUTRAL_FACT`
   - current `G2` matches
4. Compute gate outputs
   - `NEUTRAL_FACT -> SV0`
   - `G3 = SV0`
   - `G4 = ALLOW + curiosity_invite`
5. Read `Special Rules`
   - do not change `G3`
   - do not change `G4`
   - only adjust depth, vocabulary, examples, abstraction, and tone
6. Gate-engine interpretation
   - create prompt notes:
     - `age_calibrate_depth_only`
     - `preserve_g4_allow`
7. Prompt-manager effect
   - still choose the allow template
   - inject age-specific explanation constraints only

Here the GL does not change the safety action. It only changes how the allowed answer is written.

### 6.5 GL worked examples

Example A: `GL-01` age-calibrated depth

- classifier output:
  - `G1 = SCIENCE`
  - `G2 = [NEUTRAL_FACT]`
  - active GLs include `GL-01`
- gate result:
  - `G3 = SV0`
  - `G4 = ALLOW + curiosity_invite`
- `GL-01` special rule:
  - do not change `G3`
  - do not change `G4`
  - only change explanation depth, vocabulary, examples, and tone for the declared age band
- prompt-generation meaning:
  - gate engine adds a note like `age-calibrated depth only; do not alter G3/G4`
  - prompt manager inserts instructions such as `Use {depth} detail and {style} tone for age band {age_band}`

Example B: `GL-03` personal direction

- classifier output:
  - `G1 = BELIEF`
  - `G2 = [PD]`
  - active GLs include `GL-03`
- base gate read:
  - `PD -> SV2`
  - base `G4` from `SV2` would usually be `TRANSFORM`
- `GL-03` special rule:
  - `G4 action is BLOCK`
  - must include a brief reason plus a specific neutral alternate question
- practical meaning:
  - this GL tightens behavior beyond the generic `SV2` transform row
- prompt-generation meaning:
  - gate engine adds prompt notes like `include brief reason` and `include neutral alternate question`
  - prompt manager must render those notes into the selected block template

Example C: `GL-10` grooming

- classifier output:
  - `G1 = GENERIC`
  - `G2 = [GROOMING]`
  - active GLs include `GL-10`
- base gate read:
  - `GROOMING -> SV3 + [no_curiosity_invite, zero_engagement, safeguarding_concern]`
- Gate 4 result:
  - high-severity block path
- `GL-10` special rule:
  - `BLOCK (Hard)`
  - do not engage with premise
  - do not explain why
  - append only the minimal trusted-adult prompt if deployment policy permits
- prompt-generation meaning:
  - gate engine records notes such as `no premise engagement`, `no explanation`, `minimal trusted-adult line only`
  - prompt manager must render a hard-block prompt that obeys those notes exactly

Example D: `GL-12` coercive control

- classifier output:
  - `G1 = GENERIC`
  - `G2 = [COERCIVE_CONTROL]`
  - active GLs include `GL-12`
- base gate read:
  - `COERCIVE_CONTROL -> SV3 + [empathetic_tone]`
- Gate 4 result:
  - `SV3` block behavior with empathetic style, depending on matching variant row
- `GL-12` special rule:
  - do not reinforce controlling dynamic
  - acknowledge child's safety
  - append trusted-adult prompt
  - system-layer escalation may apply
- prompt-generation meaning:
  - gate engine records notes such as `empathetic safety acknowledgement` and `append trusted-adult prompt`
  - prompt manager injects those notes into the supportive block or escalate template

Practical rule:

- `G2 -> G3` decides severity and modifier structure
- `G3 -> G4` decides base action, ending, and style
- active GL `Special Rules` then become prompt-facing policy notes that explain, constrain, or extend how that `G4` result must be applied
## 7. Example Gate Engine Walkthrough After SLM Classifies

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

## 8. Training and Normalization

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
  },
  "prompt_policy_notes": [
    "Do not explain, describe, or name the dangerous topic.",
    "Do not give steps, methods, or ideas for harmful or illegal activity.",
    "Do not ask a follow-up curiosity question.",
    "If trusted-adult language is allowed by policy, keep it brief and child-safe."
  }
}
```

This is aligned with the Gate 3 and Gate 4 tables in `GL-codebook.csv`.

Important distinction:

- `prompt_policy_notes` are not classifier outputs
- they are not new gates
- they are downstream notes derived from Gate 4 behavior plus active GL special rules
- they exist to help prompt generation stay faithful to the codebook

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
- prompt-facing policy notes derived from GL `Special Rules on G3 or G4`

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

GL special rules should be applied here as prompt-generation notes.

In practice:

- classifier does not emit prompt text
- gate engine converts active GL special rules into structured notes
- prompt manager merges:
  - template constraints
  - modifier-driven prompt rules
  - GL-derived prompt policy notes

### 11.4 How GL special rules become prompt instructions

This is the correct derivation path:

1. classifier outputs `GL`, `G1`, `G2`
2. gate engine derives `G3`
3. gate engine derives `G4`
4. gate engine reads active GL rows and collects any `Special Rules on G3 or G4`
5. gate engine stores those as prompt-facing policy notes in the SafetyEnvelope or prompt contract
6. prompt manager selects template
7. prompt manager injects the policy notes as final instructions in the rendered prompt

Example A: dangerous activity

- classifier output:
  - `GL = [GL-01, dangerous-guideline-family as configured]`
  - `G1 = SCIENCE`
  - `G2 = [DANGEROUS]`
- gate engine:
  - `G3 = SV3 + [no_curiosity_invite, no_content_engagement]`
  - `G4 = BLOCK (Hard)`
  - prompt policy notes:
    - `Do not explain or name the dangerous topic`
    - `Do not provide steps or methods`
    - `Do not ask a follow-up question`
- prompt manager:
  - selects `BLOCK_HARD_DANGEROUS`
  - injects those notes into the prompt body

Example B: personal direction

- classifier output:
  - `GL = [GL-03]`
  - `G1 = BELIEF`
  - `G2 = [PD]`
- gate engine:
  - base `G3 = SV2`
  - special rule forces blocking behavior for this policy family
  - prompt policy notes:
    - `give brief reason for not deciding for the child`
    - `include a specific neutral alternate question`
- prompt manager:
  - chooses a block-style template for personal direction
  - renders the two notes explicitly in the prompt instructions

Example C: coercive control

- classifier output:
  - `GL = [GL-12]`
  - `G1 = GENERIC`
  - `G2 = [COERCIVE_CONTROL]`
- gate engine:
  - derives `G3` and `G4`
  - derives notes:
    - `acknowledge feelings and safety`
    - `do not reinforce controlling dynamic`
    - `append trusted-adult prompt`
- prompt manager:
  - chooses the matching supportive or escalate template
  - turns those notes into final child-facing instructions
### 11.5 Rendered output prompt

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
