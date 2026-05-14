# GL Classifier, Gate Engine, SafetyEnvelope, and Prompt Manager Reference

This document is a detailed runtime interpretation of [GL-codebook.csv](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/GL-codebook.csv) and [Contracts.csv](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/Contracts.csv). Its goal is to explain the full system flow from normalized child question through classifier output, gate-engine computation, SafetyEnvelope construction, prompt template selection, prompt-rule enforcement, checklist validation, and training-data design.

This reference follows the codebook as the source of truth and uses the current canonical runtime ids throughout.

The latest codebook revision standardizes most runtime ids to underscore form. This document follows those exact ids.

## 1. Source Of Truth And Ownership

The codebook defines the safety semantics. The contracts document defines the intended stage boundaries.

Canonical stage ownership:

1. input normalization prepares the question for classification
2. classifier assigns `G1` and one or more `G2` labels
3. age policy is appended as runtime context, not learned output
4. gate engine derives `G3` from `G2`
5. gate engine derives `G4` from `G3`
6. gate engine computes active `GL` families by reading Block E using `Applies_When`, `Uses_G1_LOVs`, and `Uses_G2_LOVs`
7. gate engine converts the matching GL special rules into structured prompt-policy notes
8. SafetyEnvelope packages question context, gate outputs, age settings, active GLs, and prompt-policy notes
9. prompt manager selects a template and renders the final LLM prompt
10. prompt checklist validates the rendered prompt before any model call

Critical ownership rules:

- classifier owns `G1` and `G2`
- gate engine owns `G3` and `G4`
- age policy appends the Block I runtime settings, including `Max_Answer_Style`, `Max_Words`, and `Depth`, without changing classifier or gate outputs
- prompt manager must not soften, reinterpret, or override gate outputs

## 2. Codebook Blocks And Their Roles

The current codebook is organized into these functional blocks:

- Block A: `G1` nature dictionary
- Block B: `G2` framing / intent / risk dictionary
- Block C: `G3` severity computation
- Block D: `G4` final action, ending, and style
- Block E: GL guideline families and special handling
- Block F: prompt authoring rules
- Block G: prompt templates for hard cases
- Block H: prompt compliance checklist
- Block I: age policy runtime settings
- Block J: intent lexicon for classifier training and support

How the blocks connect:

- Blocks A and B define what the classifier predicts
- Blocks C and D define what the gate engine computes
- Block E defines GL rule families computed by the gate engine
- Blocks F, G, and H govern prompt generation fidelity
- Block I provides age-calibration context
- Block J supports classifier training and inference for `G1` and `G2`

## 3. Canonical Runtime Vocabulary

The current system should treat these as canonical ids.

### 3.1 Canonical G1 LOV ids

- `FACT`
- `BELIEF`
- `DEATH_GRIEF`
- `SCIENCE`
- `TECHNOLOGY`
- `CIVIC_LAW`
- `GENERIC`

### 3.2 Canonical G2 LOV ids

- `NEUTRAL_FACT`
- `PERSONAL_DIRECTION`
- `HATE_GROUP`
- `DANGEROUS`
- `EMOTIONAL`
- `BULLYING`
- `GROOMING`
- `UNSAFE_SEXUAL_CONTENT`
- `COERCIVE_CONTROL`
- `VULN_EXPLOIT`
- `SELF_HARM`
- `AMBIGUOUS_RISK`
- `SAFETY_HAZARD`
- `VIOLENCE`
- `GENERIC_INTENT`

## 4. End-To-End Flow

The complete flow should be read in this order:

1. receive child question and age band
2. normalize question text and preserve raw text for audit
3. classifier assigns one `G1` and one or more `G2`
4. classifier may also emit a short internal `reason`
5. age policy settings are looked up from Block I
6. gate engine computes `G3`
7. gate engine computes `G4`
8. gate engine computes active `GL` families from Block E using the question flags plus emitted `G1` and `G2`
9. gate engine applies GL special rules as prompt-policy notes
10. SafetyEnvelope is constructed
11. prompt manager selects a template using `G4`, `G3`, and sometimes `G2`
12. prompt rules are applied as hard constraints
13. checklist validation runs
14. only validated prompt is sent to the LLM

Important non-goals:

- the classifier does not directly decide prompt wording
- Gate 4 does not reread raw question text to invent new semantics
- prompt manager does not recompute safety

## 5. Gate 1: G1 Nature Classification

`G1` answers: what is the broad subject matter of the child’s question?

`G1` is always single-label.

The canonical `G1` ids and their definitions should be read directly from Block A of `GL-codebook.csv`. This document does not restate those values.

Rules for `G1`:

- assign exactly one `G1`
- `G1` is topic, not risk
- harmful phrasing should not be forced into `G1`; it belongs in `G2`
- if the question is about chemistry but asks how to harm someone, `G1` stays `SCIENCE` while `G2` carries danger or violence

## 6. Gate 2: G2 Framing / Intent / Risk Classification

`G2` answers: how is the question framed, and what safety-relevant pattern is present?

`G2` is multi-label.

Rules for `G2`:

- one or more labels may fire
- every matched `G2` must be forwarded to Gate 3
- no matched `G2` may be silently dropped before aggregation
- `G2` is the main source of safety semantics

### 6.1 G2 source-of-truth rule

