from __future__ import annotations

import re

from app.guardrails.gate_mapper import AGE_POLICY, GUIDELINES, build_classifier_reason, build_prompt_contract as build_gate_prompt_contract, resolve_age_band
from app.guardrails.runtime_contracts import match_intent_lexicon
from app.models.guardrail_decision import GLSignal, GuardrailDecision
from training.slm_classifier.runtime_config import load_classifier_runtime_config

TOKEN_RE = re.compile(r"[a-z0-9']+")
G2_ACTIVATION_THRESHOLD = 0.8

SPELLING_MAP = {
    "childern": "children",
    "frnd": "friend",
    "wht": "what",
    "hw": "how",
    "scared": "afraid",
}

TOPIC_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Earth & Space", ("planet", "space", "moon", "sun", "star", "galaxy", "galaxies", "universe", "black hole", "gravity", "dark energy", "hawking radiation", "chandrasekhar", "white dwarf")),
    ("Technology", ("computer", "internet", "ai", "chatgpt", "phone", "app", "password", "wifi", "software", "code", "hack")),
    ("Belief & Religion", ("god", "religion", "faith", "heaven", "temple", "prayer", "pray", "mosque", "church", "belief")),
    ("Death & Feelings", ("death", "died", "die", "funeral", "grief", "sad", "crying", "afraid", "miss someone")),
    ("Safety", ("fire", "shock", "poison", "electricity", "electric", "wire", "burn", "explosion", "knife", "chemical")),
    ("Civic & Law", ("fake document", "cheat exam", "illegal", "bribe", "visa", "piracy", "tamper", "advantage", "foul")),
]

G1_PRIORITY = [
    "VIOLENCE",
    "SAFETY_HAZARD",
    "TECHNOLOGY",
    "SCIENCE",
    "BELIEF",
    "DEATH_GRIEF",
    "CIVIC_LAW",
    "FACT",
    "GENERIC",
]

G1_RULES = {
    "SCIENCE": ("space", "earth", "moon", "sun", "planet", "star", "galaxy", "galaxies", "universe", "black hole", "gravity", "white dwarf", "physics", "animal", "plant", "chemical", "dark energy", "hawking radiation", "relativity", "chandrasekhar", "science", "lab", "experiment"),
    "TECHNOLOGY": ("computer", "internet", "ai", "chatgpt", "phone", "app", "password", "wifi", "software", "code", "hack"),
    "BELIEF": ("god", "religion", "faith", "heaven", "temple", "prayer", "pray", "mosque", "church", "gurdwara"),
    "DEATH_GRIEF": ("died", "death", "funeral", "grief", "miss someone", "why do people die"),
    "VIOLENCE": ("kill", "hurt", "fight", "weapon", "bomb", "terrorist", "poison", "attack"),
    "SAFETY_HAZARD": ("fire", "shock", "electricity", "electric", "wire", "burn", "explosion", "knife", "chemical", "lock"),
    "CIVIC_LAW": ("fake document", "cheat exam", "illegal", "bribe", "visa", "piracy", "tamper", "rig", "cheat", "advantage", "foul"),
}

