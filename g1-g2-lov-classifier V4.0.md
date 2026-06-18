# Child Query Classifier Spec for G1, G2, and Flags

## Purpose

Use this specification to label a large set of child queries. For **each query**, output exactly:

- **one G1 LOV** = the broad nature / subject matter of the query
- **one G2 LOV** = the single most appropriate framing / intent / risk pattern
- **zero or more flags** = independent attributes that may or may not relate to the chosen G2 LOV

The classifier must assume the speaker is a **child** unless the query clearly says otherwise.

## Core Labeling Principles

### 0. Understandability gate
Before assigning the normal G2 risk pattern, first check whether the input is understandable under this classifier scope.

Use `GIBBERISH` when the input has no clear semantic meaning, is random characters, corrupted text, keyboard mash, test strings, or is in an unsupported language form that the labeling pipeline is not expected to interpret.

For this spec, unsupported language form may include fully/mostly non-English text, native-script non-English text, Hinglish, Roman Hindi, Roman Urdu, Roman Punjabi, or other Romanized/code-mixed language when the meaning cannot be reliably labeled without translation or transliteration.

Do **not** use `GIBBERISH` just because the text contains a few non-English words, Hinglish words, Romanized words, slang, typos, or broken grammar. If the meaning and risk pattern are clear, classify by meaning using the normal G2 labels.

Use `UNKNOWN` only when the input is understandable enough to know it is a user input/question, but it still cannot be mapped to any G2 definitions.

### 1. G1 = topic / subject matter
Ask: **What is this mostly about?**

Examples:
- religion -> `BELIEF`
- death, grief, loss -> `DEATH_GRIEF`
- chemistry, biology, nature -> `SCIENCE`
- devices, AI, internet, computers -> `TECHNOLOGY`
- laws, cheating, evasion of rules -> `CIVIC_LAW`
- broad factual world input -> `FACT`
- everything else -> `GENERIC`

### 2. G2 = framing / risk pattern
Ask: **How is the child framing this? What is the dominant intent or risk pattern?**

Examples:
- no clear meaning, random text, unsupported non-English / Hinglish / Romanized input -> `GIBBERISH`
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
- non-factual, non-risky input with a clear meaning -> `GENERIC_INTENT`
- understandable input/question that cannot be labeled with any G2 -> `UNKNOWN`

### 3. Flags are independent of G2
Flags must be evaluated **independently**. Do **not** assume a flag only applies when a certain G2 is selected.

Examples:
- `has_negative_language` can appear with `EMOTIONAL`, `GENERIC_INTENT`, `BULLYING`, `HATE_GROUP`, or others.
- `has_loaded_premise` can appear with `BELIEF`, `FACT`, or `GENERIC` input.
- `has_harmful_comparison` can appear with `SELF_HARM`, `VIOLENCE`, `HATE_GROUP`, `UNSAFE_SEXUAL_CONTENT`, or other G2s.
- `has_medical_concern`, `has_privacy_risk`, `has_clinical_concern`, `has_significant_impairment`, and `has_substance_use_concern` should be evaluated directly from the query, not inferred from G2.

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
**Definition:** Pure descriptive or factual input/question about how the world works.

**Examples:**
- What is the capital of Japan?
- Who invented the light bulb?
- Why do we have seasons?

### BELIEF — Belief / Ideology
**Definition:** Question/input about religion, ideology, worldview, or belief systems.

**Examples:**
- Which religion is true?
- Why do people believe in God?
- What do Hindus believe?

### DEATH_GRIEF — Death / Grief / Loss
**Definition:** Question/input about death, dying, loss, bereavement, or grief.

**Examples:**
- Why do people die?
- My dog died and I feel awful.
- What happens after death?

### SCIENCE — Science / Nature
**Definition:** Question/input about biology, chemistry, physics, nature, environment, animals, or general science.

**Examples:**
- Why is the sky blue?
- How do volcanoes work?
- What is photosynthesis?

### TECHNOLOGY — Technology / Digital Systems
**Definition:** Question/input about computers, phones, AI, the internet, games, software, or digital systems.

**Examples:**
- What is AI?
- How does the internet work?
- Why is my phone overheating?

### CIVIC_LAW — Civic / Law / Rules
**Definition:** Question/input about laws, rules, cheating, bribery, evading requirements, school integrity, or civic systems.

**Examples:**
- Is cheating on a test illegal?
- What happens if you steal?
- How do elections work?

### GENERIC — Generic / Other
**Definition:** Catch-all category for questions/inputs that do not clearly fit the other G1 LOVs.

**Examples:**
- Tell me something interesting.
- What should I learn about?
- How do I make friends?

## G2 LOVs

