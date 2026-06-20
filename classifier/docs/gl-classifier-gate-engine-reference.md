# GL Classifier, Gate Engine, and Prompt Builder Implementation Reference

This is the final implementation reference for the classifier, deterministic gate engine, guideline notes, and prompt builder.

The runtime source of truth is the YAML codebook configuration under:

```text
classifier/configs/codebook-config/
```

Do not use authoring artifacts as runtime references after they have been converted into codebook YAML.

## 1. Runtime Config Files

The codebook runtime loads these configuration files:

- `g1.yaml`: G1 LOVs, names, and definitions.
- `g2.yaml`: G2 LOVs, definitions, severity floors, and associated flags.
- `g3.yml`: Gate 3 severity/modifier computation contract.
- `g4.yml`: Gate 4 final action and response-style contract.
- `gl-rules.yml`: Block E guideline notes.
- `flag-mappings.yaml`: Flag to tone/action/escalation mappings.
- `modifier-tags.yaml`: Tone/action/escalation variable definitions.
- `prompt-dictionary.yaml`: Prompt runtime variables and flag prompt fragments.
- `prompt-master-template.yml`: Final prompt master template.
- `prompt-rules.yaml`: Prompt authoring and compliance rules.
- `age-policy.yaml`: Age-band answer style, word budget, and depth settings.
- `intent-lexicon.yaml`: Intent families and intent phrases used as classifier support signals.

The parser entrypoint is:

```python
from training.slm_classifier.codebook import parse_codebook

codebook = parse_codebook()
```

## 2. Classifier Responsibilities

The SLM classifier predicts these outputs independently:

- `G1`
- `G2`
- `flags`
- `intent_families`
- `intent_phrases`

The classifier does not compute `G3`, `G4`, active GL behavior, or final prompt wording.

### G1

`G1` is the nature of the input.

It answers:

```text
What is the broad nature / subject matter of the child's question?
```

Examples of G1 nature categories include `FACT`, `BELIEF`, `SCIENCE`, `TECHNOLOGY`, and `GENERIC`.

G1 is topic/nature classification. It is not the safety decision.

### G2

`G2` is the single-label type/framing of the input.

It answers:

```text
How is the question framed? What is the intent or risk pattern of this query?
```

Examples of G2 framing categories include `NEUTRAL_FACT`, `PERSONAL_DIRECTION`, `DANGEROUS`, `EMOTIONAL`, `GROOMING`, `SELF_HARM`, and `AMBIGUOUS_RISK`.

G2 is the main safety-framing prediction. The classifier returns exactly one selected runtime G2. G2 is not multi-label. Intent families and intent phrases may support that selection, but there is no second or supporting G2 path in deterministic gate logic.

### Flags

Flags are independently predicted by the classifier.

Flags show which safety signals are associated with the input. They are not derived from G1 or G2.

Examples:

- `has_emotional_distress`
- `has_safety_hazard`
- `has_grooming_involved`
- `has_vuln_exploit`
- `has_self_harm`
- `has_loaded_premise`
- `has_harmful_comparison`
- `has_negative_language`

The meaning of active flags becomes deterministic only when the gate engine reads `flag-mappings.yaml`.

### Intent Families And Intent Phrases

`intent_families` and `intent_phrases` are classifier support signals.

They help identify the selected G2 by providing intent-pattern evidence. They do not directly decide G3, G4, or final prompt wording.

Runtime uses them as explanation/support metadata, not as the authoritative gate decision.

## 3. Deterministic Runtime Responsibilities

The deterministic runtime owns:

- G3 computation
- G4 computation
- GL guideline-note application
- prompt-builder assembly
- final prompt rendering

The deterministic runtime must not ask the classifier to decide prompt behavior.

## 4. Gate 3: Severity Computation

Config source:

```text
classifier/configs/codebook-config/g3.yml
```

Gate 3 is:

```text
GATE 3: SEVERITY COMPUTATION | GATE ENGINE
```

It answers:

```text
Given the single selected G2 LOV, what is the combined severity and modifier set for this query?
```

Gate 3 does not add new LOVs. It reads the single selected G2, the active flags, and codebook configuration, then produces the packet that Gate 4 consumes.

Gate 3 has three elements.

### G3_SV

`G3_SV` is severity.

Config key:

```yaml
g3.elements.G3_SV
```

Computation rule:

```text
G3_SV = Severity Floor of that G2
```

Because runtime uses exactly one selected G2, severity is the severity floor of that selected G2. If the framing is unclear or confidence is too low, the selected G2 should be `AMBIGUOUS_RISK`.

Example:

```text
If selected G2 is GROOMING and GROOMING has severity floor SV3, then G3_SV = SV3.
If selected G2 confidence is too low to assign a concrete framing, selected G2 becomes AMBIGUOUS_RISK and G3_SV follows the AMBIGUOUS_RISK severity floor.
```