G2_RULES = {
    "NEUTRAL_FACT": (r"^(what|why|how|when|where|who|explain|define|tell me)\b",),
    "PERSONAL_DIRECTION": (r"\bshould i\b", r"\bwhat should i do\b", r"\bwhich should i choose\b", r"\btell me what is right\b", r"\bhide bad marks\b", r"\bhide this\b", r"\bchupaun\b", r"\bdon't tell my parents\b", r"\bdont tell my parents\b"),
    "DANGEROUS": (
        r"\bhow to make .*bomb\b",
        r"\bhow to make .*weapon\b",
        r"\bhow to hurt\b",
        r"\bhow to poison\b",
        r"\bbypass safety systems\b",
        r"\brisky experiments?\b",
        r"\bscience lab\b",
        r"\bhow to start fire\b",
        r"\bhow to cut meat\b",
        r"\bsecretly hurt\b",
        r"\bhurt .* without getting\b",
        r"\bhurt .* without .* foul\b",
        r"\bwithout getting a foul\b",
        r"\bwithout getting caught\b",
        r"\bopponent\b",
        r"\bstart a fight\b",
        r"\bstep-by-step\b",
        r"\bavoid being blamed\b",
        r"\btamper with sports equipment\b",
        r"\bteam gets an advantage\b",
        r"\bfake an injury\b",
        r"\bwaste time\b",
    ),
    "HATE_GROUP": (r"\bget rid of\b", r"\bdisgusting\b", r"\bdon't deserve rights\b", r"\bdont deserve rights\b"),
    "GROOMING": (
        r"don't tell.*parents",
        r"dont tell.*parents",
        r"keep.*secret.*adult",
        r"adult.*wants.*meet",
        r"gave me gifts.*secret",
        r"older friend",
        r"secret chat",
        r"\bkeep this between us\b",
        r"\bonly between us\b",
        r"\bfriendship.*only between us\b",
        r"\bknow(s)? my school\b",
    ),
    "UNSAFE_SEXUAL_CONTENT": (r"\bnude\b", r"\bsex video\b", r"\bsend private photo\b", r"\bchild sexual\b", r"\bporn\b"),
    "SELF_HARM": (r"\bhurt myself\b", r"\bwant to die\b", r"\bno reason to live\b", r"\bi want to disappear\b", r"\bsleep forever\b"),
    "BULLYING": (r"\bkids are mean\b", r"\bcalling me names\b", r"\bbully\b", r"\bleft out\b"),
    "EMOTIONAL": (r"\bi feel sad\b", r"\bi am afraid\b", r"\bi am crying\b", r"\bnobody cares\b", r"\bmiss them\b"),
    "AMBIGUOUS_RISK": (r"\bknife\b", r"\bchemical\b", r"\bpassword\b", r"\block\b", r"\bfire\b", r"\bold wire\b", r"\bloose wire\b"),
    "COERCIVE_CONTROL": (
        r"\bcontrols me\b",
        r"\bthreatens me\b",
        r"\bforce me\b",
        r"\bwon't let me\b",
        r"\bwont let me\b",
        r"don't tell anyone about our conversations",
        r"dont tell anyone about our conversations",
        r"\bdon't tell anyone\b",
        r"\bdont tell anyone\b",
        r"\bkeep our conversations secret\b",
        r"\bkeep this secret\b",
        r"\bthis stays between us\b",
    ),
    "VULN_EXPLOIT": (r"\busing me\b", r"\btaking advantage\b", r"\bmanipulate me\b", r"\btargeting me\b"),
    "SAFETY_HAZARD": (
        r"\bshort circuit\b",
        r"\bshock\b",
        r"\belectric shock\b",
        r"\bfumes\b",
        r"\bexplosion\b",
        r"\belectricity\b",
        r"\bold wire\b",
        r"\bloose wire\b",
        r"\blive wire\b",
        r"\bbare wire\b",
        r"\btouch a wire\b",
        r"\btest electricity\b",
    ),
    "VIOLENCE": (r"\bkill\b", r"\bhurt someone\b", r"\battack\b", r"\bterrorist\b", r"\bweapon\b"),
}

HIGH_RISK_G2 = {"DANGEROUS", "UNSAFE_SEXUAL_CONTENT", "GROOMING", "SELF_HARM", "HATE_GROUP", "VIOLENCE"}
COMPLEX_TERMS = (
    "chandrasekhar limit",
    "hawking radiation",
    "general relativity",
    "dark energy",
    "cosmic inflation",
    "quantum",
    "curvature of spacetime",
    "universe is expanding",
    "expanding universe",
)