The canonical `G2` ids, their definitions, severity floors, and modifier tags should be read directly from Block B of `GL-codebook.csv`. This document does not restate those values. The runtime concern here is only how the classifier emits `G2`, how multiple `G2` labels coexist, and how Gate 3 consumes the resulting rows.

### 6.2 G2 multi-label rules

Examples of valid multi-label outcomes:

- `BULLYING + EMOTIONAL`
- `DEATH_GRIEF` in `G1` with `EMOTIONAL` or `SELF_HARM` in `G2`
- `BELIEF` in `G1` with `PERSONAL_DIRECTION`
- safeguarding-related combinations such as `GROOMING + VULN_EXPLOIT` where supported by classifier behavior

Important rule:

- multi-label `G2` means the system must aggregate all matching severity floors and all matching modifiers

## 7. Gate 3 Aggregation Contract

Gate 3 is where the codebook becomes mechanically strict. Gate 3 does not invent new LOVs, and it does not reread the question for meaning. It aggregates the Gate 2 outputs into one instruction packet for Gate 4.

`G3` contains:

- `G3_SV`
- `G3_MOD`
- `source_g2`

### 7.1 Exact Gate 3 rules

`G3_SV (Severity)`:

- rule: `MAX(severity floor of all active G2 LOVs)`
- implication: a single `SV3` label makes the entire query `SV3`
- implication: severity only moves upward, never downward

`G3_MOD (Modifier Packet)`:

- rule: `UNION(all modifier tags from all active G2 LOVs, deduplicated)`
- implication: every unique modifier from every active `G2` must be kept
- implication: order does not matter
- implication: there is no modifier priority inside `G3_MOD`

`G3_FORWARD`:

- rule: forward the exact pair `(G3_SV, G3_MOD)` to Gate 4
- implication: Gate 4 must consume the Gate 3 packet
- implication: Gate 4 should not recompute severity from `G2`
- implication: Gate 4 should not ignore modifiers that survived aggregation

### 7.2 Gate 3 worked examples

Example A:

- `G2 = [DANGEROUS, GROOMING]`
- `DANGEROUS -> SV3 + [no_curiosity_invite, no_content_engagement]`
- `GROOMING -> SV3 + [no_curiosity_invite, zero_engagement, safeguarding_concern]`
- `G3_SV = SV3`
- `G3_MOD = {no_curiosity_invite, no_content_engagement, zero_engagement, safeguarding_concern}`
- `G3_FORWARD = (SV3, {no_curiosity_invite, no_content_engagement, zero_engagement, safeguarding_concern})`

Example B:

- `G2 = [EMOTIONAL, BULLYING]`
- `EMOTIONAL -> SV2 + [empathetic_tone, emotional_support_required]`
- `BULLYING -> SV2 + [empathetic_tone, no_curiosity_invite]`
- `G3_SV = SV2`
- `G3_MOD = {empathetic_tone, emotional_support_required, no_curiosity_invite}`
- `G3_FORWARD = (SV2, {empathetic_tone, emotional_support_required, no_curiosity_invite})`

Example C:

- `G2 = [SAFETY_HAZARD]`
- `SAFETY_HAZARD -> SV2 + [clarification_required]`
- `G3_SV = SV2`
- `G3_MOD = {clarification_required}`
- `G3_FORWARD = (SV2, {clarification_required})`

### 7.3 Gate 3 invariants

These rules must hold in code and tests:

- `G3_SV` is computed only from active `G2`
- `G3_MOD` is computed only from active `G2`
- deduplication of modifiers must happen before Gate 4
- missing modifiers are a correctness bug
- lowering severity because another `G2` is milder is a correctness bug
- resolving conflicts between modifiers inside Gate 3 is a correctness bug; Gate 3 only aggregates

## 8. Gate 4 Decision Contract

Gate 4 reads the Gate 3 packet and decides final action, ending, and style.

`G4` contains:

- `action`
- `ending`
- `style`

### 8.1 Exact Gate 4 reading order

Gate 4 must execute in this order:

1. read `G3_SV`
2. select the base severity row
3. inspect `G3_MOD`
4. if a modifier-specific row exists for that severity, select that row
5. apply `Action`, `Base Ending`, and `Response Style`
6. then apply additive modifiers such as `safeguarding_concern`
7. only after base Gate 4 resolution should GL special rules further constrain or extend prompt behavior

### 8.2 Base Gate 4 rows

Base meaning from the codebook:

- `SV0`
  - action: `ALLOW`
  - ending: `curiosity_invite`
  - style: neutral, age-calibrated

- `SV1`
  - action: `TRANSFORM`
  - ending: `curiosity_invite`
  - style: neutral, balanced

- `SV2`
  - action: `TRANSFORM`
  - ending: `curiosity_invite`
  - style: neutral, balanced

- `SV3`
  - action: `BLOCK`
  - ending: `neutral_alternate_question`
  - style: neutral

### 8.3 Gate 4 variant rows

This section is reference-only and should be read as example lookup patterns for how Gate 4 variant matching works. The actual variant rows, action ids, endings, and styles must always be taken directly from Block D of `GL-codebook.csv`.

Reference examples:

- `SV1 + no_curiosity_invite`
  - action: `TRANSFORM`
  - ending: none
  - style: neutral, balanced

- `SV2 + empathetic_tone + emotional_support_required`
  - action: `TRANSFORM`
  - ending: `curiosity_invite` or omitted if distress is high
  - style: empathetic, warm

