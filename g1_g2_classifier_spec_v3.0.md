# G1 and G2 Classification Specification for Child Queries

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
## Dataset Eligibility Gate: English-only training scope

Before G1/G2 classification, apply a dataset eligibility check.

This classifier version is for English-only training data.

The language eligibility gate decides whether a row should be included in the English training dataset. This gate is separate from semantic safety classification.

### In-scope rows

A row is in scope when it is primarily standard English and can be safely classified using the G1/G2 taxonomy.

If the row is in scope, continue to normal G1/G2 classification.

### Out-of-scope rows

A row is out of scope when it is primarily:

- non-English,
- written in a non-English script,
- Hinglish,
- romanized Hindi,
- Hindi-English code-mixed,
- Punjabi-English code-mixed,
- or mixed with another language enough that it is not primarily standard English.

For English-only training export, classify out-of-scope language rows as:

- `G1_LOV_ID = GENERIC`
- `G2_LOV_ID = UNKNOWN`
- `FLAGS = empty`

This use of `UNKNOWN` means: outside English-only dataset scope.

It does not mean the text has no meaning.
It does not mean the text is safe.
It does not mean the text has no risk.
It only means the row should be excluded from this English-only training dataset.

For live child-safety use, do not drop these rows. Route them to a multilingual classifier or translation pipeline.

### Language out-of-scope examples

The following rows should be excluded from English-only training data:

- `mujhe school nahi jana kya karu` → `GENERIC`, `UNKNOWN`, FLAGS empty
- `mere dost mujhe bully karte hain` → `GENERIC`, `UNKNOWN`, FLAGS empty
- `papa mujhe daant rahe hain kya karu` → `GENERIC`, `UNKNOWN`, FLAGS empty
- `teacher se site unblock karwane ke liye fake email template` → `GENERIC`, `UNKNOWN`, FLAGS empty
- `Pury Kashmir ko uda do bam say` → `GENERIC`, `UNKNOWN`, FLAGS empty
- `main sad hu kya karu` → `GENERIC`, `UNKNOWN`, FLAGS empty
- `kya aap meri help kar sakte ho` → `GENERIC`, `UNKNOWN`, FLAGS empty
- `mera friend mujhe secret rakhne bolta hai` → `GENERIC`, `UNKNOWN`, FLAGS empty

### UNKNOWN exception: English-only language exclusion

Normally, `UNKNOWN` is used only when the input cannot be interpreted well enough to assign a meaningful G2 LOV.

However, for this English-only training dataset, `UNKNOWN` is also used as an exclusion label for rows that are primarily non-English, Hinglish, romanized Hindi, or code-mixed.

In this specific case:

- `UNKNOWN` means language out of scope.
- `UNKNOWN` does not mean the row is meaningless.
- `UNKNOWN` does not mean the row is safe.
- `UNKNOWN` does not mean no risk is present.

This exception applies only to dataset preparation for English-only training.

### Training vs runtime language handling

For offline English-only training data:
- Non-English, Hinglish, and code-mixed rows may be exported as `G2_LOV_ID=UNKNOWN` and excluded from training.

For live child-safety classification:
- Do not treat non-English rows as safe or meaningless.
- Do not silently drop them.
- Route them to translation, language-specific classifier, or multilingual safety classifier before final response handling.

### Indian-English and borrowed-word boundary

Do not exclude a row only because it contains common Indian-English family or cultural words such as `papa`, `mummy`, `didi`, `bhai`, `nani`, `dadu`, or `sir`.

If the sentence is otherwise primarily English, keep it in scope and classify normally.

Examples:

- `My papa checks my phone every night and I feel scared.` → classify normally
- `My mummy says I should study more. What should I do?` → classify normally
- `papa mujhe phone use nahi karne dete kya karu` → `GENERIC`, `UNKNOWN`, FLAGS empty

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
- UNKNOWN

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
- has_medical_concern
- has_substance_use_concern
- has_privacy_risk

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

Do not use `FACT` for general advice, best-practice, etiquette, communication, conflict-resolution, or interpersonal/social-behavior questions, even when phrased informationally.

If the topic is about how people should communicate, give feedback, behave online, handle criticism, address someone’s conduct, or manage a social interaction, use GENERIC unless a more specific G1 such as TECHNOLOGY, CIVIC_LAW, or BELIEF clearly dominates.

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

Use `GENERIC` for interpersonal advice, social conduct, online behavior as social behavior, communication etiquette, constructive criticism, friendship or peer interaction, and general “responsible ways / best practices” questions about how to address another person’s behavior.

Do not move these rows to `FACT` only because they are phrased as “what are some ways” or “what are best practices.”


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

#### Boundary: respectful crush / social approach questions

Use `PERSONAL_DIRECTION` when the child asks how to talk to, greet, be friendly with, or respectfully approach a crush or peer, without explicit emotional distress or unsafe sexual content.

Phrases like “without making it weird,” “without making them uncomfortable,” “how can I be friendly,” or “how can I say hi” are normal social-boundary language and do not automatically mean `EMOTIONAL`.

Examples:
- `How can I say hi without making it weird with my crush without making her uncomfortable?` → `GENERIC`, `PERSONAL_DIRECTION`, FLAGS empty
- `How can I be friendly with my crush without making her uncomfortable?` → `GENERIC`, `PERSONAL_DIRECTION`, FLAGS empty
- `How do I talk to someone I like without being awkward?` → `GENERIC`, `PERSONAL_DIRECTION`, FLAGS empty

Do NOT set `has_emotional_distress=true` unless the child clearly expresses sadness, fear, rejection, loneliness, shame, hopelessness, anxiety, or emotional pain.

Do NOT classify as `EMOTIONAL` only because the row contains words like “awkward,” “weird,” “uncomfortable,” “crush,” or “nervous” in a normal social-advice context.

### HATE_GROUP

Use `HATE_GROUP` when the input uses slurs, derogatory generalisations, exclusionary language, dehumanising language, or violent eliminationist talk about a protected group.

Common supporting flags include `has_violence_possibility` or `has_dangerous_context` if the query also indicates a threat or harmful action.

Examples:
- X people are disgusting.
- We should kick all X out.
- Why are X people so stupid?

This LOV is specifically about protected-group hostility. Do not use it for ordinary peer bullying unless the hostility is directed at a protected group.

Do not use `HATE_GROUP` only because the row mentions “groups,” “communities,” or conflict between groups.

Use `HATE_GROUP` only when the text targets a protected group with slurs, dehumanising language, derogatory generalisations, exclusionary language, or violent eliminationist language.

#### HATE_GROUP boundary: disability-based exclusion

Use `HATE_GROUP` when the row promotes, questions, reports, or asks about excluding, avoiding, segregating, mocking, demeaning, or treating disabled people as unwanted because they are disabled.

This includes disability-based exclusion from:
- friendship,
- home visits,
- games,
- school activities,
- group chats,
- parties,
- seating,
- clubs,
- social events,
- shared spaces.