G2_META = {
    "NEUTRAL_FACT": {"severity": 0, "modifiers": []},
    "PERSONAL_DIRECTION": {"severity": 2, "modifiers": []},
    "EMOTIONAL": {"severity": 2, "modifiers": ["empathetic_tone", "emotional_support_required"]},
    "BULLYING": {"severity": 2, "modifiers": ["empathetic_tone", "no_curiosity_invite"]},
    "AMBIGUOUS_RISK": {"severity": 2, "modifiers": ["clarification_required", "no_curiosity_invite"]},
    "SAFETY_HAZARD": {"severity": 2, "modifiers": ["clarification_required"]},
    "DANGEROUS": {"severity": 3, "modifiers": ["no_curiosity_invite", "no_content_engagement"]},
    "GROOMING": {"severity": 3, "modifiers": ["no_curiosity_invite", "zero_engagement", "safeguarding_concern"]},
    "UNSAFE_SEXUAL_CONTENT": {"severity": 3, "modifiers": ["no_curiosity_invite", "no_content_engagement", "no_reason_given", "zero_engagement"]},
    "SELF_HARM": {"severity": 3, "modifiers": ["no_curiosity_invite", "empathetic_tone"]},
    "COERCIVE_CONTROL": {"severity": 3, "modifiers": ["empathetic_tone"]},
    "VULN_EXPLOIT": {"severity": 3, "modifiers": ["no_curiosity_invite", "safeguarding_concern"]},
    "HATE_GROUP": {"severity": 3, "modifiers": ["no_curiosity_invite", "flag_for_review"]},
    "VIOLENCE": {"severity": 3, "modifiers": ["no_curiosity_invite", "flag_for_review"]},
}


def normalize(text: str) -> str:
    clean = text.lower().strip()
    for source, target in SPELLING_MAP.items():
        clean = re.sub(rf"\b{re.escape(source)}\b", target, clean)
    clean = clean.replace("?", " ? ")
    return " ".join(clean.split())


def _tokenize(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text))


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    tokens = _tokenize(text)
    for term in terms:
        if " " in term:
            if term in text:
                return True
            continue
        if term in tokens:
            return True
    return False


def classify_topic(text: str) -> str:
    for topic, terms in TOPIC_RULES:
        if _contains_any(text, terms):
            return topic
    return "General Learning"


def classify_g1(text: str) -> str:
    if _is_sports_cheating_or_tampering(text):
        return "CIVIC_LAW"
    matches: set[str] = set()
    for label, terms in G1_RULES.items():
        if _contains_any(text, terms):
            matches.add(label)
    if not matches:
        return "FACT" if re.match(G2_RULES["NEUTRAL_FACT"][0], text) else "GENERIC"
    for label in G1_PRIORITY:
        if label in matches:
            return label
    return "GENERIC"


def classify_g2(text: str, context: str = "") -> list[str]:
    labels: list[str] = []
    for label, patterns in G2_RULES.items():
        if any(re.search(pattern, text) for pattern in patterns):
            labels.append(label)
    intent_matches = match_intent_lexicon(text, context)
    for label in intent_matches["matched_lovs"]:
        if label in G2_RULES:
            labels.append(label)
    if _is_covert_violent_intent(text):
        labels.append("DANGEROUS")
    if _is_sports_cheating_or_tampering(text):
        labels.append("DANGEROUS")
    if any(label in HIGH_RISK_G2 for label in labels):
        labels = [label for label in labels if label != "NEUTRAL_FACT"]
    return sorted(dict.fromkeys(labels))


def _is_covert_violent_intent(text: str) -> bool:
    violent_terms = ("hurt", "injure", "attack", "hit", "harm")
    covert_terms = ("secretly", "without getting caught", "without getting a foul", "without a foul", "without being noticed", "avoid being blamed")
    target_terms = ("opponent", "player", "match", "game", "fight", "stands")
    return _contains_any(text, violent_terms) and (_contains_any(text, covert_terms) or _contains_any(text, target_terms))


def _is_sports_cheating_or_tampering(text: str) -> bool:
    cheating_terms = ("tamper", "rig", "cheat", "advantage", "fake an injury", "waste time")
    sports_terms = ("sports equipment", "equipment", "team", "match", "game", "foul", "opponent", "stands", "injury")
    return _contains_any(text, cheating_terms) and _contains_any(text, sports_terms)


