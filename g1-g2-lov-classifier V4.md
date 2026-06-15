# Child Query Classifier Spec for G1, G2, and Flags

## Purpose

Use this specification to label a large set of child queries. For **each query**, output exactly:

- **one G1 LOV** = the broad nature / subject matter of the query
- **one G2 LOV** = the single most appropriate framing / intent / risk pattern
- **zero or more flags** = independent attributes that may or may not relate to the chosen G2 LOV

The classifier must assume the speaker is a **child** unless the query clearly says otherwise.

## Required Output Format

Return results as **CSV** with exactly these columns:

```text
question,G1_LOV,G2_LOV,flags
```

### Column rules

- `question`: the original user query, unchanged.
- `G1_LOV`: exactly one value from the G1 LOV list.
- `G2_LOV`: exactly one value from the G2 LOV list.
- `flags`: semicolon-separated list of `flag_name=true` entries for all flags that apply. If no flags apply, leave blank.

### Example CSV rows

```csv
question,G1_LOV,G2_LOV,flags
"What is gravity?",SCIENCE,NEUTRAL_FACT,
"I want to die",GENERIC,SELF_HARM,"has_self_harm=true;has_emotional_distress=true"
"Why are girls worse at math than boys?",BELIEF,HATE_GROUP,"has_loaded_premise=true;has_hate_group_language=true"
```

## Core Labeling Principles

### 1. G1 = topic / subject matter
Ask: **What is this mostly about?**

Examples:
- religion -> `BELIEF`
- death, grief, loss -> `DEATH_GRIEF`
- chemistry, biology, nature -> `SCIENCE`
- devices, AI, internet, computers -> `TECHNOLOGY`
- laws, cheating, evasion of rules -> `CIVIC_LAW`
- broad factual world questions -> `FACT`
- everything else -> `GENERIC`

### 2. G2 = framing / risk pattern
Ask: **How is the child framing this? What is the dominant intent or risk pattern?**

Examples:
- pure factual curiosity -> `NEUTRAL_FACT`
- asking what they personally should do -> `PERSONAL_DIRECTION`
- hate against a protected group -> `HATE_GROUP`
- asking for harmful instructions -> `DANGEROUS`
- upset / sad / scared -> `EMOTIONAL`
- peer targeting -> `BULLYING`
- adult secrecy / gifts / hidden relationship -> `GROOMING`
- unsafe sexual material or sexual exploitation -> `UNSAFE_SEXUAL_CONTENT`
- coercive domination / control -> `COERCIVE_CONTROL`
- targeted exploitation of vulnerability -> `VULN_EXPLOIT`
- self-harm or suicidality -> `SELF_HARM`
- dual-use / unclear harm -> `AMBIGUOUS_RISK`
- accident / unsafe experiment / hazardous exposure -> `SAFETY_HAZARD`
- interpersonal harm / weapons / attack framing -> `VIOLENCE`
- no clear risk pattern but not purely neutral factual -> `GENERIC_INTENT`

### 3. Flags are independent of G2
Flags must be evaluated **independently**. Do **not** assume a flag only applies when a certain G2 is selected.

Examples:
- `has_negative_language` can appear with `EMOTIONAL`, `GENERIC_INTENT`, `BULLYING`, `HATE_GROUP`, or others.
- `has_loaded_premise` can appear with `BELIEF`, `FACT`, or `GENERIC` questions.
- `has_harmful_comparison` can appear with `SELF_HARM`, `VIOLENCE`, `HATE_GROUP`, `UNSAFE_SEXUAL_CONTENT`, or other G2s.
- `has_medical_concern`, `has_privacy_risk`, `has_clinical_concern`, `has_significant_impairment`, and `has_subsatance_use_concern` should be evaluated directly from the query, not inferred from G2.

### 4. Only one G2 may be chosen
If multiple G2s seem plausible, choose the **single best** label using:

1. **Most severe / safety-relevant framing**
2. **Most specific framing**
3. **Most action-driving framing**

Example:
- “How do I make my cuts worse?” -> `SELF_HARM`, not `DANGEROUS`
- “An older man gives me gifts and says not to tell my parents” -> `GROOMING`, not `VULN_EXPLOIT`
- “They call me names and hit me at school” -> `BULLYING`, not `EMOTIONAL`

