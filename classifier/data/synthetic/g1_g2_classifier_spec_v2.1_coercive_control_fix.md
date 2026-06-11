# G1 and G2 Classification Specification for Child Queries

Version note: v2.1 coercive-control precision patch. This patch tightens `COERCIVE_CONTROL` and `has_coercive_control` so parent/caregiver mentions, hidden self-harm, hidden eating behavior, or ordinary criticism do not trigger coercive-control without explicit fear-based control evidence.

## Purpose

This document is the machine-readable operational specification for classifying a child query into **Gate 1 (G1)** and **Gate 2 (G2)** labels, plus supporting flags. It is designed to be consumed by a language model or other classifier that must assign labels strictly from the approved List of Values (LOV).

This document is not a policy essay and not a free-form safety guide. It is an execution spec. The classifier must follow the LOVs exactly as written here and must not invent, rename, merge, split, or substitute labels.

The classifier has three jobs:

1. Assign exactly **one** G1 LOV.
2. Assign exactly **one** G2 LOV.
3. Assign supporting flags in the third output column.

The classifier must remain inside the Codebook. It must not import outside taxonomies, moderation schemas, or inferred labels. If uncertain, it must choose the closest valid LOV from the approved set rather than inventing a new category.

---

## Scope

This specification applies to short or long child-authored inputs, including:

- direct questions,
- emotional disclosures,
- descriptive statements,
- requests for advice,
- requests for factual explanation,
- ambiguous queries,
- risky or safety-sensitive phrasing.

The task is classification only. The classifier is not being asked to answer the child, provide help, or perform moderation. It is only being asked to assign correct G1 and a single G2 LOV, plus any supporting flags, based on the wording and meaning of the input.

---

## Core Principles

### Principle 1: G1 and G2 answer different questions

- **G1** answers: "What is the broad subject matter of this input?"
- **G2** answers: "How is this input framed? What intent, risk pattern, or conversational shape does it contain?"

G1 is about topic. G2 is about framing.

A single input always has one broad subject matter, even if it also contains emotional or risky framing. That broad subject matter should be captured in G1. The framing and risk patterns should be captured in G2.

### Principle 2: G1 is single-label

Only one G1 LOV may be emitted for each input. The classifier must choose the best-fit broad topic.

### Principle 3: G2 is single-label with auxiliary flags

Exactly one G2 LOV must be emitted for each input. If more than one framing pattern is present, the classifier must choose the most important one as the primary G2 LOV and express the rest as supporting flags. The flags provide additional context but do not change the single G2 label.

Do not output a list of G2 labels. Do not use multi-label G2 output.

### Principle 4: Do not over-label

The classifier should not emit extra G2 LOVs merely because they are loosely related. A LOV should be emitted only when the query clearly expresses that framing or risk pattern.

### Principle 5: Do not under-label

If the input clearly expresses more than one G2 pattern, retain the strongest one as the G2 LOV and capture the rest as flags. For example, a child may be both distressed and bullied, or may be asking for personal direction while also describing grief.

### Principle 6: Stay inside the LOV set

The classifier must use only the LOV IDs defined in this document.

Allowed G1 LOV IDs:
- FACT
- BELIEF
- DEATH_GRIEF
- SCIENCE
- TECHNOLOGY
- CIVIC_LAW
- GENERIC

Allowed G2 LOV IDs:
- NEUTRAL_FACT
- PERSONAL_DIRECTION
- HATE_GROUP
- DANGEROUS
- EMOTIONAL
- BULLYING
- GROOMING
- UNSAFE_SEXUAL_CONTENT
- COERCIVE_CONTROL
- VULN_EXPLOIT
- SELF_HARM
- AMBIGUOUS_RISK
- SAFETY_HAZARD
- VIOLENCE
- GENERIC_INTENT

Allowed support flags:
- has_hate_group_language
- has_dangerous_context
- has_emotional_distress
- has_bullying_involved
- has_grooming_involved
- has_unsafe_sexual_content
- has_coercive_control
- has_vuln_exploit
- has_self_harm
- has_ambiguous_risk
- has_safety_hazard
- has_violence_possibility
- has_clinical_concern
- has_significant_impairment

No other labels or flags are allowed.

---

## G1 Classification Rules

## G1 Overview

G1 captures the main subject matter of the child input. The classifier should ask:

**What is this mostly about?**

The answer must be exactly one G1 LOV.

If more than one G1 could fit, the classifier should select the label that best captures the main subject. If no specific G1 clearly fits, use `GENERIC`.

## G1 LOVs

### FACT

Use `FACT` for pure factual or descriptive questions about the world, especially when they do not fit more specific topic buckets like science, technology, belief, death/grief, or civic/law.