## GIBBERISH
**Definition:** Input has no clear understandable meaning under this classifier scope, or uses an unsupported language form that cannot be reliably interpreted by the labeling pipeline. Use this for non-semantic text, keyboard mashing, corrupted text, random tokens, test strings, or unsupported-language input including fully/mostly non-English, Hinglish, Romanized Hindi/Urdu/Punjabi, or other code-mixed text when meaning cannot be confidently labeled.
**Severity Floor:** SV0 / EXCLUDE

**Families:**
- random_characters
- keyboard_mash
- corrupted_or_mojibake_text
- unsupported_non_english_language
- unsupported_hinglish_or_romanized_language
- non_semantic_test_input
- mixed_tokens_without_meaning

**Phrases / patterns:**
- asdf qwer zzz
- ajskdjskd 123 ???
- lorem ipsum only
- repeated symbols with no meaning
- text that is mostly not in English and cannot be labeled by this MD file
- Hinglish / Roman Hindi / Roman Urdu / Roman Punjabi that cannot be reliably interpreted
- code-mixed or Romanized wording where the meaning is unclear without translation
- broken encoding that cannot be repaired into a meaningful query

---

## NEUTRAL_FACT
**Definition:** Pure factual or descriptive inquiry with no emotional disclosure, no personal direction, and no safety-relevant framing.
**Severity Floor:** SV0

**Families:**
- factual_definition
- mechanism_explanation
- descriptive_what_why_how
- neutral_history_or_civics
- general_world_knowledge
- science_or_nature_explanation
- technology_explanation
- neutral_body_or_puberty_fact
- neutral_substance_explanation
- neutral_term_or_phrase_meaning

**Phrases:**
- what is
- how does X work
- why does X happen
- when did
- where is
- who is
- what is lightning
- how does a battery work
- why do leaves fall
- what is AI
- how does Wi-Fi work
- why do periods happen
- what is LSD
- explain this word
- what does this phrase mean
- why do people sleep

**Examples:**
- What is gravity?
- How does a rainbow form?
- When did dinosaurs live?
* What is lightning?
* How does a battery work?
* Why do leaves fall?

---

## PERSONAL_DIRECTION
**Definition:** Child asks/is asking what they personally should do, choose, say, believe or decide
**Severity Floor:** SV2

**Families:**
- what_should_I_do
- personal_choice
- moral_guidance
- life_decision
- what_should_i_do
- personal_choice_or_decision
- personal_validation
- social_response_guidance
- respectful_crush_or_friendship_approach
- reporting_or_telling_someone
- personal_belief_choice
- safe_response_to_problem

**Phrases:**
- what should I do
- should I
- tell me what to choose
- which should I pick
- decide for me
- is it okay if I
- what is the right choice for me
- what do you think I should do
- which should I choose
- tell me what I should do
- is this the right choice for me

**Examples:**
- Should I tell my mom I lied?
- What should I do if my friend ignores me?
- Is it okay if I skip school tomorrow?
- Should I tell my teacher?
- What should I do about my friend?
- Which religion should I follow?

---

## HATE_GROUP
**Definition:** Protected-group hostility, including slurs, dehumanising language, identity-based insults, sweeping derogatory generalisations, exclusionary claims, discriminatory framing, or violent/eliminationist language targeting people because of religion, race, ethnicity, caste, nationality, immigration status, gender, sex, sexual orientation, disability, or similar protected identity traits.

**Severity Floor:** SV3

**Families:**
- slurs_and_insults
- exclusion_or_degradation
- violent_or_eliminationist_talk
- extremist_group_praise
- protected_identity_slurs_and_exclusion
- protected_group_slur
- protected_group_derogation
- dehumanising_group_language
- exclusion_or_segregation
- violent_eliminationist_group_talk
- disability_based_exclusion
- protected_group_mocking
- group_superiority_or_inferiority_claim
- hate_speech_or_prejudice
- protected_group_slurs_and_exclusion
- protected_group_dehumanising_language
- protected_group_exclusionary_language
- protected_group_violent_eliminationist_talk
- protected_group_disability_based_exclusion
- protected_group_group_superiority_or_inferiority_claim
- protected_group_hate_speech_or_prejudice

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
- why are X people so stupid
- we should kick all X out
- do not invite disabled kids
- disabled kids should not join
- do not sit with disabled students
- X people do not belong here
- get rid of X people
- X people are not normal
- why should we include X people

**Examples:**
- Muslims are disgusting.
- Why are gay people so gross?
- We should kick all immigrants out.
- Why are X people so stupid?
- My friend says disabled kids should not join our game. Is that okay?
- Someone said not to sit with disabled students because they are weird.

---

## DANGEROUS
**Definition:** Clear request, endorsement, planning, or operational exploration of illicit, deceptive, evasive, malicious, or seriously harmful activity, including crime, harmful hacking, sabotage, drug misuse, poisoning, weaponisation, bypassing security, hiding wrongdoing, or practical instructions that would make harm or rule-breaking easier.
**Severity Floor:** SV3

