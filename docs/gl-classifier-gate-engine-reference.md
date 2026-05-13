# GL Classifier, Gate Engine, and Prompt Manager Reference

This document is aligned to the current [GL-codebook.csv](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/GL-codebook.csv) and [Contracts.csv](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/Contracts.csv). It describes the intended runtime contract from classifier output through Gate 3, Gate 4, SafetyEnvelope construction, and prompt rendering.

## 1. Source of Truth

The source of truth is the codebook, not legacy implementation names.

- `Contracts.csv` says the classifier assigns `G1` and `G2`.
- `GL-codebook.csv` defines the current `G1` LOVs, `G2` LOVs, `G3` computation, `G4` action table, GL notes, prompt rules, prompt templates, checklist items, and age policy rows.

Canonical runtime ownership:

1. classifier detects active guideline families
2. classifier assigns one `G1`
3. classifier assigns one or more `G2`
4. gate engine derives `G3`
5. gate engine derives `G4`
6. prompt manager renders the final prompt under prompt-rule and checklist constraints

## 2. Gate Dictionary Overview

The current codebook defines four gate layers:

- `G1`: broad nature / subject matter
- `G2`: framing, intent, or risk pattern
- `G3`: derived severity plus modifier packet
- `G4`: derived final action, ending, and response style

It also defines:

- `GL-01` to `GL-10`: guideline families with special handling notes
- prompt authoring rules `PR-01` to `PR-05`
- prompt checklist `CHK-01` to `CHK-08`
- age runtime policy in Block I

## 3. Current G1 LOVs

`G1` is single-label. It answers: what is the broad subject matter of the child’s question?

Current `G1` LOVs from the codebook:

- `FACT`
- `BELIEF`
- `DEATH_GRIEF`
- `SCIENCE`
- `TECHNOLOGY`
- `CIVIC_LAW`
- `GENERIC`

Important constraints:

- `G1` is topical classification, not the safety outcome.
- `G1` alone does not determine allow vs transform vs block.
- harmful framing is primarily carried by `G2`.

## 4. Current G2 LOVs

`G2` is multi-label. It answers: how is the question framed, and what safety-relevant pattern is present?

Current `G2` LOVs from the codebook:

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

Important constraints:

- multiple `G2` LOVs can fire for one query
- each active `G2` contributes a severity floor and zero or more modifiers
- Gate 3 uses the union of all matched `G2` rows

## 5. Gate Flow

The intended reading of the codebook is:

1. normalize the child question
2. classify active guideline-relevant signals
3. assign `G1`
4. assign one or more `G2`
5. derive `G3` from all active `G2`
6. derive `G4` from `G3`
7. apply additive GL notes and age policy without mutating core gate outputs unless the codebook explicitly says to do so

The distinction matters:

- `GL` rows describe policy families and special rules
- `G1` and `G2` are controlled classifier outputs
- `G3` and `G4` are deterministic gate outputs

## 6. Gate 3 Computation

`G3` contains:

- `severity`
- `modifiers`
- `source_g2`

Computation:

- `severity = MAX(severity_floor of all active G2 LOVs)`
- `modifiers = UNION(all modifier tags emitted by active G2 LOVs)`
- `source_g2 = ordered list of matched G2 ids`

Examples:

- `NEUTRAL_FACT -> SV0 + []`
- `EMOTIONAL -> SV2 + [empathetic_tone, emotional_support_required]`
- `DANGEROUS -> SV3 + [no_curiosity_invite, no_content_engagement]`
- `GROOMING -> SV3 + [no_curiosity_invite, zero_engagement, safeguarding_concern]`
- `UNSAFE_SEXUAL_CONTENT -> SV3 + [no_curiosity_invite, no_content_engagement, no_reason_given, zero_engagement]`
- `AMBIGUOUS_RISK -> SV2 + [clarification_required, no_curiosity_invite]`
- `SAFETY_HAZARD -> SV2 + [clarification_required]`
- `VIOLENCE -> SV3 + [no_curiosity_invite, flag_for_review]`

Worked examples:

- `Why is the sky blue?`
  - `G1 = SCIENCE`
  - `G2 = [NEUTRAL_FACT]`
  - `G3 = { severity: SV0, modifiers: [], source_g2: [NEUTRAL_FACT] }`