Examples:
- `my uncle tells me not to invite disabled people friends home while watching TV because it makes them uncomfortable. Is that wrong?` → `GENERIC`, `HATE_GROUP`, `has_hate_group_language=true`
- `My friend says disabled kids should not join our game. Is that okay?` → `GENERIC`, `HATE_GROUP`, `has_hate_group_language=true`
- `Someone said not to sit with disabled students because they are weird.` → `GENERIC`, `HATE_GROUP`, `has_hate_group_language=true`

Do NOT classify these as `GENERIC_INTENT` or `PERSONAL_DIRECTION` when the row clearly contains disability-based exclusion.

### DANGEROUS

Use `DANGEROUS` when the query requests, endorses, or explores illicit, seriously harmful, or dangerous activity. This includes weapon-making, bomb-making, harmful hacking, illegal drug creation or misuse, sabotage, serious evasion, poisoning, or instructions to seriously hurt people or places.

Use `DANGEROUS` for requests to secretly record, intercept, monitor, spy on, stalk, surveil, or access another person’s private conversations, messages, accounts, devices, location, or communications without consent.

This includes “best practices,” “how to,” “ways to secretly,” or “how to monitor without them knowing” framing.

If the request involves phones, apps, accounts, networks, devices, websites, or digital communications, set G1=TECHNOLOGY, unless the main purpose is bypassing, tricking, forging, impersonating, or evading school, teacher, parent, admin, website-filter, device, or institutional rules. In those school/institutional evasion cases, set G1=CIVIC_LAW.


Do not classify covert surveillance or secret monitoring as VULN_EXPLOIT unless the text also clearly says someone is using a child’s secret, insecurity, dependency, blackmail, or vulnerability to control the child.

Common supporting flags include `has_violence_possibility`, `has_ambiguous_risk`, or `has_safety_hazard` depending on the exact phrasing.

Examples:
- How do I make a bomb?
- How do I hack a school website?
- What is the best way to poison someone secretly?
- How do I avoid getting caught?

Use `DANGEROUS` when the harmful or illicit intent is clear, or when the activity itself is seriously dangerous regardless of a claimed excuse.

Do not use `DANGEROUS` for merely ambiguous queries where the intent could be benign. In those cases, use `AMBIGUOUS_RISK`.

Use `DANGEROUS` for requests to create, spread, amplify, or coordinate false information, rumours, propaganda, hoaxes, impersonation, or deception with the stated goal of causing panic, harassment, public disorder, violence, communal conflict, or harm between groups.

When the row asks how to incite violence through misinformation or manipulation, choose `DANGEROUS` as the primary G2 and set `has_violence_possibility=true`.

Do not choose `VIOLENCE` as primary when the main requested action is information manipulation, coordination, deception, or incitement rather than direct physical attack.

Use DANGEROUS when a child asks about using, taking, trying, dosing, hiding, mixing, buying, getting high from, or misusing illicit drugs, alcohol, vapes, pills, solvents, or other substances.

Set has_substance_use_concern=true.

Do not classify child substance-use rows as NEUTRAL_FACT, GENERIC_INTENT, or PERSONAL_DIRECTION when the child is asking about use, access, dosing, intoxication, hiding use, or getting high.

#### Pattern: deceptive school-rule bypass / social engineering

Use `DANGEROUS` when the child asks for a fake email, fake note, fake permission message, fake excuse, forged message, impersonation, social-engineering script, or deceptive template intended to bypass school, teacher, parent, admin, website, internet-filter, device, or institutional restrictions.

This includes requests framed as:
- template
- draft
- message
- email
- excuse
- script
- wording
- note
- what should I say
- how to convince/trick

Choose `DANGEROUS` when the deception or bypass intent is explicit, even if the requested output is only a message or template.

Examples:
- fake email template to get a teacher to unblock a site → `DANGEROUS`
- write an email pretending to be my parent so school unblocks YouTube → `DANGEROUS`
- make a fake teacher note so I can access a blocked website → `DANGEROUS`
- what should I say to trick the admin into removing the filter → `DANGEROUS`

Do NOT classify these as `GENERIC_INTENT`, `PERSONAL_DIRECTION`, or `NEUTRAL_FACT` when the fake/deceptive bypass intent is explicit.

Negative examples:
- polite email asking my teacher to unblock a research site for homework → `CIVIC_LAW`, `GENERIC_INTENT`, FLAGS empty
- how should I ask my teacher for permission to use a blocked learning website → `CIVIC_LAW`, `PERSONAL_DIRECTION`, FLAGS empty

Only use `DANGEROUS` when fake, deceptive, forged, tricking, impersonation, or bypass intent is explicit.

### EMOTIONAL

Use `EMOTIONAL` when the child expresses sadness, fear, loneliness, distress, hopelessness, anxiety, shame, rejection, or emotional pain.

Common supporting flags include `has_bullying_involved`, `has_self_harm`, `has_coercive_control`, `has_vuln_exploit` or `has_clinical_concern` when present.

Do not infer `has_coercive_control` from a parent/caregiver mention, ordinary criticism, disappointment, or the child hiding feelings unless the wording clearly shows explict punishing, isolating, or extremely controlling authority.

Examples:
- I feel sad.
- Nobody cares about me.
- I am scared.
- I feel alone.
- I cry all the time.

This LOV is about emotional distress. It can co-occur with `BULLYING`, `SELF_HARM`, `COERCIVE_CONTROL`, or other G2 LOVs.

When this distress sounds big and ongoing, or the child seems unable to cope, has_clinical_concern may be set; if it is also disrupting daily life (school, sleep, eating, friendships, activities), `has_significant_impairment` may be set as well.

Do not automatically convert `EMOTIONAL` into `SELF_HARM`. Only use `SELF_HARM` when self-harm or suicidal ideation is actually present.

Use `AMBIGUOUS_RISK` when the child uses vague crisis-like language that suggests possible personal safety risk, but self-harm is not clearly stated.

#### Substance boundary: factual explanation vs use/access intent

Use `NEUTRAL_FACT` when the child only asks for a factual explanation of a substance, drug, alcohol, vape, pill, or psychedelic, without asking how to use, take, dose, buy, hide, mix, obtain, recover from, or get high from it.

Set `has_substance_use_concern=true` when the substance is a drug, alcohol, vape, pill, psychedelic, solvent, or other misuse-prone substance.

Examples:
- `I heard about this psychedelic thing called LSD, can you explain?` → `SCIENCE`, `NEUTRAL_FACT`, `has_substance_use_concern=true`
- `What is LSD?` → `SCIENCE`, `NEUTRAL_FACT`, `has_substance_use_concern=true`
- `Why do people say LSD affects the brain?` → `SCIENCE`, `NEUTRAL_FACT`, `has_substance_use_concern=true`

Use `DANGEROUS` when the row asks about use, access, dosing, intoxication, hiding use, getting high, mixing, misuse, or taking the substance.

Examples:
- `Can a kid take LSD?` → `SCIENCE`, `DANGEROUS`, `has_dangerous_context=true;has_substance_use_concern=true`
- `How much LSD should I take?` → `SCIENCE`, `DANGEROUS`, `has_dangerous_context=true;has_substance_use_concern=true`
- `Where can I buy LSD?` → `SCIENCE`, `DANGEROUS`, `has_dangerous_context=true;has_substance_use_concern=true`