Help text:

```text
A single SV3 LOV makes the whole query SV3, regardless of other LOVs. Severity only goes up, never down.
```

### G3_MOD

`G3_MOD` is the modifier packet.

Config key:

```yaml
g3.elements.G3_MOD
```

Computation rule:

```text
G3_MOD = all active flags array mapped through flag-mappings.yaml
```

The classifier predicts active flags. The gate engine reads `flag-mappings.yaml` and converts each active flag into tone/action/escalation candidates.

Example:

```text
Active flags:
- has_emotional_distress
- has_bullying_involved

flag-mappings.yaml emits:
- has_emotional_distress -> supportive / normal_advice / none
- has_bullying_involved -> supportive / boundary_setting / none

G3_MOD carries the active tone/action/escalation candidates forward.
```

Help text:

```text
All active classifier flags are collected. Their tone/action/escalation mappings are read from flag-mappings.yaml. Order does not matter; later GL priority rules resolve conflicts.
```

### G3_FORWARD

`G3_FORWARD` is the output to Gate 4.

Config key:

```yaml
g3.elements.G3_FORWARD
```

Computation rule:

```text
Forward the pair: (G3_SV, G3_MOD) as the instruction packet.
```

Gate 4 reads `g4.yml` using `G3_SV`, then applies modifier and GL behavior from `G3_MOD` and `gl-rules.yml`.

Example:

```text
G3_FORWARD = SV3 + {
  tone: firm,
  action: boundary_setting,
  escalation: encourage_help_seeking
}
```

Help text:

```text
Gate 4 reads G3_SV to pick the base action, then reads G3_MOD to adjust response style, tone, ending, and escalation.
```

## 5. Gate 4: Final Action + Response Style

Config source:

```text
classifier/configs/codebook-config/g4.yml
```

Gate 4 is:

```text
Gate 4: FINAL ACTION + RESPONSE STYLE | GATE ENGINE
```

It answers:

```text
Given G3_SV and G3_MOD, what action should the response take and how should it be styled?
```

Base severity actions from `g4.yml`:

| G3_SV | G4 Action | Meaning |
|---|---|---|
| `SV0` | `ALLOW` | Answer directly and fully. Append curiosity invite. |
| `SV1` | `TRANSFORM` | Reframe loaded/ranking framing. Respond with balanced perspective. |
| `SV2` | `TRANSFORM` | Transform with balanced framing. No hard block. |
| `SV3` | `BLOCK` | Block the response. Include a brief reason and safe redirect. |

Gate 4 must not recompute classifier semantics. It reads the deterministic `G3_FORWARD` packet.

## 6. Flag Mapping

Config source:

```text
classifier/configs/codebook-config/flag-mappings.yaml
```

Each active classifier flag maps to:

- `Tone`
- `Action`
- `Escalation`

Example:

```yaml
has_self_harm:
  tone: supportive
  action: safety_check
  escalation: encourage_help_seeking
```

The gate engine gathers all tone/action/escalation candidates from active flags. Conflict resolution is handled by GL guideline notes.

## 7. GL Guideline Notes

Config source:

```text
classifier/configs/codebook-config/gl-rules.yml
```

GL notes are deterministic gate-engine rules. They resolve tone/action/escalation priority and response order after flags have been mapped.

Active GL notes:

- `GL-T1`: TonePriorityGL
- `GL-A1`: ActionPriorityGL
- `GL-E1`: EscalationPriorityGL
- `GL-CU1`: Clinical Concern Support Router
- `GL-O1`: ResponseOrderGL

### GL-T1: Tone Priority

When more than one tone candidate is active:

1. if any `firm`, use `firm`
2. else if any `cautious`, use `cautious`
3. else use `supportive`

Apply the final tone consistently throughout the response.

### GL-A1: Action Priority

When more than one action candidate is active:

1. if any `safety_check`, use `safety_check`
2. else if any `boundary_setting`, use `boundary_setting`
3. else if any `clarify_context`, use `clarify_context`
4. else if any `de_escalate`, use `de_escalate`
5. else use `normal_advice`

If `safety_check` is chosen, it must come first in the response.

### GL-E1: Escalation Priority

If any active flag requires `encourage_help_seeking`, direct the child to a trusted adult, parent, caregiver, teacher, counselor, doctor, or helpline.

Otherwise do not escalate.

### GL-CU1: Curiosity Invite Routing

If severity is `SV3`, use `no_curiosity_invite`.

Otherwise use `curiosity_invite`.

Do not end high-risk responses with exploratory or open-ended engagement.

### GL-O1: Response Order

Response order:

1. if `safety_check` is active, ask the safety question first
2. apply tone consistently
3. perform the selected action
4. if `encourage_help_seeking` is active, end with a clear direction to contact a trusted adult

## 8. Prompt Builder

The prompt builder consumes deterministic outputs only.

Inputs:

- child age
- selected G1
- single selected G2
- active flags
- `G3_SV`
- `G3_MOD`
- `G4`
- active GL guideline notes
- runtime variables from `prompt-dictionary.yaml`
- final template from `prompt-master-template.yml`

### Prompt Runtime Variables

Config source:

```text
classifier/configs/codebook-config/prompt-dictionary.yaml
```

Prompt dictionary provides:

- `runtime_variables`
- `flag_prompts`

`runtime_variables` define text for variables such as:

- `supportive`
- `cautious`
- `firm`
- `clarify_context`
- `boundary_setting`
- `de_escalate`
- `encourage_help_seeking`
- `safety_check`
- `normal_advice`

`flag_prompts` define:

- `{flag_context}`
- `{flag_guidance}`
- `{flag_example_start}`

### Prompt Master Template

Config source:

```text
classifier/configs/codebook-config/prompt-master-template.yml
```

The final prompt must be rendered from:

```yaml
prompt_master_template.template
```

Required placeholders:

- `{age}`
- `{flag_context}`
- `{tone_instructions}`
- `{action_instructions}`
- `{escalation_instructions}`
- `{flag_guidance}`
- `{flag_example_start}`
- `{attached_guidelines}`

### Prompt Builder Algorithm

1. Read classifier output: `G1`, `G2`, flags, intent support metadata.
2. Read G2 severity floor from `g2.yaml`.
3. Compute `G3_SV` using `g3.yml`.
4. Map active flags through `flag-mappings.yaml` to collect tone/action/escalation candidates.
5. Build `G3_MOD` from those active mapped candidates.
6. Build `G3_FORWARD = (G3_SV, G3_MOD)`.
7. Read `g4.yml` using `G3_SV` to select base G4 action.
8. Apply GL rules from `gl-rules.yml`:
   - resolve tone with `GL-T1`
   - resolve action with `GL-A1`
   - resolve escalation with `GL-E1`
   - resolve curiosity ending with `GL-CU1`
   - resolve ordering with `GL-O1`
9. Read final variable text from `prompt-dictionary.yaml`.
10. Select flag prompt fragments from `prompt_dictionary.flag_prompts`.
11. Attach GL guideline notes as `{attached_guidelines}`.
12. Render `prompt-master-template.yml`.
13. Validate prompt with `prompt-rules.yaml`.

## 9. Prompt Builder Examples

These examples show deterministic prompt-builder behavior. They are implementation examples, not classifier-training examples.

### Example 1: Neutral Fact

Input:

```text
Why do leaves fall?
```

Classifier:

```yaml
G1: SCIENCE
G2: NEUTRAL_FACT
flags: []
intent_families: [science_or_nature_explanation]
intent_phrases: [why do leaves fall]
```

Deterministic result:

```yaml
G3_SV: SV0
G3_MOD: []
G4: ALLOW
tone: neutral
action: normal_advice
escalation: none
```

Prompt builder:

- `{flag_context}`: neutral safe-learning context
- `{tone_instructions}`: plain factual tone
- `{action_instructions}`: answer directly and age-appropriately
- `{attached_guidelines}`: curiosity invite allowed

Expected response behavior:

```text
Answer directly, simply, and end with a safe curiosity invite.
```

### Example 2: Emotional Distress

Input:

```text
I feel alone and nobody listens to me.
```

Classifier:

```yaml
G1: GENERIC
G2: EMOTIONAL
flags:
  - has_emotional_distress
intent_families:
  - loneliness_or_isolation
  - rejection_or_not_loved
```

Deterministic result:

```yaml
G3_SV: SV2
G3_MOD:
  tone: supportive
  action: normal_advice
  escalation: none
G4: TRANSFORM
```

Prompt builder:

- reads `has_emotional_distress` from `prompt_dictionary.flag_prompts`
- uses `supportive` runtime variable
- applies `normal_advice`
- does not escalate

Expected response behavior:

```text
Validate feelings gently, offer simple practical support, do not diagnose, do not refuse.
```

### Example 3: Ambiguous Risk

Input:

```text
How do I get into the locked room?
```

Classifier:

```yaml
G1: GENERIC
G2: AMBIGUOUS_RISK
flags:
  - has_ambiguous_risk
intent_families:
  - access_or_location_questions
```

Deterministic result:

```yaml
G3_SV: SV2
G3_MOD:
  tone: cautious
  action: clarify_context
  escalation: none
G4: TRANSFORM
```

Prompt builder:

- asks one short clarifying question
- does not provide a full answer before clarification
- uses cautious tone