- `SV2 + redirect_preferred`
  - action: `TRANSFORM`
  - ending: `neutral_redirect`
  - style: neutral, supportive

- `SV2 + clarification_required`
  - action: `TRANSFORM_HOLD`
  - ending: `safe_disambiguation_question`
  - style: neutral
  - process meaning: turn 1 must contain exactly one safe clarification question and nothing else substantive

- `SV2 + escalate + empathetic_tone`
  - action: `TRANSFORM_ESCALATE`
  - ending: `curiosity_invite`
  - style: empathetic

- `SV3 + empathetic_tone + no_curiosity_invite`
  - action: `BLOCK`
  - ending: none
  - style: empathetic

- `SV3 + zero_engagement + no_curiosity_invite + no_content_engagement`
  - action: `BLOCK_HARD`
  - ending: none
  - style: none / minimal
  - process meaning: no topic engagement, no reason, no alternate question

- `SV3 + escalate + empathetic_tone + no_curiosity_invite`
  - action: `BLOCK_ESCALATE`
  - ending: none
  - style: empathetic

- `ANY + safeguarding_concern`
  - additive behavior, not a replacement row
  - append `trusted_adult_prompt` after inherited ending behavior

### 8.4 Gate 4 invariants

- Gate 4 must always start from `G3_SV`
- Gate 4 must always inspect `G3_MOD`
- Gate 4 must not ignore a matching modifier-specific row
- additive modifiers must be applied after base row selection
- `clarification_required` is a process gate, not only a style hint
- `no_content_engagement` is a hard prohibition on topic engagement
- `no_curiosity_invite` suppresses ending questions even if a lower-severity base row normally allows one

## 9. Classifier Notes And Modifier Handling

The codebook is the source of truth for modifier tags and their meanings. This document does not redefine them.

What matters here at runtime is:

- classifiers emit `G2`
- each `G2` row in Block B carries classifier-facing guidance in `Notes for Classifier`
- each `G2` row also carries modifier tags that Gate 3 must aggregate without reinterpretation

### 9.1 How to use `Notes for Classifier`

`Notes for Classifier` in Block A and Block B are important because they provide classifier-directional guidance that is not the same thing as gate computation.

These notes should be used for:

- training-data authoring
  - to shape positive examples, near-boundary examples, and hard negatives

- inference-time rationale support
  - to explain why a given `G1` or `G2` was selected

- threshold tuning
  - to understand which signals are strong matches versus soft contextual hints

- ambiguity handling
  - to identify cases that should co-fire multiple labels or move toward clarification paths

- review and QA
  - to evaluate whether classifier output is consistent with the intended policy family

### 9.2 What `Notes for Classifier` should not do

`Notes for Classifier` should not be treated as:

- a replacement for the codebook row values
- a replacement for semantic classification
- a hard-coded keyword list that bypasses model interpretation
- a second gate engine

### 9.3 Modifier handling rule

Modifier tags are not interpreted by the classifier as free-form prose. The classifier’s job is to emit `G2`. Gate 3 then receives the modifier tags indirectly through the matched Block B rows.

The handling rule is:

1. classifier emits `G2`
2. runtime looks up the matched `G2` rows in Block B
3. Gate 3 aggregates the row-provided severity floors and modifier tags
4. Gate 4 consumes the aggregated packet

So the classifier should learn toward the correct `G2` rows, while the gate engine remains the only component that computes modifier packets.

## 10. GL Guideline Family Contract

Block E is now gate-engine logic, not classifier output. GLs are computed after `G1`, `G2`, `G3`, and base `G4` are available.

Important interpretation rule:

- GLs do not replace `G2 -> G3 -> G4`
- GLs are computed by the gate engine
- GLs refine or constrain how base `G4` is applied

### 10.1 Current GL rows

Current Block E rows in the codebook:

- `GL-C1`: Comparative Harmful Choice Detector
- `GL-L1`: Loaded / Biased Premise Enforcer
- `GL-N1`: Negative / Abusive Language Enforcer
- `GL-V1`: Vulnerability Exploitation Escalation

### 10.2 How to read one GL row

Read GL rows in this order:

1. `Applies_When`
2. `Uses_G1_LOVs`
3. `Uses_G2_LOVs`
4. `Special Rules on G3 or G4`

Interpretation:

- `Applies_When` is the trigger logic
- `Uses_G1_LOVs` is the expected topic shape
- `Uses_G2_LOVs` is the expected framing shape
- `Special Rules` tell the gate engine what to override, append, or enforce

### 10.3 GL runtime procedure

Recommended runtime procedure:

1. classifier emits `G1` and `G2`
2. gate engine computes base `G3`
3. gate engine computes base `G4`
4. gate engine evaluates each GL row’s `Applies_When` flags
5. gate engine checks whether current `G1` and `G2` match `Uses_G1_LOVs` and `Uses_G2_LOVs`
6. if the row is active and coherent, the gate engine marks that `GL` as active
7. gate engine applies that GL row’s `Special Rules` as prompt-policy notes or explicit gate constraints

GL rows do not directly render prompt text. They produce structured policy behavior that the prompt manager later enforces.

### 10.4 Gate-engine example for GL computation

Question:

- `Which is better for hurting someone, a brick or a stick?`

Assumed upstream inputs into the gate engine:

- question text
- flag object derived from `Applies_When` feature extraction
- `G1`
- `G2`