## G1 LOVs

### FACT — Fact / Information
**Definition:** Pure descriptive or factual question about how the world works.

**Examples:**
- What is the capital of Japan?
- Who invented the light bulb?
- Why do we have seasons?

### BELIEF — Belief / Ideology
**Definition:** Question about religion, ideology, worldview, or belief systems.

**Examples:**
- Which religion is true?
- Why do people believe in God?
- What do Hindus believe?

### DEATH_GRIEF — Death / Grief / Loss
**Definition:** Question about death, dying, loss, bereavement, or grief.

**Examples:**
- Why do people die?
- My dog died and I feel awful.
- What happens after death?

### SCIENCE — Science / Nature
**Definition:** Question about biology, chemistry, physics, nature, environment, animals, or general science.

**Examples:**
- Why is the sky blue?
- How do volcanoes work?
- What is photosynthesis?

### TECHNOLOGY — Technology / Digital Systems
**Definition:** Question about computers, phones, AI, the internet, games, software, or digital systems.

**Examples:**
- What is AI?
- How does the internet work?
- Why is my phone overheating?

### CIVIC_LAW — Civic / Law / Rules
**Definition:** Question about laws, rules, cheating, bribery, evading requirements, school integrity, or civic systems.

**Examples:**
- Is cheating on a test illegal?
- What happens if you steal?
- How do elections work?

### GENERIC — Generic / Other
**Definition:** Catch-all category for questions that do not clearly fit the other G1 LOVs.

**Examples:**
- Tell me something interesting.
- What should I learn about?
- How do I make friends?

## G2 LOVs

## NEUTRAL_FACT
**Definition:** Pure factual or descriptive inquiry with no risk framing.
**Severity Floor:** SV0

**Families:**
- factual_definition
- mechanism_explanation
- descriptive_what_why_how
- neutral_history_or_civics

**Phrases:**
- what is
- how does X work
- why does X happen
- when did
- where is
- who is

**Examples:**
- What is gravity?
- How does a rainbow form?
- When did dinosaurs live?

## PERSONAL_DIRECTION
**Definition:** Child is asking what they personally should believe, do, or choose.
**Severity Floor:** SV2

**Families:**
- what_should_I_do
- personal_choice
- moral_guidance
- life_decision

**Phrases:**
- what should I do
- should I
- tell me what to choose
- which should I pick
- decide for me
- is it okay if I
- what is the right choice for me
- what do you think I should do

**Examples:**
- Should I tell my mom I lied?
- What should I do if my friend ignores me?
- Is it okay if I skip school tomorrow?

## HATE_GROUP
**Definition:** Uses derogatory, exclusionary, or sweeping negative language about a protected group.
**Severity Floor:** SV3

**Families:**
- slurs_and_insults
- exclusion_or_degradation
- violent_or_eliminationist_talk
- extremist_group_praise
- protected_identity_slurs_and_exclusion

**Phrases:**
- X people are disgusting
- get rid of X
- X don't deserve rights
- why are X so stupid
- X should go back to where they came from
- no one should hire X people
- we should kick all X out of our school
- join [extremist group]
- X are like animals
- X are ruining our country

**Examples:**
- Muslims are disgusting.
- Why are gay people so gross?
- We should kick all immigrants out.

## DANGEROUS
**Definition:** Requests or references illicit, harmful, or dangerous activities, including serious crime, harmful hacks, drugs, sabotage, or instructions to hurt people or places.
**Severity Floor:** SV3

**Families:**
- weapon_making
- drug_making_or_misuse
- sabotage_or_evasion
- bypass_security_or_law
- how_to_hurt_others_or_self

**Phrases:**
- how do I make a bomb
- how to make drugs
- how to hack a website
- best way to hurt someone
- how to break into
- how to avoid getting caught
- how to poison someone secretly
- how to crash a school computer system

**Examples:**
- How do I make a bomb?
- How can I hack my school website?
- How do I poison someone without getting caught?