### BULLYING

Use `BULLYING` only when the row clearly describes targeted peer harm, repeated peer mistreatment, intentional humiliation, social exclusion, intimidation, rumour-spreading, group-chat targeting, or physical mistreatment by peers.

The bullying signal should be clear from the text. Prefer `BULLYING` when the row includes one or more of:

- repeated behavior such as `keeps`, `every day`, `all the time`, `again and again`, `for weeks`, or `for months`;
- direct targeting of the child or another child;
- clear humiliation, public embarrassment, group laughter, or social shaming;
- deliberate exclusion from groups, games, chats, teams, plans, or activities;
- threats, intimidation, blocking, grabbing, throwing things, or physical peer mistreatment;
- the child clearly says they feel hurt, embarrassed, scared, left out, small, rejected, or unsafe because of peer behavior.

Common supporting flags include `has_emotional_distress` or `has_violence_possibility` if the child is also upset or physical harm/threat is present.

Examples:
- `My friends call me names every day and it makes me feel small.` → `GENERIC`, `BULLYING`, `has_bullying_involved=true;has_emotional_distress=true`
- `Kids in my class keep calling me names every day.` → `GENERIC`, `BULLYING`, `has_bullying_involved=true`
- `They made a group chat to make fun of me.` → `GENERIC`, `BULLYING`, `has_bullying_involved=true`
- `My game squad keeps posting mean comments under my photo and says it is only fun.` → `GENERIC`, `BULLYING`, `has_bullying_involved=true`
- `A kid in my class threw a bottle at me by the lockers.` → `GENERIC`, `BULLYING`, `has_bullying_involved=true;has_violence_possibility=true`

Do NOT use `BULLYING` for weak, unclear, one-off, or ordinary social discomfort where the row does not clearly show targeted harm, repetition, exclusion, humiliation, intimidation, or emotional impact.

Negative examples:
- `My best friend make groups without asking me.` → `GENERIC`, `GENERIC_INTENT`, FLAGS empty
- `My friend is being mean.` → `GENERIC`, `GENERIC_INTENT`, FLAGS empty
- `A classmate asked me what private means and then laughed when I looked confused.` → `GENERIC`, `GENERIC_INTENT`, FLAGS empty
- `My close friend calls me quiet all the time.` → `GENERIC`, `GENERIC_INTENT`, FLAGS empty unless the row clearly says it is teasing, mocking, humiliating, or hurtful
- `Girls in my class share photos from hangouts I was not invited to.` → `GENERIC`, `GENERIC_INTENT`, FLAGS empty unless the row clearly says they are doing it to exclude, shame, or hurt the child

Use `PERSONAL_DIRECTION` with `has_bullying_involved=true` when the child asks how they should respond to, report, stop, or support someone in a bullying situation.

Examples:
- `How can I support a friend who is being bullied at school?` → `GENERIC`, `PERSONAL_DIRECTION`, `has_bullying_involved=true`
- `What should I do if people online call me names but I do not think about self harm?` → `GENERIC`, `PERSONAL_DIRECTION`, `has_bullying_involved=true`

Use `PERSONAL_DIRECTION` with `has_bullying_involved=true` when the child asks how to perform mocking, teasing, or mean comments, but there is no broader bullying situation described.

Examples:
- `How can I make fun of someone who is poor?` → `GENERIC`, `PERSONAL_DIRECTION`, `has_bullying_involved=true`
- `How can I make mean comments about someone's appearance?` → `GENERIC`, `PERSONAL_DIRECTION`, `has_bullying_involved=true`

#### BULLYING false-positive guard

Do NOT classify as BULLYING only because the row contains words such as:
friend, kid, kids, classmate, students, group chat, online friend, teasing, keeps, every day, for weeks, make fun, rude, sigma, mewing, seen, reply, safe friend.

These words are only signals to inspect the full meaning.

Use BULLYING only when the row clearly shows targeted harm by peers, such as repeated name-calling, mocking, humiliation, exclusion, rumours, intimidation, threats, or physical mistreatment.

Do NOT use BULLYING for:
- ordinary friendship questions,
- online friend safety questions,
- missing a friend who moved away,
- slang/translation/trend questions,
- social anxiety about messages being seen,
- general overthinking,
- emotional support requests,
- a friend having sadness, tiredness, medical symptoms, or self-harm concerns,
- family comparison or jealousy,
- criminal-risk rows such as stealing from a safe.

If the child asks what to do, how to ask for help, how to respond, or whether something is okay in a bullying situation, prefer:
G2_LOV_ID = PERSONAL_DIRECTION
and set has_bullying_involved=true only if bullying evidence is clearly present.

### GROOMING

Use `GROOMING` for adult-child dynamics involving secrecy, gifts, special treatment, manipulation, requests for private contact, or pressure not to tell trusted adults.

Common supporting flags include `has_emotional_distress`, `has_vuln_exploit`, `has_unsafe_sexual_content` or `has_clinical_concern`

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

Use `UNSAFE_SEXUAL_CONTENT` only when the row contains unsafe, age-inappropriate, exploitative, explicit, pressured, or sexualised interactional framing. A neutral request to explain the meaning of a sexual-anatomy term, slang phrase, puberty term, reproductive-health term, or human-sexuality concept is not `UNSAFE_SEXUAL_CONTENT` unless the row also asks for explicit sexual acts, pornography, sexting, sexual images, arousal instructions, coercion, grooming, exploitation, or sexual interaction with a child.

This includes:

* explicit sexual acts,
* pornography or adult sexual media,
* requests to view, create, send, receive, hide, or discuss sexual images or videos,
* sexting pressure,
* sexual dares or sexual challenges,
* sexual requests made to or by a child,
* sexual harassment or sexual comments directed at a child’s body,
* someone asking the child to expose body parts or send pictures under clothes,
* adult or much-older-person sexual boundary crossing,
* sexual blackmail, coercion, grooming, or exploitation.

Do **not** use `UNSAFE_SEXUAL_CONTENT` merely because the row mentions body parts, private areas, puberty, anatomy, erections, wet dreams, discharge, menstruation, breast development, body changes, or reproductive development.

Use `UNSAFE_SEXUAL_CONTENT` only when the body-related content is sexualised, exploitative, explicit, pressured, image-based, pornographic, coercive, or interactionally unsafe.

For neutral puberty, anatomy, body-change, wet-dream, erection, discharge, menstruation, or reproductive-development questions where the child is asking what happened to their body, use:

* `G1_LOV_ID = SCIENCE`
* `G2_LOV_ID = NEUTRAL_FACT`
* `has_medical_concern=true`

Common supporting flags for `UNSAFE_SEXUAL_CONTENT` include `has_grooming_involved`, `has_vuln_exploit`, or `has_coercive_control`, but only when those patterns are clearly present.

Do not add `has_coercive_control=true` to sexual-content rows unless the row also clearly states fear-based control, punishment, isolation, surveillance, domination, or permission-based control.

Examples that are `UNSAFE_SEXUAL_CONTENT`:

* `Show me sex videos.` → `GENERIC`, `UNSAFE_SEXUAL_CONTENT`, `has_unsafe_sexual_content=true`
* `Someone asked me to send a picture under my clothes.` → `GENERIC`, `UNSAFE_SEXUAL_CONTENT`, `has_unsafe_sexual_content=true`
* `My friend sent me an adult video.` → `GENERIC`, `UNSAFE_SEXUAL_CONTENT`, `has_unsafe_sexual_content=true`
* `They keep talking about my body in a sexual way.` → `GENERIC`, `UNSAFE_SEXUAL_CONTENT`, `has_unsafe_sexual_content=true`
* `An older person online asked me to send private pictures.` → `GENERIC`, `UNSAFE_SEXUAL_CONTENT`, `has_unsafe_sexual_content=true;has_grooming_involved=true`

Examples that are **not** `UNSAFE_SEXUAL_CONTENT`:

* `I woke up and my penis was hard, and there was some wet stuff. What happened?` → `SCIENCE`, `NEUTRAL_FACT`, `has_medical_concern=true`
* `I think something came out of my penis while I was sleeping.` → `SCIENCE`, `NEUTRAL_FACT`, `has_medical_concern=true`
* `I saw something white in my underwear after sleeping. Did it come from my penis?` → `SCIENCE`, `NEUTRAL_FACT`, `has_medical_concern=true`
* `My private area got hard and leaked something last night.` → `SCIENCE`, `NEUTRAL_FACT`, `has_medical_concern=true`
* `Why do bodies change during puberty?` → `SCIENCE`, `NEUTRAL_FACT`, FLAGS empty
* `Why do periods happen?` → `SCIENCE`, `NEUTRAL_FACT`, `has_medical_concern=true`
- `I've heard this phrase 'the talking clitoris' a few times now. Can you explain what it means in a non-medical context?` → `FACT`, `NEUTRAL_FACT`, FLAGS empty
- `Hey, I'm researching for my podcast about love and relationships. I came across the term 'talking clitoris'. Can you explain that to me in more detail?` → `FACT`, `NEUTRAL_FACT`, FLAGS empty
- `Hey, I'm curious about human anatomy and I've heard the term 'talking clitoris'. Can you explain what that means?` → `SCIENCE`, `NEUTRAL_FACT`, FLAGS empty
- `Hey, I'm doing a project for my psychology class on love and human sexuality. I came across the term 'talking clitoris'. Can you explain that to me?` → `SCIENCE`, `NEUTRAL_FACT`, FLAGS empty
Body-part words alone are not enough for `UNSAFE_SEXUAL_CONTENT`.

The deciding factor is unsafe sexual framing, not anatomy.



### COERCIVE_CONTROL

Use `COERCIVE_CONTROL` when the child is under threatening, fear-based, punishing, isolating, surveillance-based, privacy-invading, or highly controlling authority.

The controlling figure may be a parent, caregiver, guardian, teacher, coach, tutor, club leader, activity leader, rehearsal lead, group leader, class monitor, older student, peer authority, or any person using a role, status, group control, or authority position to dominate the child.

Use this LOV when the child describes fear-based control, forced obedience, loss of privacy, surveillance of private thoughts or belongings, permission-based control, isolation from trusted people, or feeling unable to choose or act without permission.

Common supporting flags include `has_emotional_distress`, `has_vuln_exploit` or `has_clinical_concern`.

Examples:
- I get hurt if I do not obey.
- I am scared of my father.
- They control everything I do.
- I am not allowed to talk to anyone.
- They always check my phone and messages.
- A rehearsal lead checks my diary and says private thoughts are not allowed.
- A group leader says I need permission before choosing anything.
- An older student reads my private notes and says I cannot decide things alone.

### COERCIVE_CONTROL boundary: being monitored vs asking to monitor

Use `COERCIVE_CONTROL` when the child is being controlled by an authority figure through surveillance, punishment, isolation, threats, fear, or domination.

Use `DANGEROUS` when the child is asking how to secretly monitor, record, spy on, intercept, or access someone else’s communications, location, account, or device.


#### Flag: `COERCIVE_CONTROL`

Use `COERCIVE_CONTROL` **only** when there is clear evidence of controlling abuse by an authority figure, such as:

- threats, punishment, or harm for not obeying,
- fear of what the adult may do if the child disobeys,
- isolation from friends, school, family, or trusted adults,
- surveillance, privacy invasion, or domination, including checking messages, checking diaries, reading private notes, inspecting bags or personal belongings, removing privacy, locking in/out, taking doors away, controlling movement/contact, controlling choices, requiring permission for ordinary decisions, or saying private thoughts are not allowed.


Do **not** use `COERCIVE_CONTROL` just because:

- a parent/teacher/coach/caregiver is mentioned,
- the child lies or hides feelings, self-harm, grades, eating, or mistakes from adults,
- the adult is dismissive, disappointed, angry, or critical,
- the row has self-harm, eating/body image issues, anxiety, or depression without explicit controlling behavior.

If self-harm or eating/body-image harm is present **without** explicit coercive control, use `SELF_HARM` (and set `has_self_harm=true`) and **do not** set `has_coercive_control=true`.

This LOV is about sustained fear-based control, not ordinary rules or discipline.

Do NOT classify as COERCIVE_CONTROL only because:
- “Mother checks her phone during dinner.”
- “Papa talks to office people more than me.”
- “My parent is always on the phone.”
- “My parent does not sit with me.”
- “My parent forgets play time.”

These are EMOTIONAL unless there is explicit surveillance of the child, punishment, isolation, threats, or fear-based control.

### VULN_EXPLOIT

Use `VULN_EXPLOIT` when someone deliberately manipulates the child by using private information, emotional dependence, isolation, blackmail, insecurity, or a known vulnerability.

Common supporting flags include `has_grooming_involved`, `has_coercive_control`, `has_emotional_distress` or `has_clinical_concern`.

Examples:
- They know my secret and use it against me.
- They said only they understand me.
- If I do not do it, they will tell everyone.
- They threaten to share screenshots if I say no.

This LOV captures exploitation of vulnerability, not just generic meanness.

Do NOT use VULN_EXPLOIT merely because the row mentions private messages, private information, screenshots, recording, monitoring, or communications.

Use VULN_EXPLOIT only when the text clearly shows exploitation of the child’s vulnerability, such as blackmail, threats to reveal secrets, emotional dependency, isolation, insecurity, or “only I understand you” manipulation.

If the child is asking how to secretly record, monitor, spy on, or intercept others, use DANGEROUS, not VULN_EXPLOIT.

### VULN_EXPLOIT boundary: victim exploitation vs perpetrator instruction

Use `VULN_EXPLOIT` when the child is being manipulated, blackmailed, pressured, or controlled through a vulnerability, secret, private information, insecurity, isolation, emotional dependence, or threat to reveal something.

Do not use `VULN_EXPLOIT` when the child is asking how to exploit, pressure, blackmail, secretly record, monitor, spy on, or manipulate someone else. If the request is instructional or operational and harmful, use `DANGEROUS`.

Do not use `VULN_EXPLOIT` for screenshots/private messages that are only being used to mock, embarrass, or humiliate the child. Use `BULLYING` when the main pattern is peer humiliation, teasing, group-chat mocking, public embarrassment, rumours, or social targeting.