- `Kids are mean to me at school and I feel awful`
  - `G1 = GENERIC`
  - `G2 = [BULLYING, EMOTIONAL]`
  - `G3 = { severity: SV2, modifiers: [empathetic_tone, no_curiosity_invite, emotional_support_required], source_g2: [BULLYING, EMOTIONAL] }`

- `How do I bypass safety systems in a lab?`
  - `G1 = SCIENCE`
  - `G2 = [DANGEROUS]`
  - `G3 = { severity: SV3, modifiers: [no_curiosity_invite, no_content_engagement], source_g2: [DANGEROUS] }`

## 7. Gate 4 Computation

`G4` contains:

- `action`
- `ending`
- `style`

Read the Gate 4 table in this order:

1. find the row matching `G3_SV`
2. check `G3_MOD` for any variant row at that severity
3. apply the matching `Action`, `Base Ending`, and `Response Style`
4. then apply additive rules such as `safeguarding_concern`

Base interpretation from the current codebook:

- `SV0 -> ALLOW + curiosity_invite + neutral age-calibrated style`
- `SV1 -> TRANSFORM`, usually with `curiosity_invite`
- `SV2 -> TRANSFORM`, unless a modifier row upgrades it to hold or redirect behavior
- `SV3 -> BLOCK`, unless a modifier row upgrades it to hard block or block-plus-escalate behavior

Important modifier behavior:

- `no_curiosity_invite` suppresses ending questions
- `clarification_required` maps to `TRANSFORM_HOLD` with exactly one safe disambiguation question and no substantive answer in turn 1
- `empathetic_tone` changes style to warm/supportive
- `no_content_engagement` forbids topic engagement
- `zero_engagement` is stricter than ordinary blocking
- `safeguarding_concern` is additive and appends trusted-adult language after inheriting the base row

Worked examples:

- `SV0 + [] -> ALLOW + curiosity_invite + Neutral, age-calibrated`
- `SV2 + [clarification_required, no_curiosity_invite] -> TRANSFORM_HOLD + safe_disambiguation_question + Neutral`
- `SV3 + [no_curiosity_invite, no_content_engagement, zero_engagement] -> BLOCK_HARD + no ending + None / Minimal`
- `SV3 + [empathetic_tone, no_curiosity_invite] -> empathetic block variant with no ending question`

## 8. How To Read GL Rows

GL rows sit on top of the gates. They do not replace `G2 -> G3 -> G4`.

Read each GL row in this order:

1. `Applies_When`
2. `Uses_G1_LOVs`
3. `Uses_G2_LOVs`
4. `Special Rules on G3 or G4`

Runtime interpretation:

1. classifier reports active GL families
2. classifier assigns `G1` and `G2`
3. gate engine computes base `G3`
4. gate engine computes base `G4`
5. gate engine reads GL special rules and turns them into structured prompt-policy notes
6. prompt manager enforces those notes during prompt rendering

What GL rows do not do:

- they do not create free-form prompt text by themselves
- they do not bypass gate derivation
- they do not replace `G1` or `G2`

## 9. Current GL Family Interpretation

The current codebook GL block contains `GL-01` to `GL-10` with these meanings:

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

Notable changes from older references:

- age calibration is no longer a `GL-01` guideline family; it is handled by Block I age policy plus prompt rules
- `PD` and `LP` are not current LOV ids; the current names are `PERSONAL DIRECTION` and `LOADED PREMISE`
- `UNSAFE_CONTENT` is not the current LOV id; the current name is `UNSAFE_SEXUAL_CONTENT`
- the current codebook also has explicit `SAFETY_HAZARD` and `VIOLENCE` `G2` LOVs

## 10. GL Worked Examples

### 10.1 Comparative belief

- question: `Which religion is better?`
- likely classifier output:
  - `GL = [GL-01]`
  - `G1 = BELIEF`
  - `G2 = [COMPARATIVE]`
- gate result:
  - `G3 = SV1 + []`
  - `G4 = TRANSFORM + curiosity_invite`
- GL note:
  - keep response balanced
  - suppress curiosity invite if a later modifier requires suppression

### 10.2 Personal direction

- question: `Which religion should I believe?`
- likely classifier output:
  - `GL = [GL-02]`
  - `G1 = BELIEF`
  - `G2 = [PERSONAL DIRECTION]`
- base gate result:
  - `G3 = SV2 + []`
  - base `G4 = TRANSFORM + curiosity_invite`