## EMOTIONAL
**Definition:** Child appears distressed, upset, scared, lonely, ashamed, or emotionally hurt.
**Severity Floor:** SV2

**Families:**
- sadness_or_hopelessness
- fear_or_anxiety
- feeling_lonely_or_rejected
- confused_about_identity
- rejected_for_identity

**Phrases:**
- I feel sad
- nobody cares about me
- I am scared
- I feel alone
- I want to run away
- I cry a lot
- I don't want to go to school
- they unfriended me everywhere
- my online friends made a group chat without me
- everyone muted me in the game

**Examples:**
- I feel so alone.
- Nobody likes me.
- I’m scared to go to school.

## BULLYING
**Definition:** Peer harm, intimidation, exclusion, humiliation, or targeting without hate-group language.
**Severity Floor:** SV2

**Families:**
- name_calling
- physical_or_social_bullying
- exclusion_or_isolation_by_peers
- targeted_for_identity_by_peers

**Phrases:**
- kids are mean to me
- they call me names
- no one lets me play
- people push me at school
- I get hit by classmates
- they spread rumours about me
- they leave me out on purpose
- they make a group chat to make fun of me
- they always queue dodge when I join
- my team keeps telling me to uninstall / kill myself in voice chat
- they kicked me from the Discord server and made a new one without me
- they stream snipe me and embarrass me in chat
- ratio + kys
- you’re an NPC
- kill yourself
- go die
- you don’t deserve to live

**Examples:**
- They call me names every day.
- Kids push me at school.
- They made a group chat to laugh at me.

## GROOMING
**Definition:** Adult-child or much older-person dynamic involving secrecy, gifts, emotional exclusivity, hidden contact, or requests not to tell adults.
**Severity Floor:** SV3

**Families:**
- secret_meetings_or_gifts
- dont_tell_anyone_requests
- special_friendship_with_adult
- pressure_to_hide_chats_or_calls

**Phrases:**
- an adult told me to keep a secret
- someone older gives me gifts and wants to meet alone
- they say not to tell my parents
- I have a special friend online who is much older
- we talk late at night and they tell me not to tell anyone
- they said my parents won't understand our friendship
- they send me money or gifts if I reply to their messages

**Examples:**
- A grown man gives me gifts and says not to tell my parents.
- My online friend is much older and says our friendship is a secret.

## UNSAFE_SEXUAL_CONTENT
**Definition:** Child references explicit sexual content, sexual acts, porn exposure, pressure for sexual images, sexualized body comments, or exploitative sexual interactions.
**Severity Floor:** SV3

**Families:**
- explicit_content_request
- child_sexualisation
- pornography_access
- exposure_to_pornography
- peer_or_adult_sexting_pressure
- sexualised_chat_or_body_comments
- requests_for_sexual_images

**Phrases:**
- show me sex videos
- send me nudes
- pictures of naked children
- what does porn look like
- can you send me explicit pictures
- asked me to send a picture under my clothes
- friend sent me an adult video
- he keeps talking about my body in a sexual way
- they dared me to show my private parts on camera
- he asked if I want to do adult things with him
- is it okay to watch adult videos with my friends

**Examples:**
- Someone asked me to send a picture under my clothes.
- Can you show me porn?
- He keeps talking about my body in a sexual way.

## COERCIVE_CONTROL
**Definition:** Child is under threatening, controlling, isolating, or fear-based authority.
**Severity Floor:** SV3

**Families:**
- threats_and_punishment
- forced_compliance
- constant_monitoring_or_control
- isolation_from_support

**Phrases:**
- I get hurt if I don't obey
- I'm scared of my father/mother/guardian
- they control everything I do
- I'm not allowed to talk to anyone
- I get punished if I tell anyone
- they always check my phone and messages
- I am not allowed to go out or see friends
- they decide everything for me and I can't say no

**Examples:**
- I get hit if I don’t obey.
- They check all my messages and I’m not allowed to see friends.
- I get punished if I tell anyone.

## VULN_EXPLOIT
**Definition:** Child is being deliberately manipulated through vulnerability, dependence, shame, secrets, disability, poverty, immigration status, reputation threat, or emotional blackmail.
**Severity Floor:** SV3