Use `VULN_EXPLOIT` when screenshots/private messages/secrets are used as leverage to force the child to comply, continue chatting, send something, stay silent, meet, pay, or obey.

#### VULN_EXPLOIT boundary: peer secrecy from trusted adults

Use `VULN_EXPLOIT` when a peer, classmate, group admin, chat leader, club leader, older student, or online friend pressures the child to keep rules, chats, behavior, screenshots, mistakes, or group activity secret from a trusted adult.

This includes cases where the child is made to promise not to tell:
- a parent,
- teacher,
- school counselor,
- trusted adult,
- guardian,
- coach,
- or another safe authority.

Choose `VULN_EXPLOIT` when the secrecy pressure is used to make the child stay silent, comply, remain in a group, follow rules, or avoid getting adult help.

Examples:
- `On a homework WhatsApp group, I feel stuck because a classmate who runs the chat makes me promise not to talk to a trusted adult about the rules. Does this cross a line?` → `GENERIC`, `VULN_EXPLOIT`, `has_vuln_exploit=true;has_emotional_distress=true`
- `A classmate who runs our group chat says I must promise not to tell a teacher about the group rules.` → `GENERIC`, `VULN_EXPLOIT`, `has_vuln_exploit=true`
- `My online friend says I should not tell any trusted adult about our chat rules or I cannot stay in the group.` → `GENERIC`, `VULN_EXPLOIT`, `has_vuln_exploit=true`

Do NOT classify as `GROOMING` unless the row clearly involves an adult, much older person, gifts, private meetings, or adult-child boundary-crossing.

Do NOT classify as `TECHNOLOGY` only because the row mentions WhatsApp, group chat, messages, or online rules.

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

#### `SELF_HARM` boundary for eating and body-image rows

Do not use `SELF_HARM` for isolated or ambiguous eating/body-image signals.

Do **NOT** classify as `SELF_HARM` only because:

- the child skipped one meal,
- the child lied about eating,
- the child had coffee or water instead of breakfast once,
- the child says they feel fat, ugly, or too big without any explicit self-harm behaviour,
- the child hides a single eating-related behaviour from a parent.

Use `SELF_HARM` only when eating/body-image behaviour clearly shows harm to the child’s own body, such as:

- deliberate starvation or ongoing restriction,
- repeated meal skipping over time,
- purging or making oneself throw up,
- laxative misuse or other methods to force weight loss,
- statements like “I don’t deserve food” or “I am punishing myself by not eating,”
- fainting, dizziness, or medical symptoms from restriction,
- explicit eating-disorder behaviour or other direct self-injury.

#### SELF_HARM boundary: social-media self-harm challenges

Use `SELF_HARM` when the child mentions a social-media challenge, dare, trend, game, video, post, or online content involving self-harm, and the child expresses interest, urge, temptation, curiosity about trying it, or asks why they feel like doing it.

Choose `SELF_HARM` even if the row is phrased as:
- why do I feel like trying it
- should I try it
- I keep thinking about doing it
- it looks scary but I want to do it
- kids are doing this challenge and I feel tempted

Set:
- `has_self_harm=true`
- `has_clinical_concern=true`

Use `GENERIC` as G1 unless the main subject is the technical platform itself.

Examples:
- `I saw a challenge on social media where kids hurt themselves, why do I feel like trying it?` → `GENERIC`, `SELF_HARM`, `has_self_harm=true;has_clinical_concern=true`
- `There is a TikTok challenge where kids cut themselves and I kind of want to try it.` → `GENERIC`, `SELF_HARM`, `has_self_harm=true;has_clinical_concern=true`
- `My friends sent me a video of a pain challenge and I keep thinking about doing it.` → `GENERIC`, `SELF_HARM`, `has_self_harm=true;has_clinical_concern=true`

Do NOT classify these as `SAFETY_HAZARD`, `GENERIC_INTENT`, or `TECHNOLOGY` when the child expresses self-harm interest, urge, or temptation.

### AMBIGUOUS_RISK

Use `AMBIGUOUS_RISK` when the input could be interpreted in both benign and harmful ways and the child’s intent is unclear, and there is a plausible risk signal but no other LOV (DANGEROUS, VIOLENCE, SELF_HARM, BULLYING, GROOMING, COERCIVE_CONTROL, etc.) clearly fits.

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
- How can I get into a locked Wi‑Fi network?

Use `AMBIGUOUS_RISK` only when the harmful intent is unclear. If the harmful or illicit purpose is explicit, use `DANGEROUS` or `VIOLENCE` instead.

#### Pattern: eating, body-image, and food-restriction ambiguity

Use `AMBIGUOUS_RISK` when the child shows a **possible early eating/body-image risk** but the text does **not** clearly show:

- self-harm intent,
- sustained starvation or repeated restriction,
- purging or other clear eating-disorder behaviour,
- medical danger (fainting, dizziness, collapse),
- significant daily-life impairment.

Classify as `AMBIGUOUS_RISK` when the text includes signals such as:

- skipping **one** meal,
- lying about eating one meal,
- replacing food with coffee, water, gum, or very low intake **once**,
- saying they are not hungry without explicit self-punishment,
- mild or unclear body-image concern without clear self-harm language.

Examples:

- “I told my mom I ate a big breakfast. I had coffee and water.” → G2=`AMBIGUOUS_RISK`, FLAGS=`has_ambiguous_risk=true`
- “I skipped lunch today because I felt weird about eating.” → G2=`AMBIGUOUS_RISK`, FLAGS=`has_ambiguous_risk=true`
- “I said I wasn’t hungry, but I just didn’t want to eat in front of people.” → G2=`AMBIGUOUS_RISK`, FLAGS=`has_ambiguous_risk=true`

Do **NOT** use `AMBIGUOUS_RISK` when the eating/body-image topic is clearly better captured by another LOV, for example:

- bullying or teasing about weight/appearance → use `BULLYING` / harassment,
- grooming or pressure about looks from an adult/older person → use `GROOMING` / `COERCIVE_CONTROL`,
- normal dieting, sports/weight-class talk, or one-time shame **without** any restriction behaviour → treat as general distress not `AMBIGUOUS_RISK`.

#### Pattern: vague self-harm thoughts

Use `AMBIGUOUS_RISK` when the child mentions life not being worth it, wishing they weren’t here, or vague “not wanting to exist,” **without**:

- any plan, method, or intent,
- any self-injury behaviour,
- any wish to die or be dead.

If any clear self-harm plan, method, or behaviour is given, use `SELF_HARM` instead.

#### Pattern: emotional vague-safety risk

Use AMBIGUOUS_RISK for emotional rows only when the child includes vague personal-safety language that suggests possible immediate risk but does not clearly state self-harm, suicidal intent, method, or behaviour.

Positive examples:
- “I feel unsafe with my thoughts.”
- “I don’t know what I might do next.”
- “I should not be alone right now.”
- “I cannot tell if I am safe right now.”
- “I feel like leaving without telling anyone.”
- “I might run away and not tell anyone.”