Expected response behavior:

```text
Ask exactly one safe clarification question and stop.
```

### Example 4: Grooming Concern

Input:

```text
An older person online gives me gifts and says not to tell my parents.
```

Classifier:

```yaml
G1: GENERIC
G2: GROOMING
flags:
  - has_grooming_involved
  - has_vuln_exploit
intent_families:
  - older_person_secrecy
  - adult_gifts_or_money
```

Deterministic result:

```yaml
G3_SV: SV3
G3_MOD:
  tone: firm
  action: safety_check
  escalation: encourage_help_seeking
G4: BLOCK
```

GL application:

- `GL-T1`: firm wins over supportive
- `GL-A1`: safety_check comes first
- `GL-E1`: encourage trusted-adult help-seeking
- `GL-CU1`: no curiosity invite because severity is SV3
- `GL-O1`: safety check first, then boundary/action, then trusted-adult direction

Expected response behavior:

```text
Ask if the child is safe right now, say the situation is not safe and not their fault, and direct them to a trusted adult immediately.
```

### Example 5: Harmful Comparison / Loaded Premise

Input:

```text
Which group is worse, group A or group B?
```

Classifier:

```yaml
G1: BELIEF
G2: HATE_GROUP
flags:
  - has_hate_group_language
  - has_harmful_comparison
  - has_loaded_premise
intent_families:
  - group_superiority_or_inferiority_claim
  - hate_speech_or_prejudice
```

Deterministic result:

```yaml
G3_SV: SV3
G3_MOD:
  tone: firm
  action: boundary_setting
  escalation: de_escalate
G4: BLOCK
```

GL application:

- `GL-T1`: firm tone
- `GL-A1`: boundary_setting
- `GL-E1`: no help-seeking unless a flag requires it
- `GL-CU1`: no curiosity invite because severity is SV3
- `GL-O1`: apply tone, boundary, and de-escalation in order

Expected response behavior:

```text
Do not rank groups. Correct the unfair premise, avoid repeating hateful wording, and redirect to respectful neutral framing.
```

## 10. Rendered Prompt Examples

These examples show the kind of final prompt the prompt builder would produce from `prompt-master-template.yml` after classifier output, G3/G4 computation, flag mapping, GL application, and prompt dictionary lookup.

### Rendered Prompt 1: Emotional Distress

User input:

```text
I feel alone and nobody listens to me.
```

Rendered prompt:

```text
You are a child-safe assistant responding to a child aged 10

SITUATION:
The child is experiencing emotional distress.

ACTIVE MODIFIERS:
Use a warm, kind, reassuring, non-judgmental tone. Validate feelings without endorsing harmful content.
Provide ordinary, non-sensitive, age-appropriate guidance. Keep it practical, neutral, and not clinical.
No special escalation.

SPECIFIC GUIDANCE FOR THIS SITUATION:
Say something supportive and offer simple, practical advice. Do not diagnose, do not escalate, and do not refuse.

Start your response like this (adapt to the situation):
"I'm really sorry you're feeling this hard. It makes sense that you're overwhelmed..."

GENERAL RULES AND TIE-BREAKERS:
- Be age-appropriate, simple, and clear.
- Do not give medical advice, diagnosis, or treatment instructions.
- Do not help with self-harm, violence, illegal activity, unsafe sexual content, or exploitation.

ATTACHED GUIDELINES:
GL-T1: Use supportive tone because no firm or cautious tone candidate is active.
GL-A1: Use normal_advice because no higher-priority action candidate is active.
GL-E1: Do not escalate because no active flag requires encourage_help_seeking.
GL-CU1: Curiosity invite is allowed because severity is not SV3.
GL-O1: Apply tone consistently, then provide simple advice.

GUIDELINE APPLICATION RULES:
- Treat attached guidelines as binding rules for this response.
- If multiple attached guidelines apply, follow all of them together.
- If two attached guidelines appear to conflict, use the stricter safety-preserving behavior.
- Do not duplicate or override logic already specified in attached guidelines.

Now respond to the child's message using the attached guidelines.
```

### Rendered Prompt 2: Ambiguous Risk

User input:

```text
How do I get into the locked room?
```

Rendered prompt:

```text
You are a child-safe assistant responding to a child aged 12

SITUATION:
The child's message shows ambiguous risk.

ACTIVE MODIFIERS:
Use careful, measured language. Avoid overclaiming, diagnosis, certainty, or unnecessary detail.
Ask one brief clarifying question before answering. Do not give a full answer until the missing context is resolved.
No special escalation.

SPECIFIC GUIDANCE FOR THIS SITUATION:
Ask a short clarifying question to understand what the child is thinking about. Do not give a full answer until you know more.

Start your response like this (adapt to the situation):
"First, I need to understand more. Can you tell me what you were thinking about doing, and whether it involves hurting yourself or someone else, or breaking rules?..."

GENERAL RULES AND TIE-BREAKERS:
- Be age-appropriate, simple, and clear.
- Do not give medical advice, diagnosis, or treatment instructions.
- Do not help with self-harm, violence, illegal activity, unsafe sexual content, or exploitation.

ATTACHED GUIDELINES:
GL-T1: Use cautious tone because a cautious tone candidate is active.
GL-A1: Use clarify_context because the active action candidate requires clarification.
GL-E1: Do not escalate because no active flag requires encourage_help_seeking.
GL-CU1: Curiosity invite is allowed because severity is not SV3, but the first turn must only clarify.
GL-O1: Ask exactly one clarification question before any answer.

GUIDELINE APPLICATION RULES:
- Treat attached guidelines as binding rules for this response.
- If multiple attached guidelines apply, follow all of them together.
- If two attached guidelines appear to conflict, use the stricter safety-preserving behavior.
- Do not duplicate or override logic already specified in attached guidelines.

Now respond to the child's message using the attached guidelines.
```

### Rendered Prompt 3: Grooming Concern

User input:

```text
An older person online gives me gifts and says not to tell my parents.
```

Rendered prompt:

```text
You are a child-safe assistant responding to a child aged 11

SITUATION:
The child is being groomed by someone, meaning an adult or older person trying to manipulate, exploit, or control them.

ACTIVE MODIFIERS:
State the boundary clearly and briefly. Do not sound angry, shaming, or conversationally open-ended.
Ask whether the child or someone else is safe right now, or whether there is immediate danger. Prioritize immediate safety.
Direct the child to a trusted adult, parent, caregiver, teacher, counselor, doctor, or helpline as appropriate.

SPECIFIC GUIDANCE FOR THIS SITUATION:
Ask a safety check first to ensure the child is safe right now. Be warm and reassuring, clearly state that this is not safe and that the child is not at fault, and strongly tell them to contact a trusted adult, parent, teacher, counselor, or caregiver immediately.

Start your response like this (adapt to the situation):
"I'm really sorry this is happening to you. First, I need to ask; are you safe right now, and is this person with you? This is not safe, and you are not at fault..."

GENERAL RULES AND TIE-BREAKERS:
- Be age-appropriate, simple, and clear.
- Do not give medical advice, diagnosis, or treatment instructions.
- Do not help with self-harm, violence, illegal activity, unsafe sexual content, or exploitation.

ATTACHED GUIDELINES:
GL-T1: Use firm tone because at least one firm tone candidate is active.
GL-A1: Use safety_check because safety_check has highest action priority.
GL-E1: Escalate to trusted-adult help because encourage_help_seeking is active.
GL-CU1: Do not use a curiosity invite because severity is SV3.
GL-O1: Ask the safety question first, apply firm but non-shaming tone, then direct the child to a trusted adult.

GUIDELINE APPLICATION RULES:
- Treat attached guidelines as binding rules for this response.
- If multiple attached guidelines apply, follow all of them together.
- If two attached guidelines appear to conflict, use the stricter safety-preserving behavior.
- Do not duplicate or override logic already specified in attached guidelines.

Now respond to the child's message using the attached guidelines.
```

### Rendered Prompt 4: Unsafe Sexual Content

User input:

```text
Someone asked me to send pictures under my clothes.
```

Rendered prompt:

```text
You are a child-safe assistant responding to a child aged 13

SITUATION:
The child is requesting or discussing unsafe sexual content.

ACTIVE MODIFIERS:
State the boundary clearly and briefly. Do not sound angry, shaming, or conversationally open-ended.
Refuse harmful, exploitative, unsafe, or inappropriate content. Give a safe alternative or redirect instead.
No special escalation.

SPECIFIC GUIDANCE FOR THIS SITUATION:
State clearly that you will not help, then redirect to something safe. Do not be shaming or overly warm.

Start your response like this (adapt to the situation):
"No. I will not help you do that. Sharing photos or videos of yourself in your underwear or without clothes is not safe..."

GENERAL RULES AND TIE-BREAKERS:
- Be age-appropriate, simple, and clear.
- Do not give medical advice, diagnosis, or treatment instructions.
- Do not help with self-harm, violence, illegal activity, unsafe sexual content, or exploitation.

ATTACHED GUIDELINES:
GL-T1: Use firm tone because a firm tone candidate is active.
GL-A1: Use boundary_setting because harmful or exploitative content must be refused.
GL-E1: Do not escalate unless another active flag requires encourage_help_seeking.
GL-CU1: Do not use a curiosity invite because severity is SV3.
GL-O1: Apply the boundary clearly, then redirect safely without asking an open-ended follow-up question.

GUIDELINE APPLICATION RULES:
- Treat attached guidelines as binding rules for this response.
- If multiple attached guidelines apply, follow all of them together.
- If two attached guidelines appear to conflict, use the stricter safety-preserving behavior.
- Do not duplicate or override logic already specified in attached guidelines.

Now respond to the child's message using the attached guidelines.
```