Example classifier output:

- `G1 = GENERIC`
- `G2 = [DANGEROUS, VIOLENCE]`

Example `Applies_When` flags passed to the gate engine:

```json
{
  "has_harmful_comparison": true,
  "has_loaded_premise": false,
  "has_negative_language": false,
  "has_vuln_exploitation": false,
  "has_blackmail_pattern": false,
  "has_dependency_pattern": false
}
```

Gate-engine reading flow:

1. Gate 3 computes `G3`
   - `DANGEROUS -> SV3 + [no_curiosity_invite, no_content_engagement]`
   - `VIOLENCE -> SV3 + [no_curiosity_invite, flag_for_review]`
   - `G3_SV = SV3`
   - `G3_MOD = {no_curiosity_invite, no_content_engagement, flag_for_review}`

2. Gate 4 computes base `G4`
   - base result follows the `SV3` path
   - because `no_content_engagement` is present, the strict block profile is selected

3. Gate engine evaluates Block E
   - `GL-C1` checks `Applies_When`
   - `has_harmful_comparison = true`, so trigger condition is satisfied
   - `Uses_G2_LOVs` expects one of `DANGEROUS, VIOLENCE, SELF_HARM, HATE_GROUP, UNSAFE_SEXUAL_CONTENT, GROOMING`
   - current `G2` includes `DANGEROUS` and `VIOLENCE`, so the row is coherent
   - `GL-C1` becomes active

4. Gate engine applies `GL-C1` special rules
   - do not choose or rank harmful options
   - force `no_curiosity_invite` if not already present
   - force `BLOCK` or safety-only transform depending on the harmful class
   - require prompt instructions that forbid comparative ranking language

Result:

- active GLs: `[GL-C1]`
- `G3` remains the same severity packet
- `G4` remains on the strict safe path
- additional prompt-policy notes are attached so the prompt cannot compare the harmful options

### 10.5 Why gate-engine GL computation helps

This model is useful because:

- classifier training stays focused on `G1` and `G2`
- GL logic stays transparent and configurable in the codebook
- the system can evolve GL behavior without retraining the classifier every time
- `Applies_When` flags make policy triggers inspectable and testable

## 11. How Classifier Output And Gate-Engine Computation Work During Inference

This section explains how the system should compute classifier outputs and then let the gate engine compute `G3`, `G4`, and `GL`.

### 11.1 Inference objective

At inference time, the system is trying to answer two classifier questions and then hand off to the gate engine:

1. what is the question broadly about
2. how is the question framed and what risk pattern is present

These map to:

- `G1`: broad topic
- `G2`: framing / risk

What the gate engine then computes:

- `G3`: aggregated severity + modifiers
- `G4`: final action, ending, style
- `GL`: active guideline families and special handling

### 11.2 Recommended inference order

The most stable runtime order is:

1. normalize raw question text
2. run semantic classification for `G1`
3. run semantic multi-label classification for `G2`
4. pass question text, flag object, `G1`, and `G2` into the gate engine
5. gate engine aggregates `G2` into `G3`
6. gate engine derives `G4` from `G3`
7. gate engine computes active `GL` rows using `Applies_When`, `Uses_G1_LOVs`, and `Uses_G2_LOVs`
8. gate engine applies GL special rules as structured notes or overrides where the codebook requires them
9. package the result into the SafetyEnvelope

Why this order matters:

- `G1` and `G2` are the core classifier outputs
- `G3` must be computed from `G2`, not from raw text
- `G4` must be computed from `G3`, not directly from raw text
- `GL` is computed inside the gate engine, not inside classifier inference

### 11.3 How G1 is computed during inference

`G1` should be computed as a single-label topic classification.

Recommended signals:

- semantic meaning of the question
- Block A definitions
- soft lexical support from characteristic patterns

Examples:

- `Why do stars shine?`
  - likely `G1 = SCIENCE`

- `What is a visa?`
  - likely `G1 = FACT` or `GENERIC` depending on classifier policy

- `How can I cheat on a school exam?`
  - likely `G1 = CIVIC_LAW`

Important rule:

- `G1` should stay topical even when `G2` becomes severe
- do not turn topic classification into a risk label

### 11.4 How G2 is computed during inference

`G2` should be computed as multi-label semantic classification.

Recommended inputs:

- normalized question text
- Block B operational definitions
- Block J intent families and phrase evidence
- optional recent context if product policy allows it

Recommended decision pattern:

1. produce candidate `G2` scores from the classifier
2. use Block J evidence to support, explain, or disambiguate candidates
3. apply class thresholds
4. allow multi-label outputs where justified
5. apply boundary-resolution rules for confusing pairs

Examples:

- `Kids keep calling me names and I feel terrible`
  - likely `G2 = [BULLYING, EMOTIONAL]`

- `Should I do what this adult says even though I am scared?`
  - likely `G2 = [PERSONAL_DIRECTION, COERCIVE_CONTROL]`

- `How do I get into the locked building?`
  - likely `G2 = [AMBIGUOUS_RISK]`

- `How do I break in without getting caught?`
  - likely `G2 = [DANGEROUS]`

### 11.5 How GL is computed in the gate engine

`GL` is no longer a classifier target in this design. It is computed in the gate engine.

Inputs to GL computation:

- question text or normalized question text
- `Applies_When` flags passed alongside the question
- classifier-produced `G1`
- classifier-produced `G2`
- base `G3` and `G4` already available for rule application