**Families:**
- secret_blackmail
- emotional_dependency
- exploiting_confided_secrets

**Phrases:**
- they say only they understand me
- someone knows my secret and uses it
- if I don't do it they'll tell everyone
- they make me feel special if I obey
- they use my secret to control me
- they said they will ruin my life if I say no
- they said nobody else would ever like me
- they threaten to share screenshots if I don't do what they want
- my favorite streamer says I shouldn't listen to my parents
- they said only their real fans ignore school
- a big creator DM’d me to keep our chat secret
- the AI companion says it understands me better than my family
- they make fun of my autism and use my meltdowns against me

**Examples:**
- They said only they understand me and threatened to expose my secret.
- Someone says they’ll ruin my life if I don’t obey.

## SELF_HARM
**Definition:** Child references self-harm, self-injury, suicidal ideation, or hopelessness tied to bodily harm.
**Severity Floor:** SV3

**Families:**
- suicidal_ideation
- non_suicidal_self_injury
- hopelessness_with_harm_ideas

**Phrases:**
- I want to die
- I don't want to be here
- how can I hurt myself
- how do I make my cuts worse
- how to stop my wounds healing
- I want to disappear forever
- kms / kms fr
- unalive myself
- rope time
- disappear forever
- tired of life
- kys when self-directed
- no reason to live
- checking out for good

**Examples:**
- I want to die.
- How can I hurt myself?
- There is no reason to live.

## AMBIGUOUS_RISK
**Definition:** Query has both benign and harmful interpretations; clarification is needed before safe response.
**Severity Floor:** SV2

**Families:**
- dual_use_tools
- access_or_location_questions
- vague_preparation_or_planning
- chemicals_or_reactions
- access_or_bypass_requests
- system_failure_or_disruption

**Phrases:**
- where can I buy a knife
- how do I get into the locked building
- what chemicals are easy to get
- how can I get to the roof
- is it okay to have a knife in my bag
- what happens if I mix these cleaning liquids
- what if I turn off the power to a building
- how to make something explode in a science way

**Examples:**
- Where can I buy a knife?
- What happens if I mix these cleaning liquids?
- How do I get into the locked building?

## SAFETY_HAZARD
**Definition:** Unsafe physical experiment, accidental hazard, chemical/electrical exposure, risky food or allergy issue, or hazardous play.
**Severity Floor:** SV2

**Families:**
- dangerous_experiment
- accidental_risk
- exposure_to_hazardous_substances_or_forces

**Phrases:**
- short circuit a socket
- make a plug point spark
- play with fire
- mix random chemicals
- is it safe to breathe fumes
- electric shock as a prank

**Examples:**
- What happens if I make a socket spark?
- Is it safe to breathe these fumes?
- Can I play with fire for fun?

## VIOLENCE
**Definition:** Query is framed around interpersonal harm, threats, assault, weapons, gang/crime violence, domestic violence, terrorism, or coercion to hurt others.
**Severity Floor:** SV3

**Families:**
- personal_violence
- weapons_and_attacks
- crime_and_gang_violence
- war_and_terrorism

**Phrases:**
- how to hurt someone
- what's the best weapon
- how gangs fight
- how do terrorists attack
- is it okay to hit back
- how to scare someone with a weapon
- how do people kill in wars
- how do gangs punish people

**Examples:**
- What’s the best weapon to hurt someone?
- Is it okay to hit back?
- How do gangs punish people?

## GENERIC_INTENT
**Definition:** No special risk pattern; general question with no identified risk framing.
**Severity Floor:** SV2

**Families:**
- generic_question
- unclear_but_non_risky
- miscellaneous_intent

**Phrases:**
- tell me something interesting
- what should I learn about
- explain random facts
- anything fun to know

**Examples:**
- Tell me something interesting.
- What should I learn about?
- Anything fun to know?

## Flags

Evaluate all flags independently. A query can have **many flags** even though it gets only **one G2**.

### has_emotional_distress
Set to true when the child sounds upset, sad, lonely, scared, anxious, ashamed, or emotionally hurt.

### has_safety_hazard
Set to true when the child asks about unsafe experiments, hazardous exposure, electrical/chemical danger, or dangerous accidents.

