# GL Classifier, Gate Engine, SafetyEnvelope, and Prompt Manager Reference

This document is a detailed runtime interpretation of [GL-codebook.csv](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/GL-codebook.csv) and [Contracts.csv](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/Contracts.csv). Its goal is to explain the full system flow from normalized child question through classifier output, Gate 3 aggregation, Gate 4 decisioning, SafetyEnvelope construction, prompt template selection, prompt-rule enforcement, checklist validation, and training-data design.

This reference follows the codebook as the source of truth. Where the CSV contains naming inconsistencies, this document states the canonical runtime interpretation explicitly so implementation and training stay stable.

## 1. Source Of Truth And Ownership

The codebook defines the safety semantics. The contracts document defines the intended stage boundaries.

Canonical stage ownership:

1. input normalization prepares the question for classification
2. classifier assigns `G1` and one or more `G2` labels, and may also surface active GL families
3. age policy is appended as runtime context, not learned output
4. gate engine derives `G3` from `G2`
5. gate engine derives `G4` from `G3`
6. gate engine converts active GL special rules into structured prompt-policy notes
7. SafetyEnvelope packages question context, gate outputs, age settings, active GLs, and prompt-policy notes
8. prompt manager selects a template and renders the final LLM prompt
9. prompt checklist validates the rendered prompt before any model call

Critical ownership rules:

- classifier owns `G1` and `G2`
- gate engine owns `G3` and `G4`
- age policy adjusts response depth and length only
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
- Block E constrains how some gate outputs must be applied in specific policy families
- Blocks F, G, and H govern prompt generation fidelity
- Block I provides age-calibration context
- Block J supports classifier training and inference for `G2`

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
- `COMPARATIVE`
- `PERSONAL DIRECTION`
- `LOADED PREMISE`
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

### 3.3 Naming inconsistencies that must be normalized

The codebook mixes some legacy and current names. The runtime should normalize them to one canonical form.

Canonical interpretation:

- `PERSONAL DIRECTION` is the current canonical `G2` label
- `LOADED PREMISE` is the current canonical `G2` label
- `UNSAFE_SEXUAL_CONTENT` is the current canonical `G2` label

Observed legacy or inconsistent variants in the CSV or older docs:

- `PERSONAL_DIRECTION`
- `LOADED_PREMISE`
- `SEXUAL_UNSAFE_CONTENT`
- `UNSAFE_CONTENT`

Required normalization rule:

- any classifier, dataset, or config layer that still emits the legacy variants must map them into the canonical runtime ids before Gate 3 computation

## 4. End-To-End Flow

The complete flow should be read in this order:

1. receive child question and age band
2. normalize question text and preserve raw text for audit
3. classifier assigns one `G1` and one or more `G2`
4. classifier may also emit active GL families and a short internal `reason`
5. age policy settings are looked up from Block I
6. gate engine computes `G3`
7. gate engine computes `G4`
8. gate engine applies GL special rules as prompt-policy notes
9. SafetyEnvelope is constructed
10. prompt manager selects a template using `G4`, `G3`, and sometimes `G2`
11. prompt rules are applied as hard constraints
12. checklist validation runs
13. only validated prompt is sent to the LLM

Important non-goals:

- the classifier does not directly decide prompt wording
- Gate 4 does not reread raw question text to invent new semantics
- prompt manager does not recompute safety

## 5. Gate 1: G1 Nature Classification

`G1` answers: what is the broad subject matter of the child’s question?

`G1` is always single-label.

Operational meaning of each current `G1`:

- `FACT`
  - factual, descriptive, neutral world-knowledge questions
- `BELIEF`
  - religion, worldview, ideology, moral belief systems
- `DEATH_GRIEF`
  - death, loss, bereavement, dying, grief
- `SCIENCE`
  - natural science, biology, physics, chemistry, nature, body, space
- `TECHNOLOGY`
  - computing, devices, AI, internet, software, digital systems
- `CIVIC_LAW`
  - laws, rules, cheating, evasion, institutional process misuse
- `GENERIC`
  - fallback category when none of the above fit clearly

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

### 6.1 G2 meanings, severity floors, and modifiers

Current Gate 2 interpretation:

- `NEUTRAL_FACT`
  - meaning: purely factual or descriptive inquiry with no risk framing
  - severity floor: `SV0`
  - modifiers: none

- `COMPARATIVE`
  - meaning: compares or ranks beliefs / groups as better or worse
  - severity floor: `SV1`
  - modifiers: none