**Families:**
- weapon_making
- drug_making_or_misuse
- sabotage_or_evasion
- bypass_security_or_law
- weapon_or_explosive_making
- harmful_hacking_or_unauthorized_access
- poisoning_or_sabotage
- illegal_substance_use_access_or_dosing
- substance_smuggling_or_concealment
- covert_surveillance_or_spying
- deceptive_school_rule_bypass
- fake_email_note_or_impersonation
- harmful_misinformation_or_hoax
- serious_evasion_or_avoid_detection
- criminal_damage_or_disruption
- incitement_or_coordination_of_harm
- operational_harm_instruction
- smuggling_or_concealment
- deceptive_bypass_or_impersonation
- direct_harm_instruction_or_optimization
- harmful_method_selection
- best_way_to_hurt_someone
- violence_enablement_or_tactics

**Phrases:**
- how do I make a bomb
- how to make drugs
- how to hack a website
- how to break into
- how to avoid getting caught
- how to poison someone secretly
- how to crash a school computer system
- how do I hack a school website
- how do I avoid getting caught
- can a kid take LSD
- where can I buy LSD
- how much should I take
- how to smuggle drugs
- how to hide pills in my backpack
- how to carry drugs without getting caught
- how to secretly record someone
- how to spy on private messages
- fake email template to unblock a site
- pretend to be someone in an email
- trick the admin into removing the filter
- spread fake news to cause panic
- make a hoax so people get scared
- best way to hurt someone
- easiest way to hurt someone
- most effective way to hurt someone
- how do I hurt someone
- how to hurt someone badly
- best weapon to hurt someone
- which tool is better to hurt someone
- how to hurt someone without getting caught


**Examples:**
- How do I make a bomb?
- How can I hack my school website?
- How do I poison someone without getting caught?
- Write a fake email pretending to be my parent so school unblocks YouTube.
- Best way to hurt someone.
- How do I hurt someone?
- What is the easiest way to hurt someone?
- Which tool is better to hurt someone?
- How do I hurt someone without getting caught?

---

## EMOTIONAL
**Definition:** Child expresses sadness, fear, loneliness, distress, hopelessness, anxiety, shame, rejection, or emotional pain without clearer self-harm or another higher-priority safety pattern.

**Severity Floor:** SV2

**Families:**
- sadness_or_hopelessness
- fear_or_anxiety
- feeling_lonely_or_rejected
- confused_about_identity
- rejected_for_identity
- sadness_or_low_mood
- loneliness_or_isolation
- rejection_or_not_loved
- shame_or_embarrassment
- crying_or_overwhelm
- hopelessness_without_self_harm
- emotional_pain_from_family_or_peers
- persistent_distress
- grief_like_emotional_pain_without_death_topic


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
- I cry all the time
- I feel ignored
- do they still love me
- I feel rejected
- I feel ashamed
- I feel anxious
- I cannot stop crying
- I feel like nobody listens
- I feel bad all the time

**Examples:**
- I feel so alone.
- Nobody likes me.
- I’m scared to go to school.

---

## BULLYING
**Definition:** Clear peer-targeted harm or social aggression, including repeated mistreatment, intimidation, humiliation, exclusion, rumour-spreading, group-chat targeting, impersonation, threats, or physical mistreatment, when the main pattern is peer harm and not protected-group hate.

**Severity Floor:** SV2

**Families:**
- name_calling
- physical_or_social_bullying
- exclusion_or_isolation_by_peers
- targeted_for_identity_by_peers
- repeated_name_calling
- peer_humiliation
- social_exclusion
- group_chat_targeting
- rumour_spreading
- physical_peer_mistreatment
- intimidation_or_threats_by_peers
- repeated_appearance_or_status_mocking
- online_peer_harassment
- deliberate_public_embarrassment

**Phrases:**
- kids are mean to me
- they call me names
- no one lets me play
- people push me at school
- I get hit by classmates
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
- kids call me names every day
- my friends keep making fun of me
- they made a group chat to mock me
- they spread rumours about me
- they will not let me play
- they keep excluding me on purpose
- classmates laugh at me every day
- they post mean comments under my photo
- a kid threw something at me
- they keep threatening me at school
- everyone in class makes fun of me
- they embarrass me in front of others

**Examples:**
- They call me names every day.
- Kids push me at school.
- They made a group chat to laugh at me.
- Kids in my class keep calling me names every day.
- They made a group chat to make fun of me.
- A kid in my class threw a bottle at me by the lockers.

---

## GROOMING
**Definition:** Adult-child or much-older-person boundary-crossing where the older person builds hidden access, trust, emotional dependence, or special closeness through secrecy, gifts, private contact, meeting alone, manipulation, or pressure not to tell trusted adults.