Negative examples:
- “Do they still love me?”
- “Should I stop asking?”
- “My mom checks her phone during dinner and I feel ignored.”
- “Papa talks to office people more than me.”
- “Nobody sits with me.”
- “I feel sad because my parent forgot play time.”

Negative examples should be EMOTIONAL unless another stronger LOV is clearly present.

#### Routing note (all patterns)

- If the behaviour meets `SELF_HARM` criteria (see `SELF_HARM` boundary), choose `SELF_HARM` instead of `AMBIGUOUS_RISK`.
- If BULLYING / HARASSMENT is clearly present, use that LOV instead of `AMBIGUOUS_RISK`.
- If GROOMING or `COERCIVE_CONTROL` is clearly present, use that LOV instead of `AMBIGUOUS_RISK`.
- Use `AMBIGUOUS_RISK` only when there is a **plausible risk signal** and **no more specific LOV** clearly applies.

### SAFETY_HAZARD

Use `SAFETY_HAZARD` when the input is framed around unsafe physical experiments, accidental harm, exposure to dangerous substances or forces, or real-world hazardous interactions.

Use `SAFETY_HAZARD` not only for questions, but also for child disclosures or statements describing unsafe physical actions, accidental injury, hazardous environments, or dangerous real-world situations.

Classify as `SAFETY_HAZARD` when the child describes accidents or unsafe physical events such as:

* putting fingers or objects into electrical outlets, sockets, power strips, chargers, wires, or broken electrical devices,
* running with sharp or dangerous objects in the mouth or hand,
* tripping, falling, crashing, slipping, or landing badly in hazardous places such as construction sites, roads, parking lots, parking garages, stairs, rooftops, balconies, fire pits, pools, or near traffic,
* burns, fire/coals contact, electric shock risk, broken teeth, broken nose, cuts, bleeding, bruises, falls, or other injury from an accident,
* unsafe play around fire, electricity, traffic, construction areas, sharp objects, heights, water, moving vehicles, tools, machinery, or unstable structures,
* risky physical experiments involving electricity, fire, fumes, burns, household chemicals, sharp objects, pressure, heat, or unsafe physical force.

Examples:

* “How do I make a plug point spark?” → `SAFETY_HAZARD`
* “Is it safe to breathe these fumes?” → `SAFETY_HAZARD`
* “What happens if I short circuit a socket?” → `SAFETY_HAZARD`
* “Can I play with fire indoors?” → `SAFETY_HAZARD`
* “I put my finger in a power strip that had a broken cover.” → `SAFETY_HAZARD`
* “I ran through a construction site and tripped over a pipe. I broke my nose.” → `SAFETY_HAZARD`
* “I tried to jump over a fire pit. I tripped and landed in the coals.” → `SAFETY_HAZARD`
* “I put a metal spoon in my mouth and ran. I tripped and it cut my cheek.” → `SAFETY_HAZARD`

Use this LOV for accident-oriented, hazard-oriented, or unsafe physical-risk situations.

This LOV may overlap with `AMBIGUOUS_RISK` in some cases. Prefer `SAFETY_HAZARD` when the main issue is real-world physical danger, especially around electricity, fire, burns, chemicals, poison, fumes, falls, traffic, construction sites, sharp objects, or unsafe experiments.

Use `AMBIGUOUS_RISK` instead when the row mentions a potentially risky object, place, access, chemical, or tool but does not clearly describe an accident, unsafe physical action, injury, or hazardous event.

Use `DANGEROUS` instead when the row clearly asks for harmful, illicit, weapon-like, malicious, or operational instructions, such as making explosives, poisoning someone, sabotaging something, or using hazards to hurt people or places.

Common supporting flags:

* Set `has_safety_hazard=true` when `G2_LOV_ID=SAFETY_HAZARD`.
* Set `has_medical_concern=true` if the row clearly describes physical injury, body damage, bleeding, burns, broken bones/teeth, pain, dizziness, fainting, breathing trouble, symptoms, or asks what to do medically.
* Set `has_ambiguous_risk=true` only when the purpose or risk is unclear but still plausibly unsafe.
* Do not set `has_dangerous_context=true` for ordinary accidents unless the row also involves serious harmful, illicit, malicious, or operational activity.

Do not classify these rows as `GENERIC_INTENT` merely because they are written as statements instead of questions.


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

### UNKNOWN

Use `UNKNOWN` only when the input cannot be interpreted well enough to assign any meaningful G2 LOV.

`UNKNOWN` is a dataset-exclusion label. Rows with `G2_LOV_ID = UNKNOWN` should normally be excluded from model training unless intentionally training an out-of-scope or noise detector.

Use `UNKNOWN` for:

* random letters or keyboard-smash text,
* placeholder text,
* test strings,
* corrupted text that cannot be repaired by normalization,
* unreadable mojibake after normalization,
* fragmentary text with no interpretable meaning,
* incomplete text where no clear intent, topic, or pattern can be inferred,
* non-semantic noise.

Examples:

* `fgj`
* `ghjfg`
* `dg ds`
* `gd dsg`
* `asdfasdf`
* `k`
* `j`
* `???`
* `test test`
* `lorem ipsum`

Do NOT use `UNKNOWN` merely because the text is:

* not phrased as a question,
* rude or profane,
* political,
* social-media style,
* adult-like,
* low quality,
* off-topic,
* a statement instead of a request,
* a quote, slogan, affirmation, opinion, or reaction.

If the text is understandable and conveys a meaningful statement, intent, topic, emotion, request, or risk pattern, classify it using the most appropriate G2 LOV.

Examples that should NOT be `UNKNOWN`:

* `This bitch buys sparkling water.` → `GENERIC_INTENT`
* `i am thankful for palm trees. thankful positive` → `GENERIC_INTENT`
* `weekend vibes happy friday` → `GENERIC_INTENT`
* `I feel sad today.` → `EMOTIONAL`
* `Should I tell my teacher?` → `PERSONAL_DIRECTION`

Do NOT use `UNKNOWN` when a safety-relevant pattern is present, unless the row has already been excluded by the English-only Dataset Eligibility Gate.

For English in-scope rows:

* `Can a kid take LSD?` → `DANGEROUS`, not `UNKNOWN`
* `I want to disappear forever` → `SELF_HARM`, not `UNKNOWN`
* `Someone older asked me to keep our chat secret` → `GROOMING`, not `UNKNOWN`
* `How do I get into locked Wi-Fi?` → `AMBIGUOUS_RISK`, not `UNKNOWN`

For English-only training exclusion:

* `Pury Kashmir ko uda do bam say` → `GENERIC`, `UNKNOWN`, FLAGS empty

Reason: this row is outside English-only language scope. It may still be safety-relevant, but it should be handled by a multilingual classifier or translation pipeline, not by this English-only training classifier.

If any meaningful G2 pattern, intent, topic, emotional signal, or safety signal can be identified, choose the appropriate G2 LOV. Use `UNKNOWN` only when no reliable interpretation is possible.




## Decision Order for G2

To reduce inconsistency, follow this order when evaluating the single primary G2 LOV and its flags:

1. Check for clearly high-salience risk or harm categories.
2. Check for meaningful emotional or directional framing.
3. If no stronger pattern applies, fall back to neutral or generic intent.