Use `FACT` when the input is mainly a request for information and the topic is general rather than strongly scientific, technological, civic, or belief-based.

Examples:
- What is a mountain?
- Why do people sleep?
- Who was the first person to fly?

Do not use `FACT` when a more specific G1 LOV is clearly a better fit.

### BELIEF

Use `BELIEF` for religion, ideology, worldview, spirituality, values systems, or belief-based identity and doctrine.

Examples:
- What do Christians believe?
- Why do people believe in reincarnation?
- Should I follow this religion?

If the subject is mainly religion or ideology, `BELIEF` should be chosen even if the query is also asking for personal direction.

### DEATH_GRIEF

Use `DEATH_GRIEF` for death, dying, bereavement, mourning, grief, or loss.

Examples:
- What happens when someone dies?
- Why do I miss my grandma so much?
- How do I deal with my pet dying?

Use this G1 even if the input also contains emotional language. Emotional framing belongs in G2, while the broad topic of loss belongs in G1.

### SCIENCE

Use `SCIENCE` for biology, chemistry, physics, nature, environment, animals, plants, the body, matter, energy, or general natural science.

Examples:
- How do volcanoes erupt?
- Why do magnets attract?
- What happens if I mix these chemicals?

If the input is mainly about scientific mechanisms or natural phenomena, use `SCIENCE` even if the G2 framing may later be `SAFETY_HAZARD`, `AMBIGUOUS_RISK`, or `DANGEROUS`.

### TECHNOLOGY

Use `TECHNOLOGY` for computing, internet systems, AI, software, devices, phones, networks, websites, apps, code, hacking, or digital systems.

Examples:
- How does Wi-Fi work?
- What is artificial intelligence?
- How do I get into a locked Wi-Fi network?

If the main topic is digital or computational, use `TECHNOLOGY` even if the framing is risky or ambiguous.

### CIVIC_LAW

Use `CIVIC_LAW` for law, rules, civic structures, institutions, school or public rules, bribery, cheating, dishonest evasion, or official requirements.

Examples:
- Is it illegal to forge a document?
- What happens if someone bribes a police officer?
- How can I get around school rules?

If the input is mainly about laws, rules, compliance, cheating, or institutional processes, choose `CIVIC_LAW`.

### GENERIC

Use `GENERIC` when none of the other G1 LOVs clearly fit.

This is the fallback G1 category.

Examples:
- I feel alone.
- Kids are mean to me.
- What should I do?

Many interpersonal, emotional, or relational disclosures will fall into `GENERIC` because their main topic is not science, technology, law, belief, death, or broad factual explanation.

---

## G2 Classification Rules

## G2 Overview

G2 captures the framing, intent, and risk pattern of the query. The classifier should ask:

**How is the child saying this? What is the most important framing or safety-relevant pattern?**

Unlike G1, G2 emits exactly one LOV. Additional observed patterns must be represented as flags.

The classifier should choose the single strongest G2 LOV and should avoid adding unsupported labels or unsupported flags.

G2 is not multi-label in this version of the spec.

## G2 LOVs

### NEUTRAL_FACT

Use `NEUTRAL_FACT` when the query is a pure factual or descriptive inquiry with no risk framing, no emotional disclosure, and no personal direction.

Typical flags may be empty. If the input also contains another meaningful framing, `NEUTRAL_FACT` should usually not be the final G2 LOV.

Examples:
- What is lightning?
- How does a battery work?
- Why do leaves fall?

Use this when the query is informational and neutral.

Do not use `NEUTRAL_FACT` if the child is also asking what they personally should do, or if the query includes emotional, harmful, sexual, violent, or other risky framing.

### PERSONAL_DIRECTION

Use `PERSONAL_DIRECTION` when the child is asking what they personally should do, choose, believe, decide, or say.
Queries asking AI for personal validation about attractiveness, dateability, popularity, friendship value, or social worth should be classified as `PERSONAL_DIRECTION` when the child is asking the AI to judge or guide their personal/social identity. If emotional distress is explicit, classify as `EMOTIONAL`.

Common supporting flags include `has_emotional_distress`, `has_ambiguous_risk`, `has_self_harm`, `has_bullying_involved`, or `has_grooming_involved` when clearly present.

Look for phrasing such as:
- should I
- what should I do
- which should I choose
- decide for me
- what is the right choice for me
- tell me what I should do

Examples:
- Should I tell my teacher?
- What should I do about my friend?
- Which religion should I follow?

This LOV can co-occur with many other G2 LOVs. For example, a child can be distressed and also asking for personal direction.

### HATE_GROUP

Use `HATE_GROUP` when the input uses slurs, derogatory generalisations, exclusionary language, dehumanising language, or violent eliminationist talk about a protected group.

Common supporting flags include `has_violence_possibility` or `has_dangerous_context` if the query also indicates a threat or harmful action.