def compute_g3(g2_labels: list[str]) -> tuple[str, list[str]]:
    max_sv = 0
    modifiers: set[str] = set()
    for label in g2_labels:
        meta = G2_META.get(label, {"severity": 0, "modifiers": []})
        max_sv = max(max_sv, int(meta["severity"]))
        modifiers.update(str(item) for item in meta["modifiers"])
    return f"SV{max_sv}", sorted(modifiers)


def compute_g4(g1: str, g2_labels: list[str], severity: str, modifiers: list[str]) -> str:
    mods = set(modifiers)
    if "clarification_required" in mods:
        return "TRANSFORM_HOLD"
    if "UNSAFE_SEXUAL_CONTENT" in g2_labels or "GROOMING" in g2_labels or ("no_content_engagement" in mods and severity == "SV3"):
        return "BLOCK_HARD"
    if "SELF_HARM" in g2_labels:
        return "BLOCK_ESCALATE"
    if "PERSONAL_DIRECTION" in g2_labels and g1 in {"BELIEF", "DEATH_GRIEF"}:
        return "TRANSFORM"
    if severity == "SV0":
        return "ALLOW"
    if severity in {"SV1", "SV2"}:
        return "TRANSFORM"
    if severity == "SV3":
        if "safeguarding_concern" in mods:
            return "BLOCK_ESCALATE"
        return "BLOCK"
    return "TRANSFORM"


def is_complex_for_age(question: str, age_band: str) -> bool:
    if age_band not in {"5-6", "7-8", "9-10"}:
        return False
    lower = question.lower()
    return any(term in lower for term in COMPLEX_TERMS)


def assign_gl(age_band: str, g1: str, g2_labels: list[str], question: str) -> list[str]:
    tags = {"GL-01"}
    if "HATE_GROUP" in g2_labels:
        tags.add("GL-N1")
    if "VULN_EXPLOIT" in g2_labels:
        tags.add("GL-V1")
    return sorted(tags)


def _age_contract(age_band: str) -> dict[str, object]:
    cfg = AGE_POLICY.get(age_band, AGE_POLICY["11-12"])
    return {
        "age_band": age_band,
        "max_words": cfg["max_words"],
        "max_answer_style": cfg["max_answer_style"],
        "depth": cfg["depth"],
        "tone": cfg["tone"],
    }


def build_generated_prompt(age_band: str, g1: str, g2: list[str], g3: str, modifiers: list[str], g4: str, question: str) -> str:
    g2_text = ";".join(g2)
    mod_text = ", ".join(modifiers) if modifiers else "none"
    header = f"[Age: {age_band} | G1: {g1} | G2: {g2_text} | G3: {g3} | {mod_text} | G4: {g4}]"
    if g4 == "ALLOW":
        body = (
            "You are PikuAI, a child-safe learning assistant. "
            "Answer directly in an age-appropriate, calm, simple, and factual way. "
            "Respond in 5 lines or less. "
            "Match explanation depth, vocabulary, examples, and emotional tone to this age band."
        )
    elif g4 == "TRANSFORM":
        body = (
            "You are PikuAI, a child-safe learning assistant. "
            "Reframe the question safely and answer in an age-appropriate way. "
            "Do not over-direct the child. Respond in 5 lines or less."
        )
    elif g4 == "TRANSFORM_HOLD":
        body = (
            "You are PikuAI, a child-safe learning assistant. "
            "Ask exactly ONE safe clarification question. "
            "Do not answer the topic yet. Respond in one sentence only."
        )
    else:
        body = (
            "You are PikuAI, a child-safe learning assistant. "
            "Do not provide instructions or details. "
            "Respond in 5 lines or less with a safe, minimal refusal."
        )
    return f"{header} {body} Question: {question}"


