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

`G2` is the type/framing of the input.

It answers:

```text
How is the question framed? What is the intent or risk pattern of this query?
```

Examples of G2 framing categories include `NEUTRAL_FACT`, `PERSONAL_DIRECTION`, `DANGEROUS`, `EMOTIONAL`, `GROOMING`, `SELF_HARM`, and `AMBIGUOUS_RISK`.

G2 is the main safety-framing prediction. The classifier may surface a primary selected G2 and supporting G2 evidence, but deterministic gates must read the selected active G2 path from the runtime classifier output.

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

They help identify better G2 predictions by providing intent-pattern evidence. They do not directly decide G3, G4, or final prompt wording.

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

Gate 3 does not add new LOVs. It reads the selected active G2 path, the active flags, and codebook configuration, then produces the packet that Gate 4 consumes.

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

If more than one G2 is active in the runtime packet, severity is the highest severity floor among active G2s.

Example:

```text
If PERSONAL_DIRECTION (SV2) and GROOMING (SV3) both fire, G3_SV = SV3.
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
- selected G2
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

## 10. Implementation Invariants

- Classifier predicts `G1`, `G2`, flags, intent families, and intent phrases independently.
- `G1` is nature/topic, not risk.
- `G2` is type/framing/risk pattern.
- Flags are independent predictive signals associated with the input.
- Intent families and phrases support G2 identification; they do not drive deterministic gates directly.
- `G3` is deterministic and comes from `g3.yml`, `g2.yaml`, and active flag mappings.
- `G4` is deterministic and comes from `g4.yml`.
- GL guideline notes come from `gl-rules.yml`.
- Tone/action/escalation candidates come from `flag-mappings.yaml`.
- Runtime variable values and flag prompt fragments come from `prompt-dictionary.yaml`.
- Final prompt text is rendered from `prompt-master-template.yml`.
- Prompt authoring and compliance checks come from `prompt-rules.yaml`.