- GL special rule:
  - force block behavior for personal choice-making
  - include a brief reason
  - include a specific neutral alternate question

### 10.3 Grooming

- question: `An older person told me to keep our chats secret`
- likely classifier output:
  - `GL = [GL-07]`
  - `G1 = GENERIC`
  - `G2 = [GROOMING]`
- gate result:
  - `G3 = SV3 + [no_curiosity_invite, zero_engagement, safeguarding_concern]`
  - `G4` follows the high-severity hard-block path
- GL special rule:
  - do not engage with the premise
  - do not explain why
  - append only the approved trusted-adult line if response-layer policy permits

### 10.4 Coercive control

- question: `I get hurt if I do not obey`
- likely classifier output:
  - `GL = [GL-09]`
  - `G1 = GENERIC`
  - `G2 = [COERCIVE_CONTROL]`
- gate result:
  - `G3 = SV3 + [empathetic_tone]`
- GL special rule:
  - acknowledge safety and feelings
  - do not reinforce the controlling dynamic
  - append trusted-adult language
  - escalate at system layer if deployment policy adds escalation

## 11. Age Policy Placement

Age runtime policy comes from Block I, not from the GL family block.

Current age bands:

- `5-6`
- `7-8`
- `9-10`
- `11-12`
- `13-14`
- `15-16`
- `17`

Age policy controls:

- answer style
- max words
- depth

Age policy does not change:

- `G1`
- `G2`
- `G3`
- `G4`

## 12. Block J Intent Lexicon

Block J in `GL-codebook.csv` is the classifier intent lexicon. Its purpose is to define the intent families, phrase patterns, and training examples that help the classifier learn how to assign `G2` labels consistently.

What Block J is for:

- it is training and inference support for classifier intent recognition
- it gives each `G2` LOV a set of semantic families
- it gives each `G2` LOV example phrase patterns the classifier can learn from
- it reduces ambiguity between nearby labels such as `DANGEROUS` vs `AMBIGUOUS_RISK`, or `EMOTIONAL` vs `SELF_HARM`

What Block J is not for:

- it is not a replacement for the `G2` table
- it does not define severity directly
- it does not define `G4` actions
- it should not be treated as a raw keyword rules engine on its own

### 12.1 How Block J maps to G2

In the current codebook, Block J effectively acts as the classifier-facing semantic index for `G2`.

The relationship is:

- Block B defines the official `G2` LOV, severity floor, modifier emissions, and classifier notes
- Block J expands each `G2` LOV with intent families and example phrases

Working interpretation:

- Block B tells you what label means in the gate system
- Block J tells you how the classifier can recognize that label in real language

Example mappings:

- `NEUTRAL_FACT`
  - families: factual definition, mechanism explanation, descriptive what/why/how
  - phrases: `what is`, `how does X work`, `why does X happen`
- `PERSONAL DIRECTION`
  - families: what_should_I_do, personal_choice, moral_guidance
  - phrases: `should I`, `tell me what to choose`, `decide for me`
- `DANGEROUS`
  - families: weapon making, sabotage, bypass security or law, how to hurt
  - phrases: `how do I make a bomb`, `how to hack`, `how to avoid getting caught`
- `AMBIGUOUS_RISK`
  - families: dual-use tools, access questions, vague preparation
  - phrases: `where can I buy a knife`, `what chemicals are easy to get`
- `SAFETY_HAZARD`
  - families: dangerous experiment, accidental risk, hazardous exposure
  - phrases: `make a plug point spark`, `mix random chemicals`, `is it safe to breathe fumes`

### 12.2 How the lexicon should work at training time

The lexicon should be used as supervised training support, not as the only labeling source.

Recommended training flow:

1. start from the official `G2` LOV definitions in Block B
2. use Block J families to define positive-intent buckets for each `G2`
3. use Block J phrases as seed examples, not final exhaustive examples
4. generate or collect paraphrases around each family
5. train the classifier to predict one or more `G2` labels from full-question meaning, not just token hits
6. validate that the resulting `G2` outputs still agree with Block B severity and modifier behavior

How to use the lexicon well in training:

- seed dataset creation
  - use each Block J phrase list as a bootstrap source for synthetic examples, adversarial paraphrases, spelling variants, and multilingual variants
- contrastive labeling
  - build hard negatives between nearby classes
  - example: `how do batteries work` should stay `NEUTRAL_FACT`, while `how do I make a battery explode` should move toward `DANGEROUS` or `SAFETY_HAZARD`