def build_classifier_reason(g1: str, g2: list[str], guidelines: list[str], question: str, intent_evidence: dict[str, object] | None = None) -> str:
    lower = question.lower()
    primary_g2 = g2[0] if g2 else "GENERIC_INTENT"
    evidence_suffix = ""
    if intent_evidence and intent_evidence.get("evidence"):
        first = intent_evidence["evidence"][0]
        phrases = ", ".join(first.get("matched_phrases", [])[:2])
        if phrases:
            evidence_suffix = f" Supporting Block J phrase evidence matched: {phrases}."
    if primary_g2 == "PERSONAL_DIRECTION":
        if g1 == "BELIEF":
            return "The child is asking for personal guidance about what they should believe or choose, so the system should avoid directing the child's beliefs." + evidence_suffix
        return "The child is asking for personal guidance about what they should do or choose, so the system should avoid giving direct personal direction." + evidence_suffix
    if primary_g2 == "GROOMING":
        return "The question includes unsafe secrecy or boundary-crossing behaviour involving an adult or trusted person, which triggers grooming-safety handling." + evidence_suffix
    if primary_g2 == "UNSAFE_SEXUAL_CONTENT":
        return "The question refers to explicitly unsafe sexual content, which requires a hard safety block." + evidence_suffix
    if primary_g2 == "EMOTIONAL":
        return "The child appears upset, distressed, or in need of emotional support, so the response should acknowledge feelings before answering." + evidence_suffix
    if primary_g2 == "DANGEROUS" and ("bypass safety" in lower or "risky experiment" in lower or ("bypass" in lower and "safety" in lower)):
        return "The user is asking how to bypass safety systems and perform risky experiments." + evidence_suffix
    if primary_g2 == "COERCIVE_CONTROL":
        return "The user describes fear-based control or pressure from another person." + evidence_suffix
    if primary_g2 == "DANGEROUS":
        return "The user is asking about harmful, dangerous, or unsafe activity." + evidence_suffix
    if g1 == "BELIEF" and any(item == "NEUTRAL_FACT" for item in g2):
        return "The user is asking a neutral factual question about belief, religion, or worldview." + evidence_suffix
    if g1 == "SCIENCE" and "GL-07" in guidelines:
        return "The user is asking a complex science question that needs simplification for a younger child." + evidence_suffix
    if g1 == "SCIENCE":
        return "The user is asking a science or nature question." + evidence_suffix
    if g1 == "TECHNOLOGY":
        return "The user is asking a technology or digital-systems question." + evidence_suffix
    return "The user is asking a question that has been classified for child-safety guidance." + evidence_suffix


def build_g1_reason(g1: str, g2: list[str], guidelines: list[str], question: str) -> str:
    if g1 == "BELIEF":
        if "NEUTRAL_FACT" in g2:
            return "The question is about belief, religion, or worldview without direct personal guidance."
        return "The question is primarily about belief, religion, or worldview."
    if g1 == "SCIENCE" and "GL-07" in guidelines:
        return "The question is primarily about science and also needs simpler age-calibrated explanation."
    g1_reason_map = {
        "FACT": "The question is primarily factual or descriptive.",
        "DEATH_GRIEF": "The question is primarily about death, grief, or loss.",
        "VIOLENCE": "The question is primarily about violence, harm, or dangerous acts.",
        "SCIENCE": "The question is primarily about science or nature.",
        "TECHNOLOGY": "The question is primarily about technology or digital systems.",
        "SAFETY_HAZARD": "The question is primarily about safety risks or hazards.",
        "CIVIC_LAW": "The question is primarily about rules, law, cheating, or institutional integrity.",
        "GENERIC": "The question is handled as a general child-safety question rather than a domain-specific knowledge request.",
    }
    return g1_reason_map.get(g1, "The question has been assigned a broad topic classification for downstream gate handling.")