Recommended practical approach:

1. create a flag object for the `Applies_When` conditions
2. for each Block E row, test whether the trigger is satisfied
3. verify that current `G1` matches `Uses_G1_LOVs` where applicable
4. verify that current `G2` matches `Uses_G2_LOVs`
5. if both trigger and coherence checks pass, activate the GL row
6. apply its `Special Rules on G3 or G4`

Important rule:

- `GL` must be derived from the gate-engine reading process
- if a trigger is true but `G1`/`G2` are incoherent with the row, the system should log or review the mismatch rather than silently force the row

### 11.6 Why GL is helpful

The gates alone tell the system what severity and action to take, but `GL` adds policy meaning that the gates do not fully express by themselves.

`GL` is helpful for five reasons:

- policy-family explanation
  - `GL` explains what kind of policy situation was detected, not just its severity

- better prompt constraints
  - two cases may both end at `SV3`, but the required child-facing behavior differs
  - example: grooming and unsafe sexual content are both severe, but their allowed response patterns differ

- auditability
  - `GL` makes it easier to explain why a certain pathway was chosen
  - example: `GL-N1` explains why a severe response must also avoid repeating abusive language

- analytics and tuning
  - product and safety teams can measure policy-family distribution separately from generic severity
  - this is useful for monitoring drift, coverage, and false positives

- policy modularity
  - because GL lives in gate-engine logic, policy families can change without forcing every change through classifier retraining

### 11.7 How GL and gates work together

The cleanest interpretation is:

- `G1` tells you the subject area
- `G2` tells you the operative framing and risk pattern
- `G3` compresses all `G2` outputs into one severity/modifier packet
- `G4` determines the base response action
- `GL` tells you which policy-family notes must still be respected on top of that base action

This means:

- the gates provide deterministic mechanics
- `GL` provides policy semantics and downstream constraints

### 11.8 Detailed inference example

Question:

- `Someone says this group is disgusting and we should get rid of them`

Step 1. Normalize input

- raw text is preserved
- normalized text may collapse spacing, punctuation noise, and casing

Step 2. Compute `G1`

- broad topic is generic social / identity language
- result: `G1 = GENERIC`

Step 3. Compute candidate `G2`

- hateful protected-group language supports `HATE_GROUP`
- final result: `G2 = [HATE_GROUP]`

Step 4. Compute `G3`

- `HATE_GROUP -> SV3 + [no_curiosity_invite, flag_for_review]`
- `G3_SV = SV3`
- `G3_MOD = {no_curiosity_invite, flag_for_review}`
- `G3_FORWARD = (SV3, {no_curiosity_invite, flag_for_review})`

Step 5. Compute base `G4`

- base `SV3` row gives block behavior

Step 6. Build gate-engine flags for Block E

```json
{
  "has_negative_language": true,
  "is_protected_group_target": true,
  "includes_slurs": false,
  "has_loaded_premise": false,
  "has_harmful_comparison": false,
  "has_vuln_exploitation": false,
  "has_blackmail_pattern": false,
  "has_dependency_pattern": false
}
```

Step 7. Compute active `GL`

- `GL-N1` trigger is satisfied because `has_negative_language = true`
- `Uses_G2_LOVs` is coherent because `G2` includes `HATE_GROUP`
- result: `GL = [GL-N1]`

Step 8. Apply `GL` special rules

- do not repeat abusive language in the model’s own voice
- ensure `flag_for_review` stays present
- enforce reframing or blocking without endorsing the wording

Step 9. Build SafetyEnvelope

- include question, age context, `GL`, `G1`, `G2`, `G3`, `G4`, and policy notes

Step 10. Prompt manager selection

- prompt manager should not render the abusive wording neutrally
- it must render the response using the block result plus the `GL-N1` note that abusive language must not be repeated

Why `GL` helped here:

- base `SV3` block severity alone does not tell the system how to treat hateful wording in the response
- `GL-N1` adds the rule that abusive language must not be repeated or normalized

### 11.9 Detailed safeguarding example

Question:

- `An older person online gives me gifts and says not to tell my parents`

Inference path:

- `G1 = GENERIC`
- `G2 = [GROOMING]`
- `G3 = SV3 + {no_curiosity_invite, zero_engagement, safeguarding_concern}`
- base `G4` resolves on the severe block path
- additive `safeguarding_concern` appends trusted-adult behavior
- gate-engine flags may activate `GL-V1` if the exploitation pattern criteria are met
- if `GL-V1` is active, the gate engine additionally forces `escalate` and preserves the safeguarding pathway

Why `GL` helped here:

- `SV3` alone only says the case is severe
- `GL-V1` can add escalation behavior when exploitation-specific trigger conditions are satisfied
- that matters because not every severe case requires the same downstream handling

### 11.10 Inference invariants

The following rules should always hold:

- `G1` is single-label
- `G2` may be multi-label
- `GL` may be multi-label
- `G3` is computed only from active `G2`
- `G4` is computed from `G3`
- `GL` is computed by the gate engine after `G3` and `G4`
- `GL` may refine or constrain the application of `G4`, but it should not bypass the existence of the gate flow
- inconsistent `GL`/`G2` combinations should be logged for review

## 12. Prompt Rule Contract

Prompt rules from Block F are non-negotiable instructions for prompt generation.