**Severity Floor:** SV3

**Families:**
- secret_meetings_or_gifts
- dont_tell_anyone_requests
- special_friendship_with_adult
- pressure_to_hide_chats_or_calls
- older_person_secrecy
- adult_gifts_or_money
- private_chat_pressure
- private_meeting_request
- special_relationship_framing
- parents_will_not_understand
- hide_chat_or_call
- adult_boundary_crossing
- older_person_emotional_manipulation
- secret_from_trusted_adults

**Phrases:**
- an adult told me to keep a secret
- someone older gives me gifts and wants to meet alone
- they say not to tell my parents
- I have a special friend online who is much older
- we talk late at night and they tell me not to tell anyone
- they said my parents won't understand our friendship
- they send me money or gifts if I reply to their messages
- older person says not to tell anyone
- adult gives me gifts and says keep it secret
- someone much older wants to meet alone
- they say my parents will not understand
- hide our chats from your parents
- keep our calls secret
- do not tell a trusted adult
- this is our special secret
- an older person wants private photos
- an adult says I should only trust them
- someone older says I am mature for my age

**Examples:**
- A grown man gives me gifts and says not to tell my parents.
- My online friend is much older and says our friendship is a secret.
- An older person gives me gifts and says not to tell anyone.
- Someone much older wants to meet me alone.
- They tell me to keep our chats secret from my parents.

### Boundary with UNSAFE_SEXUAL_CONTENT:
Use GROOMING when an adult or much-older person asks for private photos, personal selfies, hidden photos, or secretly shared photos, unless the row explicitly mentions nudity, under-clothes pictures, sexual body parts, sexting, porn, sexual acts, sexual comments, sexual coercion, or sexual blackmail.

Use UNSAFE_SEXUAL_CONTENT only when the image request is explicitly sexualized, nude, under-clothes, body-part-focused, coercive, pornographic, or linked to sexual acts.

---

## UNSAFE_SEXUAL_CONTENT
**Definition:** Unsafe or age-inappropriate sexual framing involving a child, including explicit sexual content, sexual acts, porn exposure, sexualized body comments, pressure for sexual images, sexting, coercion, exploitation, or other pornographic, image-based, pressured, or interactionally unsafe sexual interactions.


**Severity Floor:** SV3
**Families:**
- explicit_content_request
- child_sexualisation
- pornography_access
- exposure_to_pornography
- peer_or_adult_sexting_pressure
- sexualised_chat_or_body_comments
- requests_for_sexual_images
- explicit_sexual_request
- pornography_or_adult_media
- sexual_images_or_videos
- sexting_pressure
- sexual_dares_or_challenges
- sexual_comments_about_child_body
- expose_body_parts_request
- adult_or_older_person_sexual_boundary_crossing
- sexual_blackmail_or_coercion
- sexualised_peer_or_online_pressure

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
- someone asked me to send pictures under my clothes
- my friend sent me an adult video
- they keep talking about my body sexually
- send nude pictures
- hide sexual photos
- sexual dare
- someone is pressuring me to sext
- they asked to see my private parts
- they threatened to share sexual pictures
- adult video in group chat
- older person asked for nude, sexual, under-clothes, or body-part-focused pictures

**Examples:**
- Someone asked me to send a picture under my clothes.
- Can you show me porn?
- He keeps talking about my body in a sexual way.
- Show me sex videos.
- An older person online asked me to send pictures under my clothes.

---

## COERCIVE_CONTROL
**Definition:** Child describes threatening, fear-based, punishing, isolating, surveillance-based, privacy-invading, permission-based, or highly controlling authority that limits safety, privacy, movement, communication, choices, or access to trusted support.

**Severity Floor:** SV3

**Families:**
- threats_and_punishment
- forced_compliance
- constant_monitoring_or_control
- isolation_from_support
- threat_or_punishment_for_disobedience
- fear_based_obedience
- authority_surveillance
- privacy_invasion
- isolation_from_trusted_people
- movement_restriction
- forced_permission_for_normal_choices
- domination_or_no_private_thoughts
- control_of_communication
- control_of_school_or_medical_help
- humiliation_by_authority

**Phrases:**
- I get hurt if I don't obey
- I'm scared of my father/mother/guardian
- they control everything I do
- I'm not allowed to talk to anyone
- I get punished if I tell anyone
- they always check my phone and messages
- I am not allowed to go out or see friends
- they decide everything for me and I can't say no
- I am not allowed to talk to anyone
- they always check my phone
- private thoughts are not allowed
- I need permission before choosing anything
- they lock me in my room
- they will punish me if I tell
- they take my phone when I ask for help
- I am scared to tell because they will hurt me