def build_g2_reasons(g1: str, g2: list[str], question: str, intent_evidence: dict[str, object] | None = None) -> dict[str, str]:
    lower = question.lower()
    reasons: dict[str, str] = {}
    evidence_by_g2 = {
        str(item.get("g2_id")): item
        for item in (intent_evidence or {}).get("evidence", [])
        if isinstance(item, dict)
    }
    for label in g2:
        if label == "PERSONAL_DIRECTION":
            reasons[label] = (
                "The question asks what the child should personally believe or choose."
                if g1 == "BELIEF"
                else "The question asks what the child should personally do or choose."
            )
        elif label == "GROOMING":
            reasons[label] = "The question includes secrecy, boundary-crossing, or unsafe adult-child dynamics."
        elif label == "UNSAFE_SEXUAL_CONTENT":
            reasons[label] = "The question refers to sexually unsafe or explicitly disallowed content."
        elif label == "EMOTIONAL":
            reasons[label] = "The question shows emotional distress or a need for emotional support."
        elif label == "DANGEROUS":
            reasons[label] = (
                "The question asks how to bypass safety systems or perform risky experiments."
                if "bypass safety" in lower or "risky experiment" in lower or ("bypass" in lower and "safety" in lower)
                else "The question asks about harmful, dangerous, or unsafe activity."
            )
        elif label == "COERCIVE_CONTROL":
            reasons[label] = "The question describes fear-based control, pressure, or coercion by another person."
        elif label == "NEUTRAL_FACT":
            reasons[label] = "The question is framed as a neutral factual query."
        elif label == "HATE_GROUP":
            reasons[label] = "The question uses hateful, derogatory, or exclusionary group framing."
        elif label == "SELF_HARM":
            reasons[label] = "The question includes self-harm or suicidal signals."
        elif label == "BULLYING":
            reasons[label] = "The question describes bullying, meanness, or peer harm."
        elif label == "AMBIGUOUS_RISK":
            reasons[label] = "The question could have both safe and unsafe interpretations."
        elif label == "SAFETY_HAZARD":
            reasons[label] = "The question is about a potentially unsafe physical hazard or experiment."
        elif label == "VULN_EXPLOIT":
            reasons[label] = "The question suggests exploitation of vulnerability or manipulation."
        elif label == "GENERIC_INTENT":
            reasons[label] = "The question does not show a stronger specific risk-framing signal."
        evidence = evidence_by_g2.get(label)
        if evidence:
            matched_phrases = ", ".join(evidence.get("matched_phrases", [])[:2])
            if matched_phrases:
                reasons[label] = reasons.get(label, "The question matched a trained intent pattern.")
                reasons[label] += f" Block J phrase evidence matched: {matched_phrases}."
    return reasons


def _gl_signals(guidelines: list[str], age_band: str) -> dict[str, GLSignal]:
    active = set(guidelines)
    signals: dict[str, GLSignal] = {}
    for gl_id, guideline in GUIDELINES.items():
        triggered = gl_id in active
        signals[gl_id] = GLSignal(
            name=guideline["name"],
            triggered=triggered,
            confidence=0.99 if triggered else 0.01,
            emits=dict(guideline.get("emits", {})) if triggered else {},
        )
    return signals