### Rendered Prompt 5: Loaded Premise And Harmful Comparison

User input:

```text
Which group is worse, group A or group B?
```

Rendered prompt:

```text
You are a child-safe assistant responding to a child aged 15

SITUATION:
The child's question contains a biased or unfair assumption about a person or group.

ACTIVE MODIFIERS:
State the boundary clearly and briefly. Do not sound angry, shaming, or conversationally open-ended.
Refuse harmful, exploitative, unsafe, or inappropriate content. Give a safe alternative or redirect instead.
Reduce conflict, intensity, or risk. Do not amplify fear, anger, or urgency unless there is immediate danger.

SPECIFIC GUIDANCE FOR THIS SITUATION:
First, gently correct or neutralize the biased premise. Do not treat the unfair assumption as true. If you need to mention the biased idea, clearly mark it as hurtful or untrue. After correcting the premise, you may give a neutral, factual explanation if it is safe and appropriate. Do not repeat slurs or hateful slogans in your own voice.

Start your response like this (adapt to the situation):
"Some people say that, but it is not true or fair. People of different genders, backgrounds, or religions are not better or worse as human beings..."

GENERAL RULES AND TIE-BREAKERS:
- Be age-appropriate, simple, and clear.
- Do not give medical advice, diagnosis, or treatment instructions.
- Do not help with self-harm, violence, illegal activity, unsafe sexual content, or exploitation.

ATTACHED GUIDELINES:
GL-T1: Use firm tone because a firm tone candidate is active.
GL-A1: Use boundary_setting because the request asks the assistant to rank harmful or biased options.
GL-E1: Do not escalate because no active flag requires encourage_help_seeking.
GL-CU1: Do not use a curiosity invite because severity is SV3.
GL-O1: Correct the premise, refuse to rank groups, de-escalate, and redirect to respectful neutral framing.

GUIDELINE APPLICATION RULES:
- Treat attached guidelines as binding rules for this response.
- If multiple attached guidelines apply, follow all of them together.
- If two attached guidelines appear to conflict, use the stricter safety-preserving behavior.
- Do not duplicate or override logic already specified in attached guidelines.

Now respond to the child's message using the attached guidelines.
```

## 11. Error Handling, Special Cases, And Overlaps

This section documents the expected corner cases and how the implementation should handle them. The guiding rule is conservative determinism: when model output is incomplete, conflicting, or ambiguous, preserve safety, keep the gate packet auditable, and avoid inventing policy outside the codebook config.

### 11.1 Missing Or Unknown G1

Case:

- classifier does not return a G1
- classifier returns a G1 not present in `g1.yaml`
- G1 confidence is unusably low

Expected handling:

- use `GENERIC` as the fallback G1
- preserve raw classifier metadata for audit
- do not let missing G1 lower G3 severity
- do not derive G2 from fallback G1

Rationale:

G1 is nature/topic. It can support prompt context, but it must not override G2 risk framing.

### 11.2 Low-Confidence Or Unclear G2

Case:

- classifier G2 score is low or uncertain
- classifier cannot confidently assign a concrete G2 framing
- classifier output is unclear enough that the next safe action requires more context

Expected handling:

- assign `AMBIGUOUS_RISK` as the runtime G2
- compute G3 from `AMBIGUOUS_RISK`
- map `has_ambiguous_risk` through `flag-mappings.yaml`
- prompt builder should ask one short clarifying question before giving a full answer
- keep low-confidence scores and raw classifier metadata for audit

Rationale:

G2 is single-label in runtime. There is no supporting G2 evidence path. When the classifier cannot confidently identify the framing, the correct behavior is not to fall back to `GENERIC_INTENT`; it is to assign `AMBIGUOUS_RISK` so the prompt can ask a clarifying question and avoid unsafe assumptions.

### 11.3 Single Selected G2 And Intent Support Signals

Case:

- SLM predicts exactly one selected G2
- intent families and intent phrases provide supporting evidence for that selected G2
- selected G2 confidence may be low

Expected handling:

- deterministic gates read exactly one selected runtime G2
- do not aggregate alternate G2 candidates
- do not promote a second G2 in the gate engine
- use intent families and phrases only as support metadata for explaining the selected G2
- if selected G2 confidence is too low or the framing remains unclear, set selected G2 to `AMBIGUOUS_RISK`

Examples:

- selected `G2 = EMOTIONAL`, supported by `sadness_or_low_mood` and `loneliness_or_isolation`
- selected `G2 = GROOMING`, supported by `older_person_secrecy` and `adult_gifts_or_money`
- selected `G2 = AMBIGUOUS_RISK`, used when the model cannot confidently distinguish benign from risky framing

### 11.4 Flag And G2 Disagreement

Case:

- G2 looks low risk but flags are risky
- G2 is risky but no matching flag is active
- flags suggest multiple behaviors such as `safety_check` and `boundary_setting`

Expected handling:

- G3 severity comes from G2 severity floor
- G3 modifier candidates come from active flags via `flag-mappings.yaml`
- do not discard flags only because G2 appears neutral
- do not create new flags from G2 inside the gate engine
- preserve disagreement in audit metadata

Examples:

- `G2 = NEUTRAL_FACT`, `has_ambiguous_risk = true`: clarify before giving operational detail.
- `G2 = GROOMING`, no grooming flag: keep SV3 severity from G2, but attached prompt variables may be less specific unless a relevant flag prompt is available.
- `has_self_harm` and `has_medical_concern`: `GL-A1` selects `safety_check`; `GL-E1` selects help-seeking.

### 11.5 Multiple Active Flags

Case:

- several independent flags are active for one input

Expected handling:

- map every active flag through `flag-mappings.yaml`
- collect all tone/action/escalation candidates
- use `GL-T1`, `GL-A1`, and `GL-E1` to resolve priority
- keep all active flags in prompt/audit metadata even if one action wins

Common overlaps:

- `has_grooming_involved` + `has_vuln_exploit`: safety check plus trusted-adult help-seeking.
- `has_emotional_distress` + `has_self_harm`: supportive tone plus safety check and escalation.
- `has_hate_group_language` + `has_loaded_premise`: firm boundary plus premise correction.
- `has_harmful_comparison` + `has_negative_language`: refuse ranking and avoid repeating abusive wording.
- `has_safety_hazard` + `has_dangerous_context`: safety check may come first, but harmful operational instructions must still be refused.

### 11.6 Tone/Action/Escalation Conflicts

Case:

- mapped flags produce conflicting tone, action, or escalation candidates

Expected handling:

- tone conflict resolves through `GL-T1`
- action conflict resolves through `GL-A1`
- escalation conflict resolves through `GL-E1`
- response order resolves through `GL-O1`

Priority summary:

- tone: `firm` > `cautious` > `supportive`
- action: `safety_check` > `boundary_setting` > `clarify_context` > `de_escalate` > `normal_advice`
- escalation: any `encourage_help_seeking` means help-seeking is active

If a conflict is not covered by GL rules, choose the stricter safety-preserving behavior and record the ambiguity for audit.

### 11.7 SV3 Curiosity Invite Suppression

Case:

- G3 severity is `SV3`
- prompt builder would otherwise add an ending question or curiosity invite

Expected handling:

- apply `GL-CU1`
- suppress curiosity invite
- do not end high-risk responses with exploratory/open-ended engagement

This applies even when the user asks a sensitive question conversationally.

### 11.8 Ambiguous Risk And Clarification

Case:

- `G2 = AMBIGUOUS_RISK`
- `has_ambiguous_risk` is active
- intent is incomplete or dual-use

Expected handling:

- use `clarify_context`
- ask exactly one brief clarifying question
- do not provide a full answer before clarification
- do not include operational details in the clarification turn

Examples:

- "How do I unlock this?"
- "What happens if I mix these?"
- "How do I get into the room?"

### 11.9 Clinical, Medical, And Self-Harm Overlap

Case:

- medical or clinical concern appears with emotional distress or self-harm

Expected handling:

- do not diagnose
- do not provide medical dosing, treatment, or self-treatment instructions
- if `has_self_harm` is active, safety check and help-seeking take priority
- if `has_medical_concern` is active without immediate safety concern, use cautious tone and direct to an adult or doctor

Overlap examples:

- `has_clinical_concern` + `has_significant_impairment`: supportive tone, serious-help framing.
- `has_medical_concern` + `has_self_harm`: safety check and trusted adult direction.
- `has_emotional_distress` without self-harm: supportive normal advice, no diagnosis.

### 11.10 Grooming, Exploitation, And Coercive Control Overlap

Case:

- grooming, vulnerability exploitation, coercive control, unsafe sexual content, or privacy risk co-occur

Expected handling:

- prioritize immediate safety check if `safety_check` is active
- use firm/supportive wording without blaming the child
- activate help-seeking if any mapped flag requires it
- avoid asking the child to investigate or confront the other person
- avoid detailed discussion of exploitative content

Overlap examples:

- `has_grooming_involved` + `has_privacy_risk`: do not share information; tell a trusted adult.
- `has_vuln_exploit` + `has_coercive_control`: boundary plus trusted-adult support.
- `has_unsafe_sexual_content` + `has_grooming_involved`: safety check and help-seeking dominate.

### 11.11 Hate, Loaded Premise, Harmful Comparison, And Negative Language

Case:

- the child uses biased framing, abusive language, or asks the assistant to rank harmful options

Expected handling:

- do not repeat slurs or abusive language in the assistant's own voice
- do not rank groups or harmful options
- correct the unfair premise before any safe factual explanation
- use de-escalation when mapped by flags
- keep the tone firm without shaming the child

Overlap examples:

- `has_hate_group_language` + `has_loaded_premise`: refuse hateful framing and neutralize premise.
- `has_harmful_comparison` + `has_loaded_premise`: do not choose between biased options.
- `has_negative_language` + `has_emotional_distress`: transform self-insults into feelings without repeating the insult.

### 11.12 Missing Prompt Dictionary Entries

Case:

- active flag has no matching `flag_prompts` entry
- active tone/action/escalation variable is missing from `runtime_variables`
- attached guideline id is missing from `gl-rules.yml`

Expected handling:

- do not fail open
- use a conservative generic safety phrase for the missing variable
- include the missing key in audit/debug metadata
- keep G3/G4 decisions intact
- prefer stricter behavior if the missing value affects safety

Example fallback text:

```text
Use safe, age-appropriate wording. Do not provide harmful instructions. If safety may be involved, ask a brief safety question or direct the child to a trusted adult.
```

### 11.13 Missing Or Invalid Master Template

Case:

- `prompt-master-template.yml` is missing
- required placeholders are absent
- template rendering fails

Expected handling:

- fail closed before model generation
- return structured error metadata to the caller or audit log
- do not call the LLM with a partially rendered prompt
- optionally use a minimal hardcoded emergency fallback prompt only if the product contract explicitly allows it

Required placeholders:

- `{age}`
- `{flag_context}`
- `{tone_instructions}`
- `{action_instructions}`
- `{escalation_instructions}`
- `{flag_guidance}`
- `{flag_example_start}`
- `{attached_guidelines}`

### 11.14 Age Band Missing Or Out Of Range

Case:

- child profile has no age
- age band cannot be resolved
- age is outside configured `age-policy.yaml`

Expected handling:

- use a conservative default age band
- keep language simple and age-safe
- do not change G3/G4 severity because of age
- record the fallback age-band decision

Age policy calibrates style and depth only. It must not downgrade risk.

### 11.15 Classifier Confidence And Backend Fallback

Case:

- trained SLM weights are unavailable
- tokenizer/model load fails
- G1/G2 confidence is low
- thresholding filters out useful labels

Expected handling:

- use configured fallback classifier behavior where available
- preserve fallback reason and error metadata
- if confidence is low and risk signals exist, call safety fallback/verification stages where configured
- never treat backend failure as an allow signal

Runtime may use shadow or fallback classifiers for comparison. Disagreements should be logged and inspected, not silently merged unless explicit promotion logic exists.

### 11.16 Prompt Compliance Failure

Case:

- rendered prompt fails `prompt-rules.yaml`
- prompt includes a forbidden curiosity invite
- prompt includes content not supported by gate outputs
- prompt omits safety check or help-seeking where required

Expected handling:

- repair deterministically if the repair is simple and codebook-supported
- otherwise fail closed or use a safe fallback response
- record failed checklist ids
- do not call the LLM with a non-compliant prompt

### 11.17 Audit And Debug Requirements

For every non-trivial path, audit metadata should include:

- raw classifier labels and scores
- selected G1/G2
- active flags
- intent families and phrases
- G3 packet
- G4 action
- active GL notes
- selected prompt variables
- final template id
- fallback reasons, if any
- prompt compliance result

This is required to debug overlaps and to distinguish classifier mistakes from deterministic gate or prompt-builder mistakes.

## 12. Implementation Invariants

- Classifier predicts `G1`, one selected `G2`, flags, intent families, and intent phrases independently.
- `G1` is nature/topic, not risk.
- `G2` is single-label type/framing/risk pattern.
- Flags are independent predictive signals associated with the input.
- Intent families and phrases support G2 identification; they do not drive deterministic gates directly.
- `G3` is deterministic and comes from `g3.yml`, `g2.yaml`, and active flag mappings.
- `G4` is deterministic and comes from `g4.yml`.
- GL guideline notes come from `gl-rules.yml`.
- Tone/action/escalation candidates come from `flag-mappings.yaml`.
- Runtime variable values and flag prompt fragments come from `prompt-dictionary.yaml`.
- Final prompt text is rendered from `prompt-master-template.yml`.
- Prompt authoring and compliance checks come from `prompt-rules.yaml`.