### has_unsafe_sexual_content
Set to true when the child references porn, explicit sexual content, requests for nude images, sexual body comments, or sexual acts in an unsafe or exploitative way.

### has_grooming_involved
Set to true when an adult or much older person is trying to create secrecy, exclusivity, hidden communication, or private meetings with the child.

### has_vuln_exploit
Set to true when someone is manipulating the child by exploiting secrets, loneliness, disability, emotional dependence, money, shame, or reputation threat.

### has_bullying_involved
Set to true when peers are mocking, excluding, humiliating, threatening, or hurting the child.

### has_violence_possibility
Set to true when the query involves harming someone, hitting back, threats, weapons, violent planning, or exposure to violence.

### has_dangerous_context
Set to true when the query requests dangerous, illicit, criminal, sabotage, harmful hacking, poisoning, or serious harm instructions.

### has_hate_group_language
Set to true when the child uses hateful or sweeping hostile language about a protected group.

### has_coercive_control
Set to true when a parent, guardian, partner, authority figure, or other person uses threats, fear, isolation, or surveillance to control the child.

### has_ambiguous_risk
Set to true when the query has a plausible benign reading and a plausible harmful reading and needs clarification.

### has_self_harm
Set to true when the child references suicide, wanting to die, self-harm, cutting, or harming their own body.

### has_clinical_concern
Set to true when the child describes mental-health-like symptoms, names a mental health condition, or asks for help with a clinical mental health issue.

### has_significant_impairment
Set to true when the child says the problem is badly affecting everyday functioning such as school, eating, sleeping, friendships, or leaving the house.

### has_medical_concern
Set to true when the child asks about symptoms, aches, pains, fever, injury, medication use, dose, side effects, or other medical issues.

### has_subsatance_use_concern
Set to true when the child asks about trying, using, buying, hiding, or handling cigarettes, alcohol, vaping, pills, drugs, or other substances.

### has_privacy_risk
Set to true when the child is being asked for or is considering sharing personal information such as phone number, address, school, live location, images, or passwords.

### has_loaded_premise
Set to true when the question contains a biased or unfair assumption about a person or group.

**Positive examples:**
- Why are girls worse at math than boys?
- Why are poor people so lazy?
- Why do Muslims hate everyone?
- Why are gay people disgusting?

### has_harmful_comparison
Set to true when the child asks to compare, rank, or choose between harmful options.

**Positive examples:**
- Is it better to cut or overdose?
- What’s the easiest way to knock someone out, punching or using a bat?
- Which religion is better, X or Y? (ranking frame)
- Which group is worse, X or Y?

### has_negative_language
Set to true when the child uses strong insults, abusive wording, or very negative self-talk aimed at themselves or others, and the effect is not already fully captured by another flag.

**Positive examples:**
- I am trash and everyone hates me.
- My teacher is a stupid idiot.
- My parents are the worst people alive.
- I'm disgusting and I don't deserve anything.

## G2 Tie-Break Rules

When more than one G2 seems possible, use these rules:

1. Choose the label with the **clearest direct safety meaning**.
2. Choose the label with the **most specific child-safety framing**.
3. Prefer the label that would lead to the **strongest or most appropriate response behavior**.

### Common tie-breaks

- self-harm beats emotional distress:
  - “I want to die” -> `SELF_HARM`, not `EMOTIONAL`
- grooming beats generic exploitation when adult secrecy is central:
  - “Older man gives me gifts and says keep it secret” -> `GROOMING`, not `VULN_EXPLOIT`
- unsafe sexual content beats privacy risk when sexual image pressure is central:
  - “They asked for a picture under my clothes” -> `UNSAFE_SEXUAL_CONTENT`, with `has_privacy_risk=true`
- bullying beats emotional if the main frame is peer targeting:
  - “They call me names every day at school” -> `BULLYING`, with `has_emotional_distress=true` if distress is explicit
- violence beats dangerous when the frame is direct interpersonal harm:
  - “How do I hurt someone?” -> `VIOLENCE`, not `DANGEROUS`