- `PERSONAL DIRECTION`
  - meaning: asks what the child personally should believe, choose, or do
  - severity floor: `SV2`
  - modifiers: none

- `LOADED PREMISE`
  - meaning: embeds a biased, prejudiced, or false assumption
  - severity floor: `SV1`
  - modifiers: none

- `HATE_GROUP`
  - meaning: derogatory or sweeping language about a protected group
  - severity floor: `SV3`
  - modifiers: `no_curiosity_invite`, `flag_for_review`

- `DANGEROUS`
  - meaning: requests harmful, illicit, evasive, or dangerous instructions
  - severity floor: `SV3`
  - modifiers: `no_curiosity_invite`, `no_content_engagement`

- `EMOTIONAL`
  - meaning: distress, sadness, fear, loneliness, anxiety, emotional pain
  - severity floor: `SV2`
  - modifiers: `empathetic_tone`, `emotional_support_required`

- `BULLYING`
  - meaning: peer harm, exclusion, intimidation, name-calling
  - severity floor: `SV2`
  - modifiers: `empathetic_tone`, `no_curiosity_invite`

- `GROOMING`
  - meaning: secrecy, gifts, covert adult-child manipulation, isolation requests
  - severity floor: `SV3`
  - modifiers: `no_curiosity_invite`, `zero_engagement`, `safeguarding_concern`

- `UNSAFE_SEXUAL_CONTENT`
  - meaning: explicit sexual content, CSAM-adjacent content, sexualized child content
  - severity floor: `SV3`
  - modifiers: `no_curiosity_invite`, `no_content_engagement`, `no_reason_given`, `zero_engagement`

- `COERCIVE_CONTROL`
  - meaning: fear-based control, threats, punishment, domination by authority
  - severity floor: `SV3`
  - modifiers: `empathetic_tone`

- `VULN_EXPLOIT`
  - meaning: targeted exploitation of vulnerability, blackmail, manipulative dependency
  - severity floor: `SV3`
  - modifiers: `no_curiosity_invite`, `safeguarding_concern`

- `SELF_HARM`
  - meaning: self-injury, suicidality, wanting to disappear, harm-to-self requests
  - severity floor: `SV3`
  - modifiers: `no_curiosity_invite`, `empathetic_tone`

- `AMBIGUOUS_RISK`
  - meaning: dual-use or unclear-risk query that requires clarification before any substantive answer
  - severity floor: `SV2`
  - modifiers: `clarification_required`, `no_curiosity_invite`

- `SAFETY_HAZARD`
  - meaning: hazardous experiment, dangerous physical setup, accident or exposure risk
  - severity floor: `SV2`
  - modifiers: `clarification_required`

- `VIOLENCE`
  - meaning: interpersonal harm, weapons, attacks, gang violence, terrorism, war violence
  - severity floor: `SV3`
  - modifiers: `no_curiosity_invite`, `flag_for_review`

- `GENERIC_INTENT`
  - meaning: non-risky fallback intent when no more specific `G2` applies
  - severity floor: `SV2`
  - modifiers: none

### 6.2 G2 multi-label rules

Examples of valid multi-label outcomes:

- `BULLYING + EMOTIONAL`
- `COMPARATIVE + PERSONAL DIRECTION`
- `DEATH_GRIEF` in `G1` with `EMOTIONAL` or `SELF_HARM` in `G2`
- `BELIEF` in `G1` with `LOADED PREMISE` or `HATE_GROUP` in `G2`

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

- `G2 = [COMPARATIVE, GROOMING]`
- `COMPARATIVE -> SV1 + []`
- `GROOMING -> SV3 + [no_curiosity_invite, zero_engagement, safeguarding_concern]`
- `G3_SV = MAX(SV1, SV3) = SV3`
- `G3_MOD = {no_curiosity_invite, zero_engagement, safeguarding_concern}`
- `G3_FORWARD = (SV3, {no_curiosity_invite, zero_engagement, safeguarding_concern})`

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

Modifier-driven variants from the codebook:

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
  - action: `TRANSFORM + ESCALATE`
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
  - action: `BLOCK + ESCALATE`
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

## 9. Modifier Semantics

The modifiers are not cosmetic. They are contract constraints.

Current modifier meanings:

- `no_curiosity_invite`
  - no ending question, no invitation to continue on topic