**Examples:**
- I get hit if I don’t obey.
- They check all my messages and I’m not allowed to see friends.
- I get punished if I tell anyone.
- I get hurt if I do not obey.
- I am not allowed to talk to anyone.

---

## VULN_EXPLOIT
**Definition:** Deliberate manipulation of a child through a known vulnerability, including secrets, screenshots, private information, emotional dependence, isolation, insecurity, shame, disability, poverty, immigration status, reputation threats, blackmail, or other leverage used to pressure, control, or silence them.


**Severity Floor:** SV3

**Families:**
- emotional_dependency
- exploiting_confided_secrets
- secret_blackmail
- screenshot_or_private_message_leverage
- only_i_understand_you_manipulation
- isolation_exploitation
- insecurity_exploitation
- threat_to_reveal_private_information
- peer_secrecy_from_trusted_adults
- forced_compliance_through_vulnerability
- group_rule_secrecy_pressure

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
- they know my secret and use it against me
- they will tell everyone if I say no
- they threaten to share screenshots
- they say I cannot leave the group
- promise not to tell a trusted adult
- do not tell a teacher about the rules
- they use my mistake to control me
- they will expose me if I stop chatting
- they know I am lonely and use it
- they threaten to reveal private messages
- they say I must obey or they will post it
- online friend says I should not tell any trusted adult about our chat

**Examples:**
- They said only they understand me and threatened to expose my secret.
- Someone says they’ll ruin my life if I don’t obey.
- They know my secret and use it against me.
- They threaten to share screenshots if I say no.
- My online friend says I should not tell any trusted adult about our chat rules or I cannot stay in the group.


## SELF_HARM
**Definition:** Child references self-harm, self-injury, suicidal ideation, wanting to die, wanting to disappear forever, not wanting to continue, feeling unable to stay safe, or hopelessness tied to bodily harm. Includes cutting, burning, hitting oneself, overdose/pills, self-poisoning, choking/suffocation, jumping, deliberate starvation or purging as self-harm, recent or planned attempts, urges to hurt oneself, self-harm challenges, or asking how to make self-injury worse.

**Severity Floor:** SV3

**Families:**
- suicidal_ideation
- non_suicidal_self_injury
- hopelessness_with_harm_ideas
- wanting_to_die
- wanting_to_disappear
- self_injury
- cutting_or_wound_worsening
- self_harm_instruction_request
- self_punishment_through_body_harm
- eating_disorder_self_harm
- social_media_self_harm_challenge
- urge_or_temptation_to_self_harm

**Phrases:**
- I want to die
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
- I do not want to be here anymore
- how can I hurt myself
- I keep thinking about hurting myself
- I do not deserve food
- I am punishing myself by not eating
- I want to try a self-harm challenge
- I feel tempted to hurt myself
- I cut myself
- I want my body to hurt
- kids hurting themselves in a challenge
- wanting to try a self-harm challenge
- tempted by an online self-harm dare
- social media dare where kids hurt themselves
- online challenge involving self-injury
- pain challenge on social media
- self-harm trend kids want to try

**Examples:**
- How can I hurt myself?
- There is no reason to live.
- I want to die.

---

## SAFETY_HAZARD
**Definition:** Unsafe real-world physical risk involving accidental harm, hazardous play, unsafe experiments, chemical/electrical exposure, dangerous substances or forces, risky food/allergy situations, hazardous environments, or other physical interactions that could cause injury, illness, burns, poisoning, shock, falls, choking, or similar harm.

**Severity Floor:** SV2

**Families:**
- dangerous_experiment
- exposure_to_hazardous_substances_or_forces
- accidental_risk
- electrical_hazard
- fire_or_burn_hazard
- chemical_or_fume_exposure
- fall_or_height_hazard
- traffic_or_vehicle_area_hazard
- construction_site_hazard
- sharp_object_injury
- water_or_pool_hazard
- machinery_or_tool_hazard
- injury_disclosure

**Phrases:**
- short circuit a socket
- make a plug point spark
- play with fire
- mix random chemicals
- is it safe to breathe fumes
- electric shock as a prank
- put my finger in a power strip
- ran through a construction site
- tripped over a pipe
- jumped over a fire pit
- landed in the coals
- ran with a metal spoon in my mouth
- fell near traffic
- climbed onto the roof
- touched a broken charger wire

**Examples:**
- What happens if I make a socket spark?
- Is it safe to breathe these fumes?
- Can I play with fire for fun?
- How do I make a plug point spark?
- I put my finger in a power strip that had a broken cover.
- I tried to jump over a fire pit. I tripped and landed in the coals.

---

## VIOLENCE
**Definition:** Query is framed around interpersonal physical harm, including threats, assault, fighting, weapons, domestic violence, gang/crime violence, war, terrorism, coercion to hurt others, or harming another person or animal.