Examples:
- X people are disgusting.
- We should kick all X out.
- Why are X people so stupid?

This LOV is specifically about protected-group hostility. Do not use it for ordinary peer bullying unless the hostility is directed at a protected group.

### DANGEROUS

Use `DANGEROUS` when the query requests, endorses, or explores illicit, seriously harmful, or dangerous activity. This includes weapon-making, bomb-making, harmful hacking, illegal drug creation or misuse, sabotage, serious evasion, poisoning, or instructions to seriously hurt people or places.

#### Deterministic override: illicit drug use or misuse

If the input contains an illicit drug term and a use/consume intent verb, classify the primary G2 as `DANGEROUS`.

This applies even if the input is phrased as a yes/no question, curiosity question, or child-safety question.

Trigger verbs include:
- take
- use
- try
- consume
- get high
- trip
- dose

Examples:
- Can a kid take LSD? → G1=`SCIENCE`, G2=`DANGEROUS`, FLAGS=`has_dangerous_context=true;has_safety_hazard=true`
- Can I try cocaine once? → G1=`SCIENCE`, G2=`DANGEROUS`, FLAGS=`has_dangerous_context=true;has_safety_hazard=true`
- What happens if a child takes acid? → G1=`SCIENCE`, G2=`DANGEROUS`, FLAGS=`has_dangerous_context=true;has_safety_hazard=true`

Do not use `NEUTRAL_FACT`, `GENERIC_INTENT`, `PERSONAL_DIRECTION`, or only `SAFETY_HAZARD` when the child is asking about using, taking, trying, consuming, dosing, tripping on, or getting high from an illicit drug.

Common supporting flags include `has_violence_possibility`, `has_ambiguous_risk`, or `has_safety_hazard` depending on the exact phrasing.

Examples:
- How do I make a bomb?
- How do I hack a school website?
- What is the best way to poison someone secretly?
- How do I avoid getting caught?

Use `DANGEROUS` when the harmful or illicit intent is clear, or when the activity itself is seriously dangerous regardless of a claimed excuse.

Do not use `DANGEROUS` for merely ambiguous queries where the intent could be benign. In those cases, use `AMBIGUOUS_RISK`.

### EMOTIONAL

Use `EMOTIONAL` when the child expresses sadness, fear, loneliness, distress, hopelessness, anxiety, shame, rejection, or emotional pain.

Common supporting flags include `has_bullying_involved`, `has_self_harm`, `has_coercive_control`, or `has_vuln_exploit` only when those patterns are explicitly present. Do not infer `has_coercive_control` from a parent/caregiver mention, ordinary criticism, disappointment, or the child hiding feelings unless the wording clearly shows fear-based, punishing, isolating, or extremely controlling authority.

Examples:
- I feel sad.
- Nobody cares about me.
- I am scared.
- I feel alone.
- I cry all the time.

This LOV is about emotional distress. It can co-occur with `BULLYING`, `SELF_HARM`, `COERCIVE_CONTROL`, or other G2 LOVs.

Do not automatically convert `EMOTIONAL` into SELF_HARM. Use `SELF_HARM` only when self-harm, suicidal ideation, wanting to die, or harming one’s own body is clearly present. Use `AMBIGUOUS_RISK` when the child uses vague crisis-like language that suggests possible personal safety risk, but self-harm is not clearly stated.

### BULLYING

Use `BULLYING` when the input involves peer harm, intimidation, social exclusion, name-calling, humiliation, rumours, social targeting, or physical mistreatment by peers, without hate-group framing.

Common supporting flags include `has_emotional_distress` or `has_violence_possibility` if the child is also upset or speaking about retaliation.

Examples:
- Kids are mean to me.
- They call me names at school.
- No one lets me play.
- They made a group chat to make fun of me.

Use `BULLYING` for peer-targeted interpersonal harm. If the same input also contains emotional pain, `EMOTIONAL` may also apply.

### GROOMING

Use `GROOMING` for adult-child dynamics involving secrecy, gifts, special treatment, manipulation, requests for private contact, or pressure not to tell trusted adults.

Common supporting flags include `has_emotional_distress`, `has_vuln_exploit`, `has_unsafe_sexual_content`, `has_clinical_concern` or `has_unsafe_sexual_content`.

Look for patterns such as:
- an older person wants secrecy,
- an adult gives gifts or money,
- someone older wants to meet alone,
- someone older says parents will not understand,
- there is pressure to hide chats, calls, or the relationship.

Examples:
- An older person gives me gifts and says not to tell anyone.
- Someone much older wants to meet me alone.
- They tell me to keep our chats secret from my parents.

Use `GROOMING` when the adult-child secrecy or manipulation pattern is present.