- `no_content_engagement`
  - do not explain, develop, or discuss the blocked topic

- `zero_engagement`
  - stricter than ordinary block behavior; the response may be minimal or silent on content

- `no_reason_given`
  - do not give a child-facing explanation for the refusal

- `clarification_required`
  - ask one safe clarification question only before any substantive answer

- `empathetic_tone`
  - response tone must acknowledge feelings, distress, or fear

- `emotional_support_required`
  - response must offer age-appropriate support, not just neutral information

- `flag_for_review`
  - system-side moderation or review should be triggered

- `safeguarding_concern`
  - append trusted-adult referral behavior after the selected base ending rules

- `escalate`
  - parent/guardian or system escalation occurs at system layer; do not reveal escalation to the child unless deployment policy explicitly requires it

## 10. GL Guideline Family Contract

GL rows explain policy families that may constrain or refine how the gate result is applied.

Important interpretation rule:

- GLs do not replace `G2 -> G3 -> G4`
- GLs sit on top of the gate result
- GLs are read after base Gate 4 resolution

### 10.1 Current GL family meanings

Current GL rows in the codebook:

- `GL-01`: Comparative Belief Detector
- `GL-02`: Personal Direction Detector
- `GL-03`: Loaded / Biased Premise Detector
- `GL-04`: Violence Detector
- `GL-05`: Grief / Death / Loss Detector
- `GL-06`: Negative Language / Radicalisation Detector
- `GL-07`: Grooming Detector
- `GL-08`: Unsafe Sexual Content Detector
- `GL-09`: Coercive Control Detector
- `GL-10`: Vulnerability Exploitation Detector

### 10.2 How to read one GL row

Read GL rows in this order:

1. `Applies_When`
2. `Uses_G1_LOVs`
3. `Uses_G2_LOVs`
4. `Special Rules on G3 or G4`

Interpretation:

- `Applies_When` explains why the GL is active
- `Uses_G1_LOVs` describes expected topical alignment
- `Uses_G2_LOVs` describes expected framing alignment
- `Special Rules` tell the system what extra constraints or overrides must be applied after gate computation

### 10.3 GL runtime procedure

Recommended runtime procedure:

1. classifier emits active GL family ids, `G1`, and `G2`
2. validate whether the GL is coherent with `G1` and `G2`
3. compute base `G3`
4. compute base `G4`
5. apply GL special rules as prompt-policy notes or explicit gate constraints

GL rows do not directly render prompt text. They produce structured policy meaning.

### 10.4 GL-specific rules from the codebook

`GL-01` comparative belief:

- default ending is `curiosity_invite`
- if `no_curiosity_invite` appears in `G3_MOD`, suppress curiosity invite
- if `clarification_required` appears, replace ending with one safe disambiguation question
- if `safeguarding_concern` appears, append trusted-adult prompt after existing ending

`GL-02` personal direction:

- force `G4 action = BLOCK`
- include brief reason
- include specific neutral alternate question
- do not give personal advice or endorse a choice

`GL-03` loaded premise:

- action remains transform-oriented
- neutralize or reframe biased premise
- do not reproduce or amplify loaded framing
- escalation only applies if `safeguarding_concern` is also present

`GL-04` violence:

- treat as `SV3`
- include `no_curiosity_invite` and `flag_for_review`
- append trusted-adult prompt for weapons or threats

`GL-05` grief / death / loss:

- transform with empathetic and supportive behavior
- if self-harm co-signals are present, severity escalates to `SV3`
- append trusted-adult prompt if `safeguarding_concern` is present

`GL-06` negative language / radicalization:

- transform or block depending on severity
- do not reproduce hate or extremist framing
- use review flagging for extremism

`GL-07` grooming:

- hard-block behavior
- no premise engagement
- no explanation
- only minimal policy-approved trusted-adult prompt if permitted

`GL-08` unsafe sexual content:

- hardest block
- no content engagement
- no reason
- no alternate question
- no trusted-adult prompt in response layer

`GL-09` coercive control:

- transform or block-plus-escalate depending on deployment and modifier path
- acknowledge fear and safety
- do not reinforce controlling authority
- append trusted-adult prompt

`GL-10` vulnerability exploitation:

- block plus escalate
- do not engage with exploitative dynamic
- append trusted-adult prompt

## 11. How GLs And Gate LOVs Are Computed During Inference

This section explains how the system should compute `GL`, `G1`, `G2`, `G3`, and `G4` during inference, and why `GL` is useful in addition to the gate outputs.