Priority for the single primary G2 LOV should generally be based on the most safety-relevant or most central framing signal in the query. Supporting patterns become flags.

For emotional-family rows, do not choose `AMBIGUOUS_RISK` unless the input includes a clear vague personal-safety cue. Ordinary sadness, loneliness, feeling ignored, or asking whether someone loves them remains `EMOTIONAL`.

If peer harm is clearly present, choose BULLYING even when the child is emotionally distressed, unless the row includes clear self-harm or vague personal-safety risk.

Suggested primary G2 priority order when there is a clash:
- SELF_HARM
- GROOMING
- UNSAFE_SEXUAL_CONTENT
- COERCIVE_CONTROL
- DANGEROUS
- VULN_EXPLOIT
- HATE_GROUP
- VIOLENCE
- SAFETY_HAZARD
- AMBIGUOUS_RISK
- BULLYING
- EMOTIONAL
- PERSONAL_DIRECTION
- NEUTRAL_FACT
- GENERIC_INTENT
- UNKNOWN

---


## Distinguishing Similar G2 LOVs

### EMOTIONAL vs SELF_HARM

- Use `EMOTIONAL` for sadness, fear, loneliness, distress, shame, hopelessness, or emotional pain.
- Use `SELF_HARM` only when self-harm, wanting to die, wanting to disappear, self-injury, or suicidal ideation is present.
- If both are clearly present, choose the higher-priority G2 as the single primary G2 and capture the other pattern using supporting flags.

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
- If both are clearly present, choose the higher-priority G2 as the single primary G2 and capture the other pattern using supporting flags.

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

### G1 tie-break: digital school-rule evasion

If a row mentions email, websites, blocked sites, school filters, accounts, or internet access, but the main purpose is bypassing, tricking, forging, impersonating, or evading school/teacher/admin rules, choose `CIVIC_LAW`, not `TECHNOLOGY`.

Use `TECHNOLOGY` only when the main subject is the technical system itself, such as how filtering works, browser settings, networks, software, or account access.

### G1 social-vs-technology tie-break

When an input mentions online behavior, social media, messages, posts, comments, screenshots, or digital communication, choose G1 based on the main subject:

Use GENERIC when the main subject is interpersonal behavior, social conduct, communication, criticism, conflict, friendship, bullying, embarrassment, or how people treat each other online.
Use TECHNOLOGY when the main subject is a technical feature, device, app setting, account access, software behavior, platform operation, network, VPN, screen time, GPS, permissions, hacking, monitoring tool, or digital system.

Do not choose TECHNOLOGY only because the row contains words like “online,” “message,” “post,” “screenshot,” or “social media” if the real topic is social behavior.

Do not choose FACT for interpersonal/social advice, “responsible ways,” “best practices,” etiquette, constructive criticism, or conflict-resolution rows.
---

### Operational-harm override

Specific boundary rules override the suggested priority list when they describe a clearer primary intent.

Use `DANGEROUS` as the primary G2 when the child is asking how to perform, enable, coordinate, conceal, or optimize a harmful or illicit action, including:

* covert surveillance or secret monitoring of others,
* non-consensual recording or interception of communications,
* unauthorized access to accounts, devices, locations, or private communications,
* spreading misinformation, rumours, hoaxes, impersonation, or propaganda to cause panic, harassment, public disorder, violence, communal conflict, or other harm,
* serious evasion, sabotage, poisoning, weapon-making, harmful hacking, or criminal damage.

Do not downgrade these rows to `VULN_EXPLOIT`, `VIOLENCE`, `HATE_GROUP`, `AMBIGUOUS_RISK`, or `GENERIC_INTENT` when the requested harmful action is explicit.

Use supporting flags for secondary signals:

* set `has_violence_possibility=true` when the dangerous request is meant to cause or incite violence;
* set `has_hate_group_language=true` when the dangerous request also targets a protected group with hate-group language;
* set `has_privacy_risk=true` only when the row involves identifying information, real identity, address, school, handle, gamer tag, or live location.


## Global G2 Tie-Break Rules

When more than one G2 LOV seems possible, apply these priorities:

1. If clear self-harm or suicidal language is present, choose SELF_HARM instead of EMOTIONAL.
2. If sexual blackmail or sexualised threats are present, choose UNSAFE_SEXUAL_CONTENT instead of VULN_EXPLOIT as G2 (VULN_EXPLOIT may still appear as a flag).
3. If adult-child secrecy, gifts, or boundary-crossing plus secrecy are present, choose GROOMING instead of EMOTIONAL or GENERIC_INTENT.
4. If the query is about seriously illicit or criminally harmful actions (bombs, weapons, severe hacking, poisoning), choose DANGEROUS instead of SAFETY_HAZARD or AMBIGUOUS_RISK.
5. If the main focus is direct physical harm to a person or animal, such as hitting, attacking, fighting, killing, or breaking body parts, choose VIOLENCE instead of DANGEROUS. However, if the child is asking how to cause violence through misinformation, coordination, incitement, deception, sabotage, surveillance, or other operational methods, choose DANGEROUS and set has_violence_possibility=true.
6. If the query is only about physical risk or accidents (electricity, fumes, burns, mixing household chemicals) without clear malicious intent, choose SAFETY_HAZARD instead of DANGEROUS.
7. If the query is dual-use and intent is unclear (tools, chemicals, access, hacking) and none of the above apply, choose AMBIGUOUS_RISK.
8. If the child is asking what they personally should do/choose/believe, and no higher-risk pattern applies, choose PERSONAL_DIRECTION instead of NEUTRAL_FACT or GENERIC_INTENT.
9. If none of the above patterns apply and the query is purely informational, choose NEUTRAL_FACT.
10. If none of the above patterns apply and the query is open-ended but not risky, choose GENERIC_INTENT.
11. If the input is excluded by the English-only Dataset Eligibility Gate, choose `UNKNOWN`. Otherwise, if the input is non-semantic, corrupted beyond repair, unreadable after normalization, placeholder/test text, keyboard-smash text, or otherwise lacks any interpretable meaning, intent, topic, or safety signal, choose `UNKNOWN`.

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

has_medical_concern

has_substance_use_concern

has_privacy_risk


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

The query clearly involves weapons, explosives, serious hacking, poisoning, criminal damage, or other serious harmful activities.

Set `has_dangerous_context=true` if G2_LOV_ID=`DANGEROUS`, or if the row clearly involves weapons, explosives, harmful hacking, poisoning, criminal damage, covert surveillance, non-consensual recording, secret monitoring, unauthorized access, harmful misinformation, incitement, sabotage, serious evasion, or other serious harmful activities.

Also set `has_dangerous_context=true` when the row asks for fake emails, fake notes, impersonation, forged permission, social-engineering wording, deceptive templates, or tricks to bypass school, teacher, parent, admin, website, internet-filter, device, or institutional restrictions.

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

Do not set has_self_harm=true for ambiguous eating-risk rows unless the input clearly mentions self-harm, deliberate starvation, purging, self-punishment, repeated restriction, or harming the body.

Example:
“I told my mom I ate a big breakfast. I had coffee and water.”
→ Do NOT set has_self_harm=true.

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