### UNSAFE_SEXUAL_CONTENT

Use `UNSAFE_SEXUAL_CONTENT` for explicit sexual content, sexual acts, pornography, sexualised body parts, sexual requests, sexual dares, sexting pressure, or requests for sexual images.

Common supporting flags include `has_grooming_involved`, `has_vuln_exploit`, or `has_coercive_control` only when those patterns are explicitly present. Do not add `has_coercive_control` to sexual-content rows unless the row also clearly states fear-based control, punishment, isolation, surveillance, or domination.

Examples:
- Show me sex videos.
- Someone asked me to send a picture under my clothes.
- My friend sent me an adult video.
- They keep talking about my body in a sexual way.

This LOV covers unsafe, age-inappropriate, exploitative, or explicit sexual framing.

It may co-occur with `GROOMING`, `VULN_EXPLOIT`, or `COERCIVE_CONTROL` if those patterns are also clearly present.

### COERCIVE_CONTROL

Use `COERCIVE_CONTROL` when the child is under threatening, fear-based, punishing, isolating, or highly controlling authority. The controlling figure is often a parent, caregiver, guardian, or older authority figure, though other controlling dynamics may also fit.

Common supporting flags include `has_emotional_distress` and `has_vuln_exploit`.

Examples:
- I get hurt if I do not obey.
- I am scared of my father.
- They control everything I do.
- I am not allowed to talk to anyone.
- They always check my phone and messages.

This LOV is about sustained fear-based control, not ordinary rules or discipline.

#### Strict evidence rule for COERCIVE_CONTROL

Use `COERCIVE_CONTROL` only when the text clearly contains at least one explicit coercive-control signal:

- threat, punishment, or harm for non-compliance,
- fear of an authority figure because of what that authority may do,
- isolation from friends, school, family, or trusted adults,
- surveillance or domination such as checking messages, removing privacy, locking in/out, taking doors away, or controlling all movement/contact,
- repeated or sustained controlling pattern rather than a single ordinary argument, criticism, disappointment, or household rule.

Do **not** use `COERCIVE_CONTROL` only because:

- a parent, dad, mom, teacher, coach, or caregiver is mentioned,
- the child lies to a parent or hides an injury, sadness, self-harm, eating behavior, grade, or mistake,
- the parent is dismissive, disappointed, angry, or critical,
- the child says “I told my dad/mom I was fine,” “I told my dad/mom I fell,” or “my mom says I am too thin,”
- the row contains self-harm, eating restriction, body image distress, anxiety, or depression without explicit controlling authority.

If self-harm or eating/body-image harm is present without explicit coercive-control evidence, prefer `SELF_HARM` and set `has_self_harm=true`; do not set `has_coercive_control=true`.

### VULN_EXPLOIT

Use `VULN_EXPLOIT` when someone deliberately manipulates the child by using private information, emotional dependence, isolation, blackmail, insecurity, or a known vulnerability.

Common supporting flags include `has_grooming_involved`, `has_coercive_control`, `has_emotional_distress` or `has_clinical_concern`.

Examples:
- They know my secret and use it against me.
- They said only they understand me.
- If I do not do it, they will tell everyone.
- They threaten to share screenshots if I say no.

This LOV captures exploitation of vulnerability, not just generic meanness.

### SELF_HARM

Use `SELF_HARM` when the child references self-harm, suicidal ideation, wanting to die, wanting to disappear, non-suicidal self-injury, or harming their own body.

Common supporting flags include `has_emotional_distress`, `has_bullying_involved`, `has_violence_possibility` or `has_clinical_concern`.

Examples:
- I want to die.
- I do not want to be here anymore.
- How can I hurt myself?
- How do I make my cuts worse?
- I want to disappear forever.

This LOV should be treated as high priority. Do not miss it when present.

If the input is emotionally distressed but does not mention self-harm, do not use `SELF_HARM`; use `EMOTIONAL` instead.

All SELF_HARM queries should normally set `has_clinical_concern`=true, and may set `has_significant_impairment`=true when the self-harm thoughts or actions are clearly affecting daily life.

### AMBIGUOUS_RISK

Use `AMBIGUOUS_RISK` when the input could be interpreted in both benign and harmful ways and the child’s intent is unclear.

Common supporting flags include `has_dangerous_context`, `has_violence_possibility`, or `has_safety_hazard` when the query is unclear but has a potentially risky surface form.

Common patterns include:
- tools that have safe and unsafe uses,
- chemicals or reactions with unclear purpose,
- access or bypass questions with unclear intent,
- vague disruption or failure questions,
- ambiguous location or entry questions.

Examples:
- Where can I buy a knife?
- How do I get into the locked building?
- What happens if I mix these cleaning liquids?
- How can I get into a locked Wi-Fi network?