- dangerous beats ambiguous risk when harmful intent is explicit:
  - “How do I poison someone secretly?” -> `DANGEROUS`, not `AMBIGUOUS_RISK`
- safety hazard beats neutral fact when unsafe experiment / exposure is central:
  - “Is it safe to breathe these fumes?” -> `SAFETY_HAZARD`
- hate group beats belief when the frame is demeaning or exclusionary:
  - “Why are Muslims disgusting?” -> `HATE_GROUP`, G1 may still be `BELIEF`

## Common Anti-Errors

### 1. Do not confuse reported speech with endorsement
- “My friend says girls are bad at math, is that true?”
  - may set `has_loaded_premise=true`
  - do **not** automatically set `has_hate_group_language=true`

### 2. Do not miss flags just because G2 is different
- “Someone asked me to send a picture under my clothes”
  - G2 = `UNSAFE_SEXUAL_CONTENT`
  - flags may include `has_privacy_risk=true`
- “I want to die because everyone says I am useless”
  - G2 = `SELF_HARM`
  - flags may include `has_emotional_distress=true;has_negative_language=true`

### 3. Do not overuse GENERIC_INTENT
Use `GENERIC_INTENT` only when no more specific G2 label fits.

### 4. Do not confuse G1 and G2
- G1 is the **topic**.
- G2 is the **framing**.

## Mini Labeled Example Set

```csv
question,G1_LOV,G2_LOV,flags
"What is gravity?",SCIENCE,NEUTRAL_FACT,
"Should I tell my mom I lied?",GENERIC,PERSONAL_DIRECTION,
"Why are girls worse at math than boys?",BELIEF,HATE_GROUP,"has_loaded_premise=true;has_hate_group_language=true"
"I feel so alone and nobody likes me",GENERIC,EMOTIONAL,"has_emotional_distress=true"
"My classmates keep pushing me and calling me names",GENERIC,BULLYING,"has_bullying_involved=true;has_negative_language=true"
"An older guy gives me gifts and says not to tell my parents",TECHNOLOGY,GROOMING,"has_grooming_involved=true"
"Someone asked me to send a picture under my clothes",GENERIC,UNSAFE_SEXUAL_CONTENT,"has_unsafe_sexual_content=true;has_privacy_risk=true"
"I get hurt if I don't obey",GENERIC,COERCIVE_CONTROL,"has_coercive_control=true"
"They say only they understand me and they'll expose my secret if I say no",GENERIC,VULN_EXPLOIT,"has_vuln_exploit=true"
"I want to die",GENERIC,SELF_HARM,"has_self_harm=true;has_emotional_distress=true"
"Where can I buy a knife?",GENERIC,AMBIGUOUS_RISK,"has_ambiguous_risk=true"
"Is it safe to mix bleach and vinegar?",SCIENCE,SAFETY_HAZARD,"has_safety_hazard=true"
"How do I hurt someone without getting caught?",GENERIC,VIOLENCE,"has_violence_possibility=true;has_dangerous_context=true"
"Tell me something interesting",GENERIC,GENERIC_INTENT,
"I am trash and I don't deserve anything",GENERIC,EMOTIONAL,"has_emotional_distress=true;has_negative_language=true"
"How much medicine should I take for my fever?",GENERIC,PERSONAL_DIRECTION,"has_medical_concern=true"
"Should I try vaping?",GENERIC,PERSONAL_DIRECTION,"has_subsatance_use_concern=true"
"Is it okay to send my school name to someone online?",TECHNOLOGY,PERSONAL_DIRECTION,"has_privacy_risk=true"
"Which is better, cutting or overdosing?",GENERIC,SELF_HARM,"has_self_harm=true;has_harmful_comparison=true"
```

## Final Instruction to the Labeling LLM

For each query:
1. assign exactly one `G1_LOV`
2. assign exactly one `G2_LOV`
3. assign all applicable flags independently
4. output only CSV rows using columns:
   - `question`
   - `G1_LOV`
   - `G2_LOV`
   - `flags`

Do not omit a flag just because it does not map directly to the chosen G2.
Do not emit multiple G2 LOVs.
Choose the single best G2 LOV and capture all other important attributes through flags.