- multi-label composition
  - create examples where multiple intents coexist
  - example: `I feel awful because kids hit me at school` should support `BULLYING + EMOTIONAL`
- boundary conditioning
  - explicitly train around dangerous boundaries such as `AMBIGUOUS_RISK` vs `DANGEROUS`, `EMOTIONAL` vs `SELF_HARM`, and `LOADED PREMISE` vs `HATE_GROUP`

### 12.3 How the lexicon should work at inference time

At runtime, Block J should inform classifier behavior, but not override full semantic classification.

Recommended inference role:

- use Block J as a feature prior or explanation scaffold
- allow phrase-family matches to increase confidence for candidate `G2` labels
- still require full-question semantic interpretation before final label assignment

Safe inference pattern:

1. normalize the question
2. compute semantic classifier scores for `G1` and `G2`
3. use Block J family/phrase matches as supporting evidence
4. resolve final `G2` labels from model score plus lexicon evidence plus conflict rules
5. pass final `G2` only into Gate 3

This prevents a brittle keyword-only system.

Example:

- `Can vinegar and baking soda pop a bottle?`
  - lexical evidence may support `SAFETY_HAZARD`
  - if the phrasing suggests curiosity about a risky experiment, final `G2` may be `SAFETY_HAZARD`
  - if the phrasing instead asks for maximizing harm or injury, final `G2` may escalate toward `DANGEROUS`

### 12.4 Why Block J must not be treated as plain keywords

The phrase column is illustrative, not exhaustive. The classifier should learn concepts, not literal strings.

Why this matters:

- children paraphrase unpredictably
- misspellings, slang, code words, and indirect framing are common
- harmful intent is often implicit
- benign questions can share vocabulary with risky questions

Examples:

- `What is a knife made of?`
  - may be `NEUTRAL_FACT`
- `Where can I get a knife?`
  - may be `AMBIGUOUS_RISK`
- `What is the best knife to scare someone with?`
  - should move toward `VIOLENCE`

Same token family, different `G2`.

### 12.5 Recommended classifier decision pattern using Block J

A practical classifier stack can use Block J in this order:

1. semantic encoder or instruction model proposes candidate `G2` labels
2. lexicon features from Block J provide evidence boosts or ambiguity alerts
3. class-specific thresholds decide which labels fire
4. conflict resolution rules clean up overlapping cases
5. final `G2` set is emitted to Gate 3

Useful conflict-resolution rules:

- prefer `SELF_HARM` over plain `EMOTIONAL` when self-injury or suicidal ideation is explicit
- prefer `HATE_GROUP` over plain `LOADED PREMISE` when derogatory protected-group language is explicit
- prefer `DANGEROUS` over `AMBIGUOUS_RISK` when harmful instructions are directly requested
- allow `BULLYING + EMOTIONAL` together when both peer harm and distress are present
- allow `DEATH_GRIEF` in `G1` with `EMOTIONAL` or `SELF_HARM` in `G2` when grief and self-harm signals co-occur

### 12.6 Recommended data design for Block J

To make Block J useful for classifier training, each intent should have:

- seed phrases from the codebook
- paraphrases with different syntax
- age-appropriate child language variants
- misspellings and shorthand
- benign near-neighbors
- harmful near-neighbors
- multi-label examples

Recommended dataset fields:

```json
{
  "question_text": "Should I believe my religion or my friend's religion?",
  "g1": "BELIEF",
  "g2": ["PERSONAL DIRECTION", "COMPARATIVE"],
  "intent_families": ["what_should_I_do", "belief_ranking"],
  "lexicon_evidence": ["should I", "which is better"],
  "rationale": "The question asks for a personal choice while comparing beliefs."
}
```

Recommended split strategy:

- keep near-duplicate paraphrases in the same split group
- reserve adversarial phrasings for validation and test
- evaluate both single-label and multi-label accuracy
- report confusion pairs, not just aggregate F1

### 12.7 How Block J connects to explanations and auditability

Block J is also useful for internal rationale generation.

The classifier can use it to explain which family was matched without exposing raw prompt logic to the user.

Example internal rationale:

- `Assigned G2=DANGEROUS because the question matched the bypass_security_or_law family and requested harmful procedural help.`

This is appropriate for:

- audit logs
- offline error analysis
- threshold tuning
- dataset correction workflows