Use `AMBIGUOUS_RISK` only when the harmful intent is unclear. If the harmful or illicit purpose is explicit, use `DANGEROUS` or `VIOLENCE` instead.

### SAFETY_HAZARD

Use `SAFETY_HAZARD` when the query is framed around unsafe physical experiments, accidental harm, exposure to dangerous substances or forces, or real-world hazardous interactions.

Common supporting flags include `has_ambiguous_risk` and `has_dangerous_context`.

Examples:
- How do I make a plug point spark?
- Is it safe to breathe these fumes?
- What happens if I short circuit a socket?
- Can I play with fire indoors?

Use this LOV for accident-oriented or hazard-oriented physical risk.

This LOV may overlap with `AMBIGUOUS_RISK` in some cases. Prefer `SAFETY_HAZARD` when the main issue is real-world physical danger, especially around electricity, fire, burns, chemicals, poison, fumes, or unsafe experiments.

### VIOLENCE

Use `VIOLENCE` when the input is framed around interpersonal harm, attacks, threats, weapons, crime, war, terrorism, gangs, or physically hurting someone.

Common supporting flags include `has_dangerous_context`, `has_bullying_involved`, or `has_ambiguous_risk`.

Examples:
- How do I hurt someone?
- What is the best weapon?
- How do gangs punish people?
- How do terrorists attack?
- Is it okay to hit back?

Use `VIOLENCE` when physical harm to people is central to the query.

This can co-occur with `DANGEROUS` when the query is both violent and operationally harmful.

### GENERIC_INTENT

Use `GENERIC_INTENT` as the fallback G2 LOV when the input has no special risk pattern, no emotional disclosure, no personal direction, and is not best captured as `NEUTRAL_FACT`.

This label should usually have no flags or only very weak flags. If a stronger framing exists, `GENERIC_INTENT` should not be the final G2 LOV.

Examples:
- Tell me something interesting.
- What should I learn about next?
- Explain something random.

Do not use `GENERIC_INTENT` if another G2 LOV clearly applies.

---

## Decision Order for G2

To reduce inconsistency, follow this order when evaluating the single primary G2 LOV and its flags:

1. Check for clearly high-salience risk or harm categories.
2. Check for meaningful emotional or directional framing.
3. If no stronger pattern applies, fall back to neutral or generic intent.

Priority for the single primary G2 LOV should generally be based on the most safety-relevant or most central framing signal in the query. Supporting patterns become flags.

Suggested primary G2 priority order when there is a clash:
- SELF_HARM
- GROOMING
- UNSAFE_SEXUAL_CONTENT
- COERCIVE_CONTROL
- VULN_EXPLOIT
- HATE_GROUP
- DANGEROUS
- VIOLENCE
- SAFETY_HAZARD
- AMBIGUOUS_RISK
- EMOTIONAL
- BULLYING
- PERSONAL_DIRECTION
- NEUTRAL_FACT
- GENERIC_INTENT

---


## Distinguishing Similar G2 LOVs

### EMOTIONAL vs SELF_HARM

- Use `EMOTIONAL` for sadness, fear, loneliness, distress, shame, hopelessness, or emotional pain.
- Use `SELF_HARM` only when self-harm, wanting to die, wanting to disappear, self-injury, or suicidal ideation is present.
- If both are present, emit both.

### BULLYING vs HATE_GROUP

- Use `BULLYING` for peer meanness, exclusion, rumours, intimidation, or targeted harassment.
- Use `HATE_GROUP` when the hostility is toward a protected group using derogatory or exclusionary group-based language.
- If a peer-bullying situation explicitly uses protected-group hatred, both may apply if both are clearly present.

### DANGEROUS vs AMBIGUOUS_RISK

- Use `DANGEROUS` when harmful, illicit, or seriously unsafe intent is clear.
- Use `AMBIGUOUS_RISK` when the same query could be benign or harmful and intent is unclear.

Example:
- "How do I make a bomb?" → `DANGEROUS`
- "What chemicals are easy to get?" → `AMBIGUOUS_RISK` if purpose is unclear

### SAFETY_HAZARD vs DANGEROUS

- Use `SAFETY_HAZARD` for unsafe physical experiments, accidents, and hazardous real-world interactions.
- Use `DANGEROUS` for more clearly illicit, harmful, operational, or weapon-like activity.

Example:
- "What happens if I make a socket spark?" → `SAFETY_HAZARD`
- "How do I make an explosive?" → `DANGEROUS`

### GROOMING vs VULN_EXPLOIT

- Use `GROOMING` when there is an adult-child secrecy, gifting, or boundary-crossing dynamic.
- Use `VULN_EXPLOIT` when a manipulator uses secrets, dependency, emotional isolation, or blackmail to control the child.
- If both are clearly present, emit both.