### 12.1 PR-01 Gate Fidelity

- every prompt must reflect `G4 Action`, `Base Ending`, and `Response Style`
- do not soften block behavior
- do not omit active modifiers
- do not paraphrase a hard block into a soft redirect

### 12.2 PR-02 clarification_required = HOLD

- if `clarification_required` is present, turn 1 must contain exactly one safe clarification question
- no answer
- no topic information
- no redirect
- no explanation

### 12.3 PR-03 no_content_engagement = Absolute Silence On Topic

- if `no_content_engagement` is present, the prompt must forbid topic explanation, reason-giving, or redirect question
- if output text is allowed at all, it must be minimal and pre-approved

### 12.4 PR-04 no_curiosity_invite = Suppress Ending Question

- if `no_curiosity_invite` is present, prompt must not end with any question
- no follow-up invitation
- final sentence must be a statement

### 12.5 PR-05 Age Band And Length Constraint Are Mandatory

- prompt header must include age band
- prompt must include explicit line or length cap
- prompt must instruct the model to match vocabulary, tone, and abstraction to the age band
- age calibration must not change `G3` or `G4`

## 13. Prompt Template Contract

Block G gives explicit hard-case templates. These are not generic examples. They are approved template shapes for difficult cases.

### 13.1 HBT-01 Dangerous hard block

Applies when:

- `G2 = DANGEROUS`
- `G3_MOD includes no_content_engagement`
- `G4 = BLOCK_HARD`

Required behavior:

- do not explain mechanism
- do not name the dangerous topic
- do not ask a redirect question
- end with brief trusted-adult or grown-up referral only if that policy is permitted for the case

### 13.2 HBT-02 Ambiguous-risk clarification hold

Applies when:

- `G2 = AMBIGUOUS_RISK`
- `G3_MOD includes clarification_required`
- `G4 = TRANSFORM_HOLD`

Required behavior:

- exactly one clarification question
- one sentence only
- no content answer
- no redirect
- no topic explanation

## 14. Prompt Checklist Contract

The checklist is the pre-send validation gate.

Current checklist logic from Block H:

- `CHK-01`
  - age band must be present in prompt header

- `CHK-02`
  - `G1`, `G2`, `G3`, `G4` must be present in prompt header

- `CHK-03`
  - explicit line or word limit must be present

- `CHK-04`
  - if `clarification_required`, turn 1 must contain only the clarification question

- `CHK-05`
  - if `no_content_engagement`, prompt must contain no topic content or redirect question

- `CHK-06`
  - if `no_curiosity_invite`, prompt must end without a question

- `CHK-07`
  - prompt body behavior must match `G4.action`

- `CHK-08`
  - prompt must introduce no unsupported content, framing, caveats, or encouragements

Operational rule:

- if any checklist item fails, do not call the LLM
- re-render or fall back to a known-good safe template

## 15. Age Policy Runtime Contract

Age policy comes from Block I and is runtime context, not learned behavior.

The age-band values and their `Max_Answer_Style`, `Max_Words`, and `Depth` settings should be read directly from Block I of `GL-codebook.csv`. This document does not restate those values.

Rules:

- age policy must be looked up after classification or in parallel as context
- age policy must not mutate `G1`, `G2`, `G3`, or `G4`
- age policy appends the Block I runtime settings, including answer style, word budget, and depth controls, for downstream prompt rendering

## 16. Block J Intent Lexicon Contract

Block J is the classifier intent lexicon. It supports how the classifier learns and predicts `G1` and `G2`.

### 16.1 Purpose

Block J defines:

- intent families per LOV
- example phrase patterns per LOV
- training anchors for dataset generation
- runtime evidence cues for classifier rationale across `G1` and `G2`

Block J does not define:

- severity
- modifier output
- final action
- prompt behavior

Those remain in Blocks A through D.

### 16.2 How Block J maps to classification

Block J should be used as classifier support for the classifier stage, especially `G2`, and as a supporting aid for `G1`.

Recommended reading:

- Block A defines `G1`
- Block B defines `G2`
- Block E defines gate-engine GL families and trigger expectations
- Block J provides linguistic families and phrase anchors that help train or support classifier outputs

Operationally:

- `G1` classification uses Block A definitions, classifier notes, and supporting lexicon-style evidence where available
- `G2` classification uses Block B definitions, classifier notes, and Block J intent families
Reference examples from Block J:

- `NEUTRAL_FACT`
  - families: `factual_definition`, `mechanism_explanation`, `neutral_history_or_civics`
  - example phrases: `what is`, `how does X work`, `who is`

- `COMPARATIVE`
  - families: `belief_ranking`, `group_comparison`, `right_wrong_belief`
  - example phrases: `which is better`, `which is right`

- `PERSONAL_DIRECTION`
  - families: `what_should_I_do`, `personal_choice`, `life_decision`
  - example phrases: `should I`, `tell me what to choose`

- `DANGEROUS`
  - families: `weapon_making`, `sabotage_or_evasion`, `bypass_security_or_law`
  - example phrases: `how do I make a bomb`, `how to hack`, `how to avoid getting caught`

- `AMBIGUOUS_RISK`
  - families: `dual_use_tools`, `access_or_location_questions`, `vague_preparation_or_planning`
  - example phrases: `where can I buy a knife`, `what chemicals are easy to get`