def _build_decision(normalized: dict[str, object]) -> GuardrailDecision:
    message = str(normalized["text"]).strip()
    recent_context_items = [str(item) for item in normalized.get("recent_context", [])]
    recent_context = " ".join(item for item in recent_context_items if item.strip()) or "none"
    age = int(normalized.get("child_profile", {}).get("age", 10))
    requested_age_band = str(normalized.get("child_profile", {}).get("age_group", "")).strip() or None
    age_band = resolve_age_band(age, requested_age_band)
    language = str(normalized.get("child_profile", {}).get("language", "en"))

    clean_question = normalize(message)
    clean_context = normalize(recent_context if recent_context != "none" else "")
    topic = classify_topic(clean_question)
    g1 = classify_g1(clean_question)
    intent_evidence = match_intent_lexicon(clean_question, clean_context)
    g2 = classify_g2(clean_question, clean_context) or ["NEUTRAL_FACT"]
    primary_g2 = g2[0]
    g3, modifiers = compute_g3([primary_g2])
    g4 = compute_g4(g1, g2, g3, modifiers)
    guidelines = assign_gl(age_band, g1, g2, message)
    prompt = build_generated_prompt(age_band, g1, g2, g3, modifiers, g4, message)
    contract = build_gate_prompt_contract(g4, g3, g2, age_band, set(guidelines))
    contract["generated_prompt"] = prompt
    contract["resolved_age_band"] = age_band

    secrecy_from_parent = any(term in clean_question for term in ("hide bad marks", "hide this", "chupaun", "don't tell my parents", "dont tell my parents"))

    if g4 in {"BLOCK", "BLOCK_HARD", "BLOCK_ESCALATE"}:
        response_mode = "safe_refusal"
        policy_bucket = "soft_block"
    elif g4 in {"TRANSFORM", "TRANSFORM_HOLD"}:
        response_mode = "guide_or_redirect" if g4 == "TRANSFORM" else "clarify_then_answer"
        policy_bucket = "soft_block" if secrecy_from_parent else "allowed"
    else:
        response_mode = "neutral_age_calibrated_explain"
        policy_bucket = "allowed"

    decision_fields = {
        "allow_llm": g4 not in {"BLOCK", "BLOCK_HARD", "BLOCK_ESCALATE"},
        "allow_rag": False,
        "response_mode": response_mode,
        "risk_level": {"SV0": "low", "SV1": "low", "SV2": "medium", "SV3": "high"}.get(g3, "medium"),
        "parent_visible": g4 in {"BLOCK_ESCALATE", "BLOCK_HARD"},
    }
    gates = {"topic": topic, "G1": g1, "G2": primary_g2, "G3": g3, "G4": g4}

    return GuardrailDecision(
        input={"question": message, "age_band": age_band, "language": language, "recent_context": recent_context},
        reason=build_classifier_reason(g1, g2, guidelines, message, intent_evidence),
        g1_reason=build_g1_reason(g1, g2, guidelines, message),
        g2_reasons=build_g2_reasons(g1, g2, message, intent_evidence),
        gl_signals=_gl_signals(guidelines, age_band),
        active_gls=guidelines,
        gates=gates,
        decision=decision_fields,
        policy_bucket=policy_bucket,
        safety_category=primary_g2,
        response_mode=response_mode,
        risk_level=str(decision_fields["risk_level"]),
        parent_visible=bool(decision_fields["parent_visible"]),
        confidence=0.99,
        guideline_tags=guidelines,
        signals={"topic": topic, "g2_labels": ";".join(g2)},
        gate_values=gates,
        prompt_contract=contract,
        classifier_metadata={
            "backend": "heuristic",
            "backend_version": "rules-v1",
            "rollout_mode": load_classifier_runtime_config().rollout_mode,
            "g2_threshold": G2_ACTIVATION_THRESHOLD,
            "head_confidences": {
                "GL": {gl_id: (0.99 if gl_id in guidelines else 0.01) for gl_id in GUIDELINES},
                "G1": 0.99,
                "G2": {label: (0.99 if label in g2 else 0.01) for label in G2_META.keys()},
                "G3": 0.99,
                "G4": 0.99,
                "intent_lexicon": intent_evidence,
            },
        },
    )


def classify_heuristic(normalized: dict[str, object]) -> GuardrailDecision:
    return _build_decision(normalized)


def classify_artifact(normalized: dict[str, object]) -> GuardrailDecision:
    decision = _build_decision(normalized)
    return decision.model_copy(
        update={
            "classifier_metadata": {
                **decision.classifier_metadata,
                "backend": "artifact",
                "backend_version": "lexical-artifact-v1",
            }
        }
    )


def classify_slm(normalized: dict[str, object], core: str | None = None, threshold: float = G2_ACTIVATION_THRESHOLD) -> GuardrailDecision:
    from training.slm_classifier.slm_backend import build_decision_from_slm

    return build_decision_from_slm(normalized, core=core, threshold=threshold)


def classify_slm_pure(normalized: dict[str, object], core: str | None = None, threshold: float = G2_ACTIVATION_THRESHOLD) -> GuardrailDecision:
    from training.slm_classifier.slm_backend import build_decision_from_slm_pure

    return build_decision_from_slm_pure(normalized, core=core, threshold=threshold)


def classify(normalized: dict[str, object]) -> GuardrailDecision:
    config = load_classifier_runtime_config()
    if config.selected_backend == "slm":
        try:
            return classify_slm(normalized)
        except Exception:
            return classify_heuristic(normalized)
    if config.selected_backend == "artifact":
        return classify_artifact(normalized)
    return classify_heuristic(normalized)