### COERCIVE_CONTROL vs VULN_EXPLOIT

- Use `COERCIVE_CONTROL` for sustained fear-based control, punishment, isolation, surveillance, or domination.
- Use `VULN_EXPLOIT` for targeted use of secrets or emotional dependence to manipulate.
- They may co-occur.

### NEUTRAL_FACT vs GENERIC_INTENT

- Use `NEUTRAL_FACT` for straightforward descriptive or factual questions.
- Use `GENERIC_INTENT` for broad, miscellaneous, or open-ended requests that are not specifically factual.

Example:
- "How do clouds form?" → `NEUTRAL_FACT`
- "Tell me something interesting." → `GENERIC_INTENT`

---

## G1 Tie-Breaking Rules

If more than one G1 appears possible, apply the following tie-break process:

1. Choose the label that best matches the main subject matter.
2. Prefer a specific topical LOV over `GENERIC`.
3. If the subject is clearly digital, use `TECHNOLOGY`.
4. If the subject is clearly chemistry, biology, physics, nature, or the natural world, use `SCIENCE`.
5. If the subject is clearly religion or worldview, use `BELIEF`.
6. If the subject is clearly law, rules, civic systems, cheating, bribery, or official compliance, use `CIVIC_LAW`.
7. If the input is mainly interpersonal or emotional and no other G1 dominates, use `GENERIC`.

---

## Global G2 Tie-Break Rules

When more than one G2 LOV seems possible, apply these priorities:

1. If clear self-harm or suicidal language is present, choose SELF_HARM instead of EMOTIONAL.
2. If sexual blackmail or sexualised threats are present, choose UNSAFE_SEXUAL_CONTENT instead of VULN_EXPLOIT as G2 (VULN_EXPLOIT may still appear as a flag).
3. If adult-child secrecy, gifts, or boundary-crossing plus secrecy are present, choose GROOMING instead of EMOTIONAL or GENERIC_INTENT.
4. If the query is about seriously illicit or criminally harmful actions, including bombs, weapons, severe hacking, poisoning, or illicit drug use/misuse by a child, choose DANGEROUS instead of SAFETY_HAZARD, AMBIGUOUS_RISK, PERSONAL_DIRECTION, NEUTRAL_FACT, or GENERIC_INTENT.
5. If the main focus is hurting a person or animal (fights, attacks, kill, hit, break legs), choose VIOLENCE instead of DANGEROUS.
6. If the query is only about physical risk or accidents (electricity, fumes, burns, mixing household chemicals) without clear malicious intent, choose SAFETY_HAZARD instead of DANGEROUS.
7. If the query is dual-use and intent is unclear (tools, chemicals, access, hacking) and none of the above apply, choose AMBIGUOUS_RISK.
8. If the child is asking what they personally should do/choose/believe, and no higher-risk pattern applies, choose PERSONAL_DIRECTION instead of NEUTRAL_FACT or GENERIC_INTENT.
9. If none of the above patterns apply and the query is purely informational, choose NEUTRAL_FACT.
10. If none of the above patterns apply and the query is open-ended or miscellaneous, choose GENERIC_INTENT.

---

## Fallback Rules

### G1 Fallback

If no G1 LOV clearly fits, use `GENERIC`.

### G2 Fallback

If the query is factual and neutral, use `NEUTRAL_FACT`.

If the query is not risky, not emotional, not directive, and not clearly factual, use `GENERIC_INTENT`.

Do not leave G2 blank unless your downstream system explicitly allows blank G2 output. If a fallback is required, use the most suitable fallback LOV from the approved set.

---

## Output Format Requirements

For each input, the classifier must return:

- `G1_LOV_ID`: exactly one LOV ID
- `G2_LOV_ID`: exactly one LOV ID
- `FLAGS`: zero or more supporting flags, separated in a consistent machine-readable form

Recommended output forms include:

### JSON-style

```json
{
  "G1_LOV_ID": "SCIENCE",
  "G2_LOV_ID": "SAFETY_HAZARD",
  "FLAGS": ["has_ambiguous_risk=true"]
}
```

### CSV-style row

```csv
row_id,input_text,G1_LOV_ID,G2_LOV_ID,FLAGS
1,"What happens if I mix these cleaning liquids?",SCIENCE,SAFETY_HAZARD,"has_ambiguous_risk=true"
```

The classifier must not output unapproved labels, hidden reasoning, or free-form policy commentary unless explicitly requested.

## Supporting Flag Rules

Flag Extraction Rules
Flags are supporting signals derived from the content of the query.
They do not replace G1 or G2, but they help downstream systems interpret the query more precisely.

The classifier must:

Evaluate every allowed flag for every input.

Set a flag to true only when its condition is clearly satisfied.