- `SAFETY_HAZARD`
  - families: `dangerous_experiment`, `accidental_risk`, `exposure_to_hazardous_substances_or_forces`
  - example phrases: `mix random chemicals`, `is it safe to breathe fumes`

### 16.3 How Block J should be used in training

Recommended use:

1. use Block J phrases as seed examples
2. expand each seed into paraphrases, child-language variants, misspellings, slang, and indirect formulations
3. add hard negatives near class boundaries
4. add multi-label examples
5. train the classifier to predict `G1` and `G2` as semantic labels, not just phrase hits

Block J should support:

- data generation
- class balancing
- rationale generation
- threshold tuning
- confusion analysis

### 16.4 How Block J should be used at inference

Recommended inference role:

- semantic model predicts candidate `G1` and `G2` outputs
- lexicon matches provide supporting evidence, ambiguity alerts, and rationale hooks
- final outputs are resolved with thresholds and multi-label logic

Important rule:

- Block J must not become a pure keyword system

Why:

- vocabulary overlap exists across safe and unsafe questions
- children paraphrase unpredictably
- intent is often implied rather than literally stated

### 16.5 Critical boundaries the classifier must learn

Important class boundaries:

- `NEUTRAL_FACT` vs `GENERIC_INTENT`
- `PERSONAL_DIRECTION` vs `GENERIC_INTENT`
- `EMOTIONAL` vs `SELF_HARM`
- `AMBIGUOUS_RISK` vs `DANGEROUS`
- `SAFETY_HAZARD` vs `DANGEROUS`
- `VIOLENCE` vs `DANGEROUS`
- `BULLYING` vs `HATE_GROUP`

Boundary examples:

- `What is a knife?`
  - likely `NEUTRAL_FACT`

- `Where can I buy a knife?`
  - likely `AMBIGUOUS_RISK`

- `What is the best knife to scare someone with?`
  - likely `VIOLENCE`

- `How do I make a knife trap?`
  - likely `DANGEROUS`

## 17. Recommended Training Data Schema

For better accuracy, the training data should be richer than only `question_text` plus one label. It should reflect the current classifier targets (`G1` and `G2`), the gate model, the intent lexicon, multi-label behavior, and audit needs. `GL` is not a direct training target in this design.

### 17.1 Minimum recommended training record

```json
{
  "schema_version": "2.0.0",
  "sample_id": "uuid",
  "split": "train",
  "language": "en",
  "source": "synthetic|human_review|redteam|production_correction",
  "question_text_raw": "Should I do what this adult says even though I am scared?",
  "question_text_normalized": "Should I do what this adult says even though I am scared?",
  "age_band": "9-10",
  "g1": "GENERIC",
  "g2": ["PERSONAL_DIRECTION", "COERCIVE_CONTROL"],
  "intent_families": ["what_should_I_do", "threats_and_punishment"],
  "lexicon_evidence": ["should I", "I am scared"],
  "severity_floor_max": "SV3",
  "expected_g3_modifiers": ["empathetic_tone"],
  "rationale": "The question asks for personal direction while also indicating fear-based control.",
  "review_status": "approved"
}
```

### 17.2 Recommended full training schema

```json
{
  "schema_version": "2.0.0",
  "sample_id": "uuid",
  "parent_sample_id": null,
  "split": "train|validation|test",
  "group_id": "paraphrase-cluster-id",
  "language": "en",
  "locale": "global",
  "source": "synthetic|human_review|redteam|production_correction|expert_authored",
  "difficulty": "easy|medium|hard|adversarial",
  "question_text_raw": "How can I hurt myself without anyone knowing?",
  "question_text_normalized": "How can I hurt myself without anyone knowing?",
  "normalization_notes": [],
  "age_band": "13-14",
  "g1": "GENERIC",
  "g2": ["SELF_HARM"],
  "intent_families": ["suicidal_ideation", "non_suicidal_self_injury"],
  "lexicon_evidence": ["hurt myself"],
  "severity_floor_per_g2": {
    "SELF_HARM": "SV3"
  },
  "expected_g3": {
    "severity": "SV3",
    "modifiers": ["no_curiosity_invite", "empathetic_tone"],
    "source_g2": ["SELF_HARM"]
  },
  "expected_g4": {
    "action": "BLOCK",
    "ending": "(none)",
    "style": "Empathetic"
  },
  "rationale": "The question explicitly asks for self-harm assistance.",
  "boundary_notes": ["self_harm_vs_emotional"],
  "safety_notes": ["high_priority"],
  "labeler_id": "expert-01",
  "review_status": "approved",
  "created_at": "2026-05-13"
}
```

### 17.3 Recommended dataset design rules

- store both raw and normalized text
- store multi-label `g2` as an array, never as a comma-separated string
- store `intent_families` separately from `g2`
- include `expected_g3` and `expected_g4` for evaluation and consistency checks
- cluster paraphrases with `group_id` so near-duplicates stay in one split
- track source type so synthetic and real-world data can be measured separately
- track `boundary_notes` for hard confusion classes

### 17.4 Recommended example coverage

Every `G2` should have:

- direct phrase matches from Block J
- paraphrases with no literal phrase overlap
- short questions
- long questions
- misspellings
- child-like wording
- indirect wording
- adversarial wording
- benign near-neighbors
- harmful near-neighbors
- multi-label compositions

### 17.5 Recommended evaluation metrics

For better accuracy, do not rely only on overall accuracy.