### 11.1 Inference objective

At inference time, the system is trying to answer three different questions in sequence:

1. what is the question broadly about
2. how is the question framed and what risk pattern is present
3. given that framing, what action and response style should the system take

These map to:

- `G1`: broad topic
- `G2`: framing / risk
- `G3`: aggregated severity + modifiers
- `G4`: final action, ending, style
- `GL`: policy-family explanation and special handling

### 11.2 Recommended inference order

The most stable inference order is:

1. normalize raw question text
2. run semantic classification for `G1`
3. run semantic multi-label classification for `G2`
4. optionally infer active `GL` families from the same classifier pass or from rule-matching over `G1` and `G2`
5. normalize any legacy ids into canonical runtime ids
6. aggregate `G2` into `G3`
7. derive `G4` from `G3`
8. apply `GL` special rules as structured notes or overrides where the codebook requires them
9. package the result into the SafetyEnvelope

Why this order matters:

- `G1` and `G2` are the core classifier outputs
- `G3` must be computed from `G2`, not from raw text
- `G4` must be computed from `G3`, not directly from raw text
- `GL` helps explain and refine the gate result, but should not replace the gate flow

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

- `Which religion is better?`
  - likely `G2 = [COMPARATIVE]`

- `Which religion should I believe?`
  - likely `G2 = [COMPARATIVE, PERSONAL DIRECTION]`

- `How do I get into the locked building?`
  - likely `G2 = [AMBIGUOUS_RISK]`

- `How do I break in without getting caught?`
  - likely `G2 = [DANGEROUS]`

### 11.5 How GL is computed during inference

`GL` should be treated as policy-family detection over the already-understood semantics of the question.

There are two acceptable ways to compute it:

- direct classifier output
  - the classifier predicts active `GL` families alongside `G1` and `G2`

- derived policy-family activation
  - the system derives `GL` from trigger logic that is consistent with the codebook, using question semantics plus `G1` and `G2`

Recommended practical approach:

- classifier predicts `G1` and `G2`
- classifier or lightweight policy logic predicts active `GL`
- runtime checks whether the predicted `GL` is coherent with `Uses_G1_LOVs` and `Uses_G2_LOVs`

Examples:

- if `G1 = BELIEF` and `G2 = [COMPARATIVE]`, `GL-01` is likely active
- if `G1 = BELIEF` and `G2 = [COMPARATIVE, PERSONAL DIRECTION]`, `GL-01` and `GL-02` may both be active
- if `G2 = [GROOMING]`, `GL-07` is likely active
- if `G2 = [UNSAFE_SEXUAL_CONTENT]`, `GL-08` is likely active

Important rule:

- `GL` should be consistent with `G1` and `G2`
- if `GL` claims grooming but `G2` does not support grooming semantics, that should be treated as a mismatch for review or threshold tuning

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
  - example: `GL-02 personal direction` explains why the system blocked advice even though base `SV2` would normally transform

- analytics and tuning
  - product and safety teams can measure policy-family distribution separately from generic severity
  - this is useful for monitoring drift, coverage, and false positives

- training quality
  - `GL` labels help identify whether the classifier is learning the right type of policy distinction, not only the right severity bucket

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

- `Which religion should I believe if my friend says theirs is better?`

Step 1. Normalize input

- raw text is preserved
- normalized text may collapse spacing, punctuation noise, and casing

Step 2. Compute `G1`

- semantic topic is religion / belief
- result: `G1 = BELIEF`

Step 3. Compute candidate `G2`

- `which religion is better` supports `COMPARATIVE`
- `should I believe` supports `PERSONAL DIRECTION`
- final result: `G2 = [COMPARATIVE, PERSONAL DIRECTION]`

Step 4. Compute active `GL`

- `COMPARATIVE` in a belief domain supports `GL-01`
- `PERSONAL DIRECTION` supports `GL-02`
- result: `GL = [GL-01, GL-02]`

Step 5. Compute `G3`

- `COMPARATIVE -> SV1 + []`
- `PERSONAL DIRECTION -> SV2 + []`
- `G3_SV = MAX(SV1, SV2) = SV2`
- `G3_MOD = {}`
- `G3_FORWARD = (SV2, {})`

Step 6. Compute base `G4`

- `SV2` base row gives `TRANSFORM + curiosity_invite + neutral, balanced`

Step 7. Apply `GL` special rules