Omit flags that are not clearly supported by the input.

Do not add a flag only because it is listed as a “common supporting flag” under a G2 category. A common supporting flag still requires explicit evidence from the input text.

Never invent new flags outside the allowed set.

Allowed flags (exact names):

has_hate_group_language

has_dangerous_context

has_emotional_distress

has_bullying_involved

has_grooming_involved

has_unsafe_sexual_content

has_coercive_control

has_vuln_exploit

has_self_harm

has_ambiguous_risk

has_safety_hazard

has_violence_possibility

has_clinical_concern

has_significant_impairment

General flag rules
For each input:

Start with FLAGS as empty.

For each flag below, check its condition.

If the condition is clearly met, add flag_name=true to FLAGS.

If the condition is not clearly met, do not add that flag.

Join all flags that fired into a semicolon‑separated string.

If no flags fire, FLAGS should be empty for that row (no “none”, no “[]”).

Flag: has_hate_group_language
Set has_hate_group_language=true if:

G2_LOV_ID = HATE_GROUP, OR

The query uses slurs, dehumanising language, or sweeping negative statements about a protected group (e.g. “X people are disgusting”, “get rid of X people”).

Examples:

“Why are X people so disgusting?” → has_hate_group_language=true

Flag: has_dangerous_context
Set has_dangerous_context=true if:

G2_LOV_ID = DANGEROUS, OR

The query clearly involves weapons, explosives, serious hacking, poisoning, criminal damage, illicit drug use/misuse, or other serious harmful activities.

Examples:

“How do I make a bomb?” → has_dangerous_context=true

“Which one is better, sticks or bricks to break someone’s legs?” → has_dangerous_context=true

Flag: has_emotional_distress
Set has_emotional_distress=true if:

G2_LOV_ID = EMOTIONAL, OR

The child clearly expresses being sad, scared, lonely, rejected, hopeless, anxious, or in emotional pain (e.g. “I feel alone”, “nobody cares about me”, “I cry all the time”).

Examples:

“Kids are mean to me and I feel really sad.” → has_emotional_distress=true

“I feel alone and nobody cares about me.” → has_emotional_distress=true

Flag: has_bullying_involved
Set has_bullying_involved=true if:

G2_LOV_ID = BULLYING, OR

The query clearly describes peer name‑calling, exclusion, humiliating group chats, rumours, or physical mistreatment by peers.

Examples:

“They call me names and won’t let me play.” → has_bullying_involved=true

Flag: has_grooming_involved
Set has_grooming_involved=true if:

G2_LOV_ID = GROOMING, OR

The query clearly describes an adult or much older person:

giving gifts or money,

asking for secrecy,

wanting private chats or meetings,

telling the child not to tell parents or trusted adults.

Examples:

“An older guy gives me gifts and says not to tell my parents.” → has_grooming_involved=true

Flag: has_unsafe_sexual_content
Set has_unsafe_sexual_content=true if:

G2_LOV_ID = UNSAFE_SEXUAL_CONTENT, OR

The query clearly involves explicit sexual content, porn, sexualised body parts, sexual dares, sexting pressure, or requests for sexual images.

Examples:

“He asked me to send pictures under my clothes.” → has_unsafe_sexual_content=true

Flag: has_coercive_control
Set has_coercive_control=true if:

G2_LOV_ID = COERCIVE_CONTROL, OR

The query clearly describes fear‑based, punishing, isolating, or extremely controlling authority (e.g. “I get hurt if I don’t obey”, “they control everything I do”, “I am not allowed to see any friends”).

Examples:

“My dad hits me if I don’t do exactly what he says.” → has_coercive_control=true

Do **not** set `has_coercive_control=true` for weak or indirect family/authority mentions. The following are negative examples unless additional coercive-control evidence is present:

- “I punched my wall so hard my knuckles are bruised. I told my dad I fell.” → no `has_coercive_control`
- “I think I’m getting fat even though my mom says I’m too thin. I stopped eating breakfast.” → no `has_coercive_control`
- “My mom said ‘you’re so dramatic’ when I told her I couldn’t stop crying.” → no `has_coercive_control`
- “I told my dad I was fine. I had been crying five minutes before.” → no `has_coercive_control`

Positive examples that should set `has_coercive_control=true`:

- “I lied because my dad will hit me if he finds out.”
- “My mom locks me in my room when I cry.”
- “My dad checks all my messages and won’t let me talk to anyone.”
- “I am scared to tell my parents because they will hurt me.”

Flag: has_vuln_exploit
Set has_vuln_exploit=true if:

G2_LOV_ID = VULN_EXPLOIT, OR

The query clearly shows someone:

using a secret to control the child,

threatening to reveal private information,

saying “only I understand you” while demanding compliance,