Track:

- `G1` accuracy
- `G2` micro-F1
- `G2` macro-F1
- exact-match rate for multi-label `G2`
- confusion pairs for key boundaries
- `G3` severity accuracy
- `G3` modifier exact-match accuracy
- `G4` action accuracy
- false-negative rate on `SV3` classes
- false-positive rate on benign `NEUTRAL_FACT` examples

## 18. Recommended Runtime Schemas

### 18.1 Classifier output schema

```json
{
  "schema_version": "2.0.0",
  "question_id": "uuid-or-hash",
  "question_text_raw": "Someone says this group is disgusting and we should get rid of them",
  "question_text_normalized": "Someone says this group is disgusting and we should get rid of them",
  "language": "en",
  "age_band": "9-10",
  "reason": "The question contains hateful language targeting a protected group.",
  "g1": {
    "id": "GENERIC"
  },
  "g2": [
    {
      "id": "HATE_GROUP",
      "rationale": "The question uses hateful protected-group language."
    }
  ]
}
```

### 18.2 Gate engine output schema

```json
{
  "g3": {
    "severity": "SV3",
    "modifiers": ["no_curiosity_invite", "flag_for_review"],
    "source_g2": ["HATE_GROUP"]
  },
  "g4": {
    "action": "BLOCK",
    "ending": "(none)",
    "style": "Empathetic or Neutral, depending on matched Gate 4 row"
  },
  "gl": {
    "active": ["GL-N1"]
  },
  "prompt_policy_notes": [
    "Do not repeat abusive language in the model's own voice.",
    "Preserve review signaling for hateful language.",
    "Do not normalize or endorse the abusive framing."
  ]
}
```

### 18.3 SafetyEnvelope schema

```json
{
  "schema_version": "2.0.0",
  "question": {
    "id": "uuid-or-hash",
    "raw_text": "Someone says this group is disgusting and we should get rid of them",
    "normalized_text": "Someone says this group is disgusting and we should get rid of them",
    "language": "en"
  },
  "user_context": {
    "age_band": "9-10",
    "age_settings": {
      "max_words": 130,
      "depth": "BASIC_REASONING",
      "style": "Clear, cause-effect, brief steps"
    }
  },
  "g1": {
    "id": "GENERIC"
  },
  "g2": {
    "active_lovs": [
      {
        "id": "HATE_GROUP"
      }
    ]
  },
  "g3": {
    "severity": "SV3",
    "modifiers": ["no_curiosity_invite", "flag_for_review"],
    "source_g2": ["HATE_GROUP"]
  },
  "g4": {
    "action": "BLOCK",
    "base_ending": "(none)",
    "style": "Empathetic or Neutral, depending on matched Gate 4 row"
  },
  "gl": {
    "active": ["GL-N1"],
    "notes": "Negative or abusive language enforcer is active."
  },
  "prompt_policy_notes": [
    "Do not repeat abusive language in the model's own voice.",
    "Preserve review signaling for hateful language.",
    "Do not normalize or endorse the abusive framing."
  ]
}
```

## 19. Prompt Manager Runtime Contract

The prompt manager consumes the SafetyEnvelope, not the raw question alone.

Required prompt-manager inputs:

- normalized question text
- raw question text if needed for audit or quoted prompt context
- age band and age settings
- active `GL`
- `G1`
- active `G2`
- `G3`
- `G4`
- prompt-policy notes

Prompt manager procedure:

1. select matching template from `G4`, `G3`, and sometimes `G2`
2. inject header values
3. inject age settings
4. apply prompt rules
5. run checklist
6. emit final prompt only if checklist passes

Representative matching examples:

- `ALLOW_NEUTRAL_FACT`
  - match: `G4=ALLOW`, `G3=SV0`, `G2 includes NEUTRAL_FACT`

- dangerous hard block
  - match: `G4=BLOCK_HARD`, `G2 includes DANGEROUS`, `G3_MOD includes no_content_engagement`

- clarification hold
  - match: `G4=TRANSFORM_HOLD`, `G2 includes AMBIGUOUS_RISK`, `G3_MOD includes clarification_required`

## 20. Implementation And Test Priorities

To keep the system faithful to the codebook, tests should verify:

- canonical label normalization
- `G2` multi-label aggregation
- `G3_SV = MAX(...)`
- `G3_MOD = UNION(...)`
- `G3_FORWARD` packet fidelity
- Gate 4 base-row selection
- Gate 4 variant-row selection
- additive `safeguarding_concern`
- `clarification_required` hold behavior
- `no_content_engagement` suppression behavior
- template-to-gate fidelity
- checklist failure on unsupported prompt content

## 21. Final Alignment Summary

The correct complete reading of the codebook is:

- `G1` is topic
- `G2` is framing / risk and may be multi-label
- Gate 3 aggregates all `G2` outputs into a strict instruction packet
- Gate 4 reads that packet to choose action, ending, and style
- GL rows constrain how some gate results must be applied
- age policy adjusts response depth, not safety severity
- Block J supports classifier training and inference for `G2`
- SafetyEnvelope is the contract boundary into prompt rendering
- prompt manager must be gate-faithful
- prompt checklist is the final pre-send safety verifier

If `GL-codebook.csv` changes, this document must be updated for:

- LOV ids
- severity floors
- modifier names
- Gate 4 rows
- GL special rules
- age bands
- Block J intent families