It is not the same as the final child-facing answer.

### 12.8 Recommended limits

Block J should guide the classifier, but the system should avoid overfitting to the lexicon.

Do not:

- hard-code exact phrase matching as the only signal
- assume every listed phrase always maps to exactly one label in isolation
- ignore context, negation, or who the harm target is
- bypass human review for newly emerging harmful phrasings not represented in the lexicon

Do:

- treat the lexicon as a living training aid
- update it when new phrasings appear in red-team or production review
- keep Block B and Block J synchronized so `G2` names and meanings do not drift

## 13. Prompt Rules and Checklist

Prompt generation must respect Block F and Block H of the codebook.

Current authoring rules:

- `PR-01`: gate fidelity
- `PR-02`: `clarification_required` means hold in turn 1
- `PR-03`: `no_content_engagement` means absolute silence on topic
- `PR-04`: `no_curiosity_invite` suppresses ending questions
- `PR-05`: age band and line/length constraint are mandatory

Current checklist items:

- `CHK-01`: age band is declared
- `CHK-02`: `G1`, `G2`, `G3`, `G4` are present in the prompt header
- `CHK-03`: explicit length instruction is present
- `CHK-04`: clarification hold is respected
- `CHK-05`: no topic content appears when forbidden
- `CHK-06`: no curiosity question appears when forbidden
- `CHK-07`: prompt body behavior matches `G4`
- `CHK-08`: prompt adds no unsupported framing or content

## 14. Runtime Contract

Recommended classifier-stage output:

```json
{
  "schema_version": "1.0.0",
  "question_id": "uuid-or-hash",
  "question_text": "How do I bypass safety systems in a lab?",
  "age_band": "9-10",
  "reason": "The child asks for help bypassing safety systems, which matches dangerous activity framing.",
  "guidelines": {
    "active": [],
    "notes": "Populate this only when runtime classifier logic explicitly surfaces a matching GL family."
  },
  "g1": {
    "id": "SCIENCE"
  },
  "g2": [
    {
      "id": "DANGEROUS",
      "rationale": "The question requests harmful or illicit instructions."
    }
  ]
}
```

Recommended SafetyEnvelope after gate derivation:

```json
{
  "schema_version": "1.0.0",
  "question_id": "uuid-or-hash",
  "question_text": "How do I bypass safety systems in a lab?",
  "age_band": "9-10",
  "reason": "The child asks for help bypassing safety systems, which matches dangerous activity framing.",
  "guidelines": {
    "active": [],
    "notes": ""
  },
  "g1": {
    "id": "SCIENCE"
  },
  "g2": [
    {
      "id": "DANGEROUS",
      "rationale": "The question requests harmful or illicit instructions."
    }
  ],
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
    "Do not provide steps, methods, workarounds, or redirect questions.",
    "If deployment policy allows trusted-adult language here, keep it brief and child-safe."
  ]
}
```

Notes on the contract:

- `reason` is classifier output, not prompt text
- `prompt_policy_notes` are derived downstream from `G4` plus any active GL special rules
- a deployment may keep `guidelines.active` sparse if only some GL rows are explicitly surfaced at runtime

## 15. Prompt Manager Responsibilities

The prompt manager consumes the SafetyEnvelope, not raw question text alone.

It should:

1. select a template from `G4`, `G3`, and relevant `G2`
2. inject age-band settings
3. inject gate tags into the prompt header
4. enforce prompt-rule constraints
5. validate the rendered prompt with the checklist before sending it to any LLM

Representative template mapping from the current codebook:

- `ALLOW_NEUTRAL_FACT` for `G4=ALLOW`, `G3=SV0`, `G2 includes NEUTRAL_FACT`
- hard-block dangerous template for `G2=DANGEROUS`, `G3_MOD includes no_content_engagement`
- clarification-hold template for `G2=AMBIGUOUS_RISK`, `G3_MOD includes clarification_required`

## 16. Final Alignment Summary

The current codebook should be interpreted as:

- classifier owns `GL`, `G1`, and `G2`
- gate engine owns deterministic `G3` and `G4`
- age policy is a runtime presentation layer, not a classifier label
- prompt manager must not soften gate outcomes
- prompt rules and checklist items are mandatory contract constraints, not optional guidance

This reference should be updated again whenever `GL-codebook.csv` changes its LOV ids, GL numbering, modifier names, or Gate 4 action rows.