or otherwise exploiting a known vulnerability or insecurity.

Examples:

“He said he will tell everyone my secret if I don’t do what he wants.” → has_vuln_exploit=true

Flag: has_self_harm
Set has_self_harm=true if:

G2_LOV_ID = SELF_HARM, OR

The query clearly mentions self‑harm, wanting to die, wanting to disappear, cutting, or harming their own body.

Examples:

“I want to die.” → has_self_harm=true

“How do I make my cuts worse?” → has_self_harm=true

Flag: has_ambiguous_risk
Set has_ambiguous_risk=true if:

G2_LOV_ID = AMBIGUOUS_RISK, OR

The query involves dual‑use tools, chemicals, access, or disruption where the purpose could be safe or harmful and intent is unclear.

Examples:

“Where can I buy a knife?” (no clear harmful intent) → has_ambiguous_risk=true

“How do I get into the locked building?” → has_ambiguous_risk=true

Flag: has_safety_hazard
Set has_safety_hazard=true if:

G2_LOV_ID = SAFETY_HAZARD, OR

The query involves risky physical experiments, electricity, fire, fumes, burns, explosions, or other hazardous real‑world interactions.

Examples:

“How do I make a plug point spark?” → has_safety_hazard=true

“Is it safe to breathe these fumes?” → has_safety_hazard=true

Flag: has_violence_possibility
Set has_violence_possibility=true if:

G2_LOV_ID = VIOLENCE, OR

The query clearly describes or plans hurting someone, attacking, fighting, using a weapon, or physically harming another person.

Examples:

“Which is better, sticks or bricks to break someone’s legs?” → has_violence_possibility=true

“How do I hurt someone so they stay home from school?” → has_violence_possibility=true

Flag: has_clinical_concern
Set has_clinical_concern=true if:

G2_LOV_ID is one of: EMOTIONAL, SELF_HARM, BULLYING, COERCIVE_CONTROL, VULN_EXPLOIT, GROOMING, UNSAFE_SEXUAL_CONTENT, OR G1_LOV_ID = DEATH_GRIEF, OR

The query shows more than everyday ups and downs — for example, strong hopelessness, feeling unable to cope, or distress that sounds big and ongoing rather than a one‑off bad day.

Do NOT set this flag when:

The child is just nervous about a normal event (like one test or game), mildly annoyed, or briefly sad about a single incident with no sign it’s overwhelming them.

Examples:

“Nothing feels good anymore, I’m sad all the time and I don’t see the point of anything.” → has_clinical_concern=true

“Kids at school have been making fun of me for months and I feel like I can’t take it anymore.” → has_clinical_concern=true

“My dad shouts at me every day and I’m always scared at home.” → has_clinical_concern=true

“I think about hurting myself when things go wrong.” → has_clinical_concern=true

“My friend didn’t sit with me at lunch and I felt bad today.” → has_clinical_concern=false

“I’m a bit stressed about my exam tomorrow.” → has_clinical_concern=false

This flag marks that the child’s message sounds like a possible mental‑health concern or bigger than everyday ups and downs; it is not a diagnosis.

Flag: has_significant_impairment
Set has_significant_impairment=true if:

has_clinical_concern=true, AND

The query clearly describes distress seriously interfering with daily life — for example: not going to school, not sleeping, not eating, not leaving their room, avoiding everyone, or stopping normal activities they used to do.

Do NOT set this flag when:

The child is distressed but still going to school, seeing friends, and doing usual activities, or when the problem sounds short‑term and not life‑disrupting.

Examples:

“I haven’t slept properly for days, I stopped eating, and I just stay in my room all the time.” → has_significant_impairment=true

“They bully me every day and I don’t want to go to school anymore.” → has_significant_impairment=true

“I feel so bad that I quit all my clubs and never see my friends now.” → has_significant_impairment=true

“I get really anxious so I always make excuses to stay home instead of going to school.” → has_significant_impairment=true

“I feel sad a lot but I still go to school and hang out with my friends.” → has_significant_impairment=false

“I was really upset yesterday but today I feel a bit better and went to school like normal.” → has_significant_impairment=false

This flag indicates that the difficulty seems to be seriously affecting daily life; it is not a clinical score or diagnosis.

---

## Final Instruction to the Classifier

When classifying an input:

1. Read the full input carefully.
2. Assign exactly one G1 LOV based on broad topic.
3. Assign exactly one primary G2 LOV based on framing, intent, and risk, using the priority and tie‑break rules in this spec.
4. Do not invent labels.
5. Do not omit clearly expressed labels.
6. Do not over-label weakly implied categories.
7. Return the result in the requested structured format.

This document is the source of truth for machine classification behavior for G1, the single primary G2 LOV, and supporting flags.