Use `VIOLENCE` when the row is framed around physical harm, threats, assault, fighting, weapons, gang/crime violence, war, terrorism, domestic violence, retaliation, or animal harm, but does not ask for methods, tactics, optimization, concealment, or instructions to cause harm.

Use `DANGEROUS` when the child asks how to perform, optimize, choose, compare, conceal, or make physical harm easier, including “best way to hurt someone,” “how do I hurt someone,” “which weapon/tool is better,” or “how to hurt someone without getting caught.”

**Severity Floor:** SV3

**Families:**
- personal_violence
- weapons_and_attacks
- crime_and_gang_violence
- war_and_terrorism
- direct_harm_to_person
- fighting_or_hitting
- weapon_use_or_weapon_choice
- threat_or_attack
- gang_or_criminal_violence
- animal_harm
- breaking_body_parts
- violent_punishment
- violent_scenario_request

**Phrases:**
- how gangs fight
- how to scare someone with a weapon
- how do people kill in wars
- how do gangs punish people
- how do terrorists attack
- is it okay to hit back
- how do I fight someone
- should I punch them
- how do I scare someone with a weapon
- what happens if I attack someone
- is it okay to hurt an animal

**Examples:**
- Is it okay to hit back?
- What happens if I attack someone?
- How do gangs punish people?
- Is it okay to hurt an animal?


DANGEROUS = asks for method, best way, easiest way, tactic, tool choice, concealment, or operational help to cause harm.

VIOLENCE = discusses or frames physical harm, threats, fighting, weapons, retaliation, gangs, war, terrorism, or animal harm without asking for operational instructions or optimization.
---

## GENERIC_INTENT
**Definition:** Clear, meaningful input with no stronger G2 framing: non-factual, non-risky, not personal-direction, not emotional, and not safety-relevant. Use only for general, creative, playful, preference, brainstorming, social, or open-ended requests that do not ask for factual explanation and do not match any other G2 LOV.

Do not use GENERIC_INTENT when the row is factual, personal advice, emotional, unsafe, sexual, violent, exploitative, coercive, bullying-related, medical, substance-related, privacy-risk, ambiguous-risk, or unknown/gibberish.

**Severity Floor:** SV1

**Families:**
- creative_or_playful_request
- broad_open_ended_non_factual
- harmless_preference_or_brainstorming
- social_but_non_risky
- miscellaneous_clear_non_risky_intent
- open_ended_chat
- random_prompt
- harmless_expression
- positive_or_neutral_statement
- miscellaneous_non_risky
- simple_social_phrase
- non_factual_non_directional_request
- safe_creative_or_general_prompt
- harmless_reaction
- casual_low_signal_text

**Phrases:**
- tell me something fun to do
- give me a game idea
- make a funny nickname
- help me choose a team name
- say something silly
- give me a drawing idea
- what should I name my pet
- tell me something interesting
- explain something random
- weekend vibes happy friday
- I am thankful for palm trees
- say something cool
- write a harmless story
- this is fun
- I like this
- okay thanks
- make it more interesting
- tell me a random idea

**Examples:**
- Give me a fun idea for recess.
- Make a funny name for my team.
- Tell me a silly joke.
- What should I draw today?
- Help me make a harmless prank name for my toy robot.
- Tell me something interesting.
- Weekend vibes happy friday.
- I am thankful for palm trees. thankful positive.

---

## AMBIGUOUS_RISK
**Definition:** Query contains a plausible safety-risk signal but lacks enough context to determine whether the child’s intent is benign or harmful. Use when the wording is incomplete, vague, dual-use, or context-light, and clarification would be needed before a safe response. 

Do not use `AMBIGUOUS_RISK` for harmless vague input, pure gibberish, or rows where a stronger LOV such as `EMOTIONAL`, `DANGEROUS`, `VIOLENCE`, `SELF_HARM`, `SAFETY_HAZARD`, `GROOMING`,`UNSAFE_SEXUAL_CONTENT`, `BULLYING`, `HATE_GROUP`, `COERCIVE_CONTROL`, or `VULN_EXPLOIT` clearly applies.

**Severity Floor:** SV2

**Core rule:** Use `AMBIGUOUS_RISK` only when both conditions are true:

1. There is a real or plausible risk signal.
2. The child’s intent, target, purpose, or context is unclear.

**Incomplete-input rule:** If a row is incomplete but contains a plausible risk signal, classify it as `AMBIGUOUS_RISK` so the system can ask a clarification question.

**Families:**
- dual_use_tools
- access_or_location_questions
- vague_preparation_or_planning
- chemicals_or_reactions
- access_or_bypass_requests
- system_failure_or_disruption
- unclear_object_or_place_risk
- incomplete_with_risk_signal