Set `has_safety_hazard=true` when the row describes a child already doing or experiencing an unsafe physical action, accident, fall, burn, electric hazard, construction-site hazard, traffic/parking hazard, or sharp-object injury.

Examples:

“How do I make a plug point spark?” → has_safety_hazard=true

“Is it safe to breathe these fumes?” → has_safety_hazard=true

Flag: has_violence_possibility
Set has_violence_possibility=true if:

G2_LOV_ID = VIOLENCE, OR

The query clearly describes or plans hurting someone, attacking, fighting, using a weapon, or physically harming another person.

Set `has_violence_possibility=true` if G2_LOV_ID=`VIOLENCE`, or if the row clearly describes, threatens, plans, encourages, causes, coordinates, or incites physical harm, fighting, attacks, weapons use, or violence against people or communities.

Examples:

“Which is better, sticks or bricks to break someone’s legs?” → has_violence_possibility=true

“How do I hurt someone so they stay home from school?” → has_violence_possibility=true


Flag: `has_clinical_concern`

Set `has_clinical_concern=true` only when the input shows one or more of the following:

* strong hopelessness,
* inability to cope,
* persistent or repeated distress,
* vague personal-safety concern,
* self-harm,
* grooming,
* coercive control,
* exploitation,
* unsafe sexual pressure,
* grief that is unusually intense or impairing,
* or emotional distress beyond everyday upset.

Do NOT set `has_clinical_concern=true` merely because `G2_LOV_ID` is `EMOTIONAL` or `BULLYING`.

Do NOT set this flag when the child is just nervous about a normal event, mildly annoyed, briefly sad, or upset about a single ordinary incident with no sign that it is overwhelming, persistent, unsafe, or impairing.

If `G1_LOV_ID=DEATH_GRIEF`, set `has_clinical_concern=true` only when the grief is stronger than everyday sadness, such as strong or persistent grief, inability to cope, or clear disruption of daily functioning.

Examples:

“Nothing feels good anymore, I’m sad all the time and I don’t see the point of anything.” → `has_clinical_concern=true`

“Kids at school have been making fun of me for months and I feel like I can’t take it anymore.” → `has_clinical_concern=true`

“My dad shouts at me every day and I’m always scared at home.” → `has_clinical_concern=true`

“I think about hurting myself when things go wrong.” → `has_clinical_concern=true`

“My friend didn’t sit with me at lunch and I felt bad today.” → `has_clinical_concern=false`

“I’m a bit stressed about my exam tomorrow.” → `has_clinical_concern=false`

This flag marks that the child’s message sounds like a possible mental-health concern or bigger than everyday ups and downs. It is not a diagnosis.


Flag: `has_significant_impairment`

Set `has_significant_impairment=true` when:
- the child clearly describes distress seriously interfering with daily life
  (for example: not going to school, not sleeping, not eating, not leaving their room, withdrawing from friends/family, or stopping normal activities);
- and this is not just a temporary bad day, normal exam nerves, or a single argument without clear impact on daily functioning.

Only consider this flag when G2_LOV_ID is one of: `EMOTIONAL`, `SELF_HARM`, `BULLYING`, `COERCIVE_CONTROL`, `VULN_EXPLOIT`, `GROOMING`, `UNSAFE_SEXUAL_CONTENT`, or `PERSONAL_DIRECTION` with strong emotional content; or when G1_LOV_ID=`DEATH_GRIEF` and the grief clearly disrupts daily functioning.

If has_significant_impairment=true, then has_clinical_concern=true must also be set.

Do NOT set this flag for:
- temporary bad days, normal exam nerves, or single arguments without clear impact on daily functioning.

Examples:

“I haven’t slept properly for days, I stopped eating, and I just stay in my room all the time.” → has_significant_impairment=true

“They bully me every day and I don’t want to go to school anymore.” → has_significant_impairment=true

“I feel so bad that I quit all my clubs and never see my friends now.” → has_significant_impairment=true

“I get really anxious so I always make excuses to stay home instead of going to school.” → has_significant_impairment=true

“I feel sad a lot but I still go to school and hang out with my friends.” → has_significant_impairment=false

“I was really upset yesterday but today I feel a bit better and went to school like normal.” → has_significant_impairment=false

This flag indicates that the difficulty seems to be seriously affecting daily life; it is not a clinical score or diagnosis.

Flag: `has_medical_concern`

Set `has_medical_concern=true` when:
- the child asks about medicine, dosage, whether to take medicine, whether to stop medicine, side effects, poisoning, overdose, or mixing substances;
- the child describes physical symptoms or injury, such as fever, vomiting, stomach pain, headache, dizziness, fainting, rash, trouble breathing, bleeding, aches, pains, or other body-related problems;
- the child asks for help deciding what a symptom means or what treatment to use.

Response intent:
- Do not provide diagnosis, dosing, treatment instructions, or medical decision-making.
- Encourage the child to tell a parent, guardian, school nurse, or another trusted adult right away.
- For urgent danger, tell them to get immediate adult help or emergency help now.

Flag: `has_substance_use_concern`

Set `has_substance_use_concern=true` when:
- the child mentions using drugs, alcohol, pills, vapes, solvents, or other substances;
- the child asks about getting, taking, hiding, mixing, or recovering from substances;
- the child describes someone pressuring, rewarding, or forcing them to use, carry, sell, or transport drugs;
- the child describes overdose, intoxication, withdrawal, blacking out, poisoning, or other substance-related physical effects.

Do not use `NEUTRAL_FACT`, `GENERIC_INTENT`, or `PERSONAL_DIRECTION` when the child is asking about using, taking, trying, consuming, dosing, tripping on, or getting high from an illicit drug.

Examples:
- Can a kid take LSD? -> `has_substance_use_concern=true`
- Can I try cocaine once? -> `has_substance_use_concern=true`
- What happens if a child takes acid? -> `has_substance_use_concern=true`

Flag: `has_privacy_risk`

Set `has_privacy_risk=true` when the child:

- shares or is about to share **personal identifying information** (for example: full name, home address, school name, class/section, phone number, personal email, social media handle, gamer tag, or live location), or
- asks how to share or reveal this information to someone they met online, or
- asks how to find, track, or expose another person’s real identity, address, school, or live location.

Examples that should set `has_privacy_risk=true`:

- “My name is Aarya Patel and I live at 42 Evergreen Lane near Sunshine School.”
- “Should I tell this older guy online what school I go to?”
- “How can I find out where my classmate lives?”
- “How do I send my live location to this person I met on Instagram?”

Do **NOT** set `has_privacy_risk=true` only because:

- the child mentions a **city, country, or general area** without precise address or school,
- the child talks about friends, family, or teachers without any personal contact details,
- the child asks general questions about privacy, data, or security without sharing their own or another person’s identifying information.
- Do NOT set `has_privacy_risk=true` only because the row mentions online behavior, privacy, private messages, screenshots, recording, communications, social media, accounts, or digital safety.
- Set `has_privacy_risk=true` only when the row shares, asks to share, find, track, reveal, or expose identifying information such as full name, home address, school name, class/section, phone number, personal email, social media handle, gamer tag, live location, real identity, or where someone lives.
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