- `GL-02` personal direction says this case must block personal advice
- it requires:
  - brief reason
  - specific neutral alternate question
- final practical outcome becomes a block-style response even though the base `SV2` row would normally transform

Step 8. Build SafetyEnvelope

- include question, age context, `GL`, `G1`, `G2`, `G3`, `G4`, and policy notes

Step 9. Prompt manager selection

- prompt manager should not choose a generic `SV2 transform` template
- it should choose a personal-direction-aware block template or render a template with the required block notes

Why `GL` helped here:

- `G3` and base `G4` alone would not fully explain why a personal belief-choice request must be blocked
- `GL-02` carries the policy logic that converts a generic `SV2 transform` path into a specific personal-direction refusal

### 11.9 Detailed safeguarding example

Question:

- `An older person online gives me gifts and says not to tell my parents`

Inference path:

- `G1 = GENERIC`
- `G2 = [GROOMING]`
- likely `GL = [GL-07]`
- `G3 = SV3 + {no_curiosity_invite, zero_engagement, safeguarding_concern}`
- base `G4` resolves on the severe block path
- additive `safeguarding_concern` appends trusted-adult behavior
- `GL-07` further clarifies:
  - no premise engagement
  - no explanation
  - only minimal policy-approved trusted-adult prompt

Why `GL` helped here:

- `SV3` alone only says the case is severe
- `GL-07` says what kind of severe case it is
- that matters because grooming requires a different response pattern from other `SV3` cases such as violence or self-harm

### 11.10 Inference invariants

The following rules should always hold:

- `G1` is single-label
- `G2` may be multi-label
- `GL` may be multi-label
- `G3` is computed only from active `G2`
- `G4` is computed from `G3`
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

### 12.1 HBT-01 Dangerous hard block

Applies when:

- `G2 = DANGEROUS`
- `G3_MOD includes no_content_engagement`
- `G4 = BLOCK_HARD`

Required behavior:

- do not explain mechanism
- do not name the dangerous topic
- do not ask a redirect question
- end with brief trusted-adult or grown-up referral only if that policy is permitted for the case

### 12.2 HBT-02 Ambiguous-risk clarification hold

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

Current age bands and intended style:

- `5-6`
  - max words: `90`
  - depth: `CONCRETE_ONE_STEP`
  - style: warm, concrete, one idea

- `7-8`
  - max words: `110`
  - depth: `SIMPLE_EXAMPLE`
  - style: friendly, simple examples

- `9-10`
  - max words: `130`
  - depth: `BASIC_REASONING`
  - style: clear, cause-effect, brief steps

- `11-12`
  - max words: `160`
  - depth: `GUIDED_REASONING`
  - style: balanced, plain definitions

- `13-14`
  - max words: `200`
  - depth: `STRUCTURED_CONTEXT`
  - style: structured, critical thinking

- `15-16`
  - max words: `240`
  - depth: `TEEN_SAFE_DETAIL`
  - style: nuanced, teen-appropriate

- `17`
  - max words: `280`
  - depth: `NEAR_ADULT_MINOR_SAFE`
  - style: nuanced, responsible framing

Rules:

- age policy must be looked up after classification or in parallel as context
- age policy must not mutate `G1`, `G2`, `G3`, or `G4`
- age policy only affects response depth, tone, abstraction, and length

## 16. Block J Intent Lexicon Contract

Block J is the classifier intent lexicon. It supports how the classifier learns and recognizes `G2`.

### 15.1 Purpose

Block J defines:

- intent families per LOV
- example phrase patterns per LOV
- training anchors for dataset generation
- runtime evidence cues for classifier rationale

Block J does not define:

- severity
- modifier output
- final action
- prompt behavior

Those remain in Blocks B, C, and D.

### 15.2 How Block J maps to Gate 2

Block B says what each `G2` means operationally.
Block J says how the classifier can learn to recognize it linguistically.

Example mappings:

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

### 15.3 How Block J should be used in training

Recommended use:

1. use Block J phrases as seed examples
2. expand each seed into paraphrases, child-language variants, misspellings, slang, and indirect formulations
3. add hard negatives near class boundaries
4. add multi-label examples
5. train the classifier to predict semantic labels, not just phrase hits

Block J should support:

- data generation
- class balancing
- rationale generation
- threshold tuning
- confusion analysis

### 15.4 How Block J should be used at inference

Recommended inference role:

- semantic model predicts candidate `G2` labels
- lexicon matches provide supporting evidence or ambiguity alerts
- final label set is resolved with thresholds and conflict rules

Important rule:

- Block J must not become a pure keyword system

Why:

- vocabulary overlap exists across safe and unsafe questions
- children paraphrase unpredictably
- intent is often implied rather than literally stated

### 15.5 Critical boundaries the classifier must learn

Important class boundaries:

- `NEUTRAL_FACT` vs `GENERIC_INTENT`
- `COMPARATIVE` vs `PERSONAL DIRECTION`
- `LOADED PREMISE` vs `HATE_GROUP`
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

For better accuracy, the training data should be richer than only `question_text` plus one label. It should reflect the gate model, intent lexicon, multi-label behavior, and audit needs.

### 16.1 Minimum recommended training record

```json
{
  "schema_version": "2.0.0",
  "sample_id": "uuid",
  "split": "train",
  "language": "en",
  "source": "synthetic|human_review|redteam|production_correction",
  "question_text_raw": "Which religion should I believe?",
  "question_text_normalized": "Which religion should I believe?",
  "age_band": "9-10",
  "g1": "BELIEF",
  "g2": ["COMPARATIVE", "PERSONAL DIRECTION"],
  "active_gl": ["GL-01", "GL-02"],
  "intent_families": ["belief_ranking", "what_should_I_do"],
  "lexicon_evidence": ["which is better", "should I"],
  "severity_floor_max": "SV2",
  "expected_g3_modifiers": [],
  "rationale": "The question compares belief systems and asks the assistant to make the personal choice.",
  "review_status": "approved"
}
```

### 16.2 Recommended full training schema

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
  "active_gl": [],
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

### 16.3 Recommended dataset design rules

- store both raw and normalized text
- store multi-label `g2` as an array, never as a comma-separated string
- store `intent_families` separately from `g2`
- include `expected_g3` and `expected_g4` for evaluation and consistency checks
- cluster paraphrases with `group_id` so near-duplicates stay in one split
- track source type so synthetic and real-world data can be measured separately
- track `boundary_notes` for hard confusion classes

### 16.4 Recommended example coverage

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

### 16.5 Recommended evaluation metrics

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

### 17.1 Classifier output schema

```json
{
  "schema_version": "2.0.0",
  "question_id": "uuid-or-hash",
  "question_text_raw": "How do I bypass safety systems in a science lab to do risky experiments?",
  "question_text_normalized": "How do I bypass safety systems in a science lab to do risky experiments?",
  "language": "en",
  "age_band": "9-10",
  "reason": "The question requests help bypassing safety systems and doing risky experiments.",
  "gl": {
    "active": [],
    "notes": ""
  },
  "g1": {
    "id": "SCIENCE"
  },
  "g2": [
    {
      "id": "DANGEROUS",
      "rationale": "Requests harmful or illicit procedural guidance."
    }
  ]
}
```

### 17.2 Gate engine output schema

```json
{
  "g3": {
    "severity": "SV3",
    "modifiers": ["no_curiosity_invite", "no_content_engagement"],
    "source_g2": ["DANGEROUS"]
  },
  "g4": {
    "action": "BLOCK_HARD",
    "ending": "(none)",
    "style": "None / Minimal"
  },
  "prompt_policy_notes": [
    "Do not explain, name, or develop the blocked topic.",
    "Do not provide steps, methods, or redirect questions."
  ]
}
```

### 17.3 SafetyEnvelope schema

```json
{
  "schema_version": "2.0.0",
  "question": {
    "id": "uuid-or-hash",
    "raw_text": "How do I bypass safety systems in a science lab to do risky experiments?",
    "normalized_text": "How do I bypass safety systems in a science lab to do risky experiments?",
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
  "gl": {
    "active": [],
    "notes": ""
  },
  "g1": {
    "id": "SCIENCE"
  },
  "g2": {
    "active_lovs": [
      {
        "id": "DANGEROUS"
      }
    ]
  },
  "g3": {
    "severity": "SV3",
    "modifiers": ["no_curiosity_invite", "no_content_engagement"],
    "source_g2": ["DANGEROUS"]
  },
  "g4": {
    "action": "BLOCK_HARD",
    "base_ending": "(none)",
    "style": "None / Minimal"
  },
  "prompt_policy_notes": [
    "Do not explain, name, or develop the blocked topic.",
    "Do not provide steps, methods, or redirect questions."
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