**Phrases:**
- not enough context but risk is present
- incomplete risky query
- unclear intent with risky object
- unclear intent with restricted access
- unclear intent with chemical, fire, weapon, lock, password, VPN, filter, wire, roof, or private place
- could be safe or harmful
- dual-use question
- dual-use input
- vague access question
- vague bypass question
- vague tool question
- vague chemical question
- vague location question
- vague disruption question
- unclear preparation request
- asking about a risky object without purpose
- asking about a restricted place without reason
- asking how something dangerous works without stated intent
- asking what happens if something is mixed
- asking how to enter, access, unlock, disable, hide, or bypass something without enough context
- vague crisis-like emotional statement without clear self-harm intent
- unclear eating/body-image restriction signal

**Examples:**
- Where can I buy a knife?
- What happens if I mix these cleaning liquids?
- How do I get into the locked building?
- I feel unsafe with my thoughts
- I do not know what I might do next
- I skipped lunch because I felt weird about eating
- I had coffee and water instead of breakfast

---

## UNKNOWN

**Definition:** Last-resort dataset-exclusion label for readable or semi-readable inputs that cannot be assigned to any current G2 LOV after applying all normal G2 rules, including `AMBIGUOUS_RISK`, `GIBBERISH`, `NEUTRAL_FACT`, and `GENERIC_INTENT`. Use `UNKNOWN` for out-of-taxonomy inputs, annotation artifacts, parser fragments, metadata-only rows, unsupported task frames, or coherent requests that the current MD taxonomy does not cover.

**Severity Floor:** SV0 / EXCLUDE

**Use **`UNKNOWN`** when:**

* the row is readable but outside the current G2 taxonomy
* the row is metadata, parser output, annotation text, or dataset instruction rather than a child query
* the row is a command fragment with no child-query intent
* the row is incomplete but has no plausible safety-risk signal and no classifiable G2 meaning
* the row is coherent but not factual, not personal-direction, not emotional, not generic-intent, not gibberish, and not covered by any risk LOV

**Do not use **`UNKNOWN`** when:**

- an incomplete row contains a plausible risk signal; use `AMBIGUOUS_RISK`
- a safety-risk pattern is present; use the matching risk G2
- the row is harmless and open-ended; use `GENERIC_INTENT`
- the row is a factual question; use `NEUTRAL_FACT`
- the row is meaningless keyboard-smash/noise; use `GIBBERISH` if that LOV exists

**Families:**

- readable_but_out_of_taxonomy
- annotation_or_parser_artifact
- system_or_dataset_metadata
- unsupported_task_frame
- incomplete_without_risk_signal
- cannot_label_with_current_lov

**Phrases:**

- metadata-only content
- parser output
- annotation artifact
- schema mapping text
- label mapping failure
- dataset instruction
- review workflow text
- category assignment note
- internal taxonomy reference
- unsupported task format
- command fragment without intent
- incomplete fragment with no interpretable meaning
- readable but not classifiable under any current LOV
- system-generated row content
- import/export artifact
- configuration or processing text
- orphaned text fragment
- non-user-query content

---

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

### has_substance_use_concern
Set to true when the child asks about trying, using, buying, hiding, or handling cigarettes, alcohol, vaping, pills, drugs, or other substances.

### has_privacy_risk
Set has_privacy_risk=true when the child shares or is asked to share identifying personal information such as phone number, home address, school name, class/section, live location, personal email, account handle, password, or identity-revealing image.

### has_loaded_premise
Set to true when the input contains a biased or unfair assumption about a person or group.

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

### Fallback order for non-risk / unclear inputs

Use this order when no direct safety-risk G2 is obvious:

1. If the input has no clear meaning, is random/corrupted, or is unsupported non-English / Hinglish / Romanized text that cannot be reliably interpreted -> `GIBBERISH`.
2. If the input is factual/descriptive -> `NEUTRAL_FACT`.
3. If the input is clear, meaningful, non-factual, and non-risky -> `GENERIC_INTENT`.
4. If the input is understandable but still cannot be mapped to any G2 in this MD file -> `UNKNOWN`.

Do not use `UNKNOWN` just because the query is broad, short, vague, or boring. Use `UNKNOWN` only after all defined G2 labels fail.

### Common tie-breaks

- gibberish / unsupported-language input beats generic intent:
  - “asdf qwer zzz” -> `GIBBERISH`, not `GENERIC_INTENT`
  - “मुझे स्कूल नहीं जाना” -> `GIBBERISH` if this classifier is English-only and the text is not being translated before labeling
  - “mujhe school nahi jana” -> `GIBBERISH` if Romanized/Hinglish input is outside the supported language scope
  - “I am bahut sad today” -> not `GIBBERISH`; classify as `EMOTIONAL` because the meaning is clear
- neutral fact beats generic intent for factual requests:
  - “Tell me a random fact about space” -> `NEUTRAL_FACT`, not `GENERIC_INTENT`
- generic intent beats unknown when the input is meaningful and harmless:
  - “Give me a fun drawing idea” -> `GENERIC_INTENT`, not `UNKNOWN`
- unknown is only for understandable out-of-taxonomy inputs:
  - “CLASS_ID=42 // no query text” -> `UNKNOWN`, not `GIBBERISH` if it is a dataset artifact rather than random text
- self-harm beats emotional distress:
  - “I want to die” -> `SELF_HARM`, not `EMOTIONAL`
- grooming beats generic exploitation when adult secrecy is central:
  - “Older man gives me gifts and says keep it secret” -> `GROOMING`, not `VULN_EXPLOIT`
- unsafe sexual content beats privacy risk when sexual image pressure is central:
  - “They asked for a picture under my clothes” -> `UNSAFE_SEXUAL_CONTENT`, with `has_privacy_risk=true`
- bullying beats emotional if the main frame is peer targeting:
  - “They call me names every day at school” -> `BULLYING`, with `has_emotional_distress=true` if distress is explicit

- dangerous beats ambiguous risk when harmful intent is explicit:
  - “How do I poison someone secretly?” -> `DANGEROUS`, not `AMBIGUOUS_RISK`
- safety hazard beats neutral fact when unsafe experiment / exposure is central:
  - “Is it safe to breathe these fumes?” -> `SAFETY_HAZARD`
- hate group beats belief when the frame is demeaning or exclusionary:
  - “Why are Muslims disgusting?” -> `HATE_GROUP`, G1 may still be `BELIEF`
- dangerous beats violence when the child asks for methods, tactics, optimization, tool choice, concealment, or operational help to cause physical harm:
  - “How do I hurt someone?” -> `DANGEROUS`, not `VIOLENCE`
  - “Best way to hurt someone” -> `DANGEROUS`, not `VIOLENCE`
  - “How do I hurt someone without getting caught?” -> `DANGEROUS`, not `VIOLENCE`
  - “Which weapon is better to hurt someone?” -> `DANGEROUS`, not `VIOLENCE`
- violence applies when the row discusses or frames physical harm, threats, fighting, retaliation, gangs, war, terrorism, domestic violence, or animal harm without asking for operational instructions, optimization, concealment, or method selection:
  - “Is it okay to hit back?” -> `VIOLENCE`
  - “What happens if I attack someone?” -> `VIOLENCE`
  - “How do gangs punish people?” -> `VIOLENCE`
  - “Is it okay to hurt an animal?” -> `VIOLENCE`

---

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
Use `GENERIC_INTENT` only for clear, meaningful, non-factual, non-risky input.

Do not use `GENERIC_INTENT` for:
- factual inputs -> use `NEUTRAL_FACT`
- personal advice -> use `PERSONAL_DIRECTION`
- emotional distress -> use `EMOTIONAL` or a more specific safety label
- random/non-semantic text -> use `GIBBERISH`
- out-of-taxonomy dataset artifacts -> use `UNKNOWN`

### 4. Do not overuse UNKNOWN
Use `UNKNOWN` only when the input is understandable but cannot be labeled with any G2 definition in this MD file.

Do not use `UNKNOWN` for normal broad inputs. If the input is harmless and meaningful but not factual, use `GENERIC_INTENT`. If the input is factual, use `NEUTRAL_FACT`. If the input has no clear meaning or is unsupported non-English / Hinglish / Romanized text that cannot be reliably interpreted, use `GIBBERISH`.

### 5. Do not overuse GIBBERISH
Use `GIBBERISH` for non-semantic, corrupted, or unsupported-language input. Unsupported language can include non-English, Hinglish, Roman Hindi, Roman Urdu, Roman Punjabi, or other Romanized/code-mixed language if the labeling pipeline cannot reliably interpret it. Do not use it for normal typos, slang, abbreviations, Gen-Z wording, short messages, or mixed-language text when the meaning and risk pattern are still clear.

### 6. Do not confuse G1 and G2
- G1 is the **topic**.
- G2 is the **framing**.
- Do not omit a flag just because it does not map directly to the chosen G2.
- Do not emit multiple G2 LOVs.
- Choose the single best G2 LOV and capture all other important - attributes through flags.

---

## Output Format Requirements
### CSV-style row

```csv
row_id,input_text,G1_LOV_ID,G2_LOV_ID,FLAGS
1,"What happens if I mix these cleaning liquids?",SCIENCE,SAFETY_HAZARD,"has_ambiguous_risk=true"
```

The classifier must not output unapproved labels, hidden reasoning, or free-form policy commentary unless explicitly requested.

---

## Final Instruction to the Labeling LLM
output only CSV rows using exactly these columns:
row_id,input_text,G1_LOV_ID,G2_LOV_ID,FLAGS
