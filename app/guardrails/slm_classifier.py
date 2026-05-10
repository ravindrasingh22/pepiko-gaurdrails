from __future__ import annotations

import re

from app.guardrails.gate_mapper import AGE_POLICY, GUIDELINES, resolve_age_band
from app.models.guardrail_decision import GLSignal, GuardrailDecision
from training.slm_classifier.runtime_config import load_classifier_runtime_config

TOKEN_RE = re.compile(r"[a-z0-9']+")

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
    ("Safety", ("fire", "shock", "poison", "electricity", "burn", "explosion", "knife", "chemical")),
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
    "SCIENCE": ("space", "earth", "moon", "sun", "planet", "star", "galaxy", "galaxies", "universe", "black hole", "gravity", "white dwarf", "physics", "animal", "plant", "chemical", "dark energy", "hawking radiation", "relativity", "chandrasekhar"),
    "TECHNOLOGY": ("computer", "internet", "ai", "chatgpt", "phone", "app", "password", "wifi", "software", "code", "hack"),
    "BELIEF": ("god", "religion", "faith", "heaven", "temple", "prayer", "pray", "mosque", "church", "gurdwara"),
    "DEATH_GRIEF": ("died", "death", "funeral", "grief", "miss someone", "why do people die"),
    "VIOLENCE": ("kill", "hurt", "fight", "weapon", "bomb", "terrorist", "poison", "attack"),
    "SAFETY_HAZARD": ("fire", "shock", "electricity", "burn", "explosion", "knife", "chemical", "lock"),
    "CIVIC_LAW": ("fake document", "cheat exam", "illegal", "bribe", "visa", "piracy", "tamper", "rig", "cheat", "advantage", "foul"),
}

G2_RULES = {
    "NEUTRAL_FACT": (r"^(what|why|how|when|where|who|explain|define|tell me)\b",),
    "PD": (r"\bshould i\b", r"\bwhat should i do\b", r"\bwhich should i choose\b", r"\btell me what is right\b", r"\bhide bad marks\b", r"\bhide this\b", r"\bchupaun\b", r"\bdon't tell my parents\b", r"\bdont tell my parents\b"),
    "COMPARATIVE": (r"\bwhich .* is better\b", r"\bwhich .* is worse\b", r"\bwho is superior\b", r"\bwhich religion is true\b", r"\bwhich religion is best\b"),
    "LP": (r"\bwhy are .* bad\b", r"\bwhy do all .*", r"\bare .* always\b"),
    "DANGEROUS": (
        r"\bhow to make .*bomb\b",
        r"\bhow to make .*weapon\b",
        r"\bhow to hurt\b",
        r"\bhow to poison\b",
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
    "GROOMING": (r"don't tell.*parents", r"dont tell.*parents", r"keep.*secret.*adult", r"adult.*wants.*meet", r"gave me gifts.*secret", r"older friend", r"secret chat"),
    "UNSAFE_CONTENT": (r"\bnude\b", r"\bsex video\b", r"\bsend private photo\b", r"\bchild sexual\b", r"\bporn\b"),
    "SELF_HARM": (r"\bhurt myself\b", r"\bwant to die\b", r"\bno reason to live\b", r"\bi want to disappear\b", r"\bsleep forever\b"),
    "BULLYING": (r"\bkids are mean\b", r"\bcalling me names\b", r"\bbully\b", r"\bleft out\b"),
    "EMOTIONAL": (r"\bi feel sad\b", r"\bi am afraid\b", r"\bi am crying\b", r"\bnobody cares\b", r"\bmiss them\b"),
    "AMBIGUOUS_RISK": (r"\bknife\b", r"\bchemical\b", r"\bpassword\b", r"\block\b", r"\bfire\b"),
    "COERCIVE_CONTROL": (r"\bcontrols me\b", r"\bthreatens me\b", r"\bforce me\b", r"\bwon't let me\b", r"\bwont let me\b"),
    "VULN_EXPLOIT": (r"\busing me\b", r"\btaking advantage\b", r"\bmanipulate me\b", r"\btargeting me\b"),
}

HIGH_RISK_G2 = {"DANGEROUS", "UNSAFE_CONTENT", "GROOMING", "SELF_HARM"}
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
    "COMPARATIVE": {"severity": 1, "modifiers": []},
    "LP": {"severity": 1, "modifiers": []},
    "PD": {"severity": 2, "modifiers": []},
    "EMOTIONAL": {"severity": 2, "modifiers": ["empathetic_tone", "emotional_support_required"]},
    "BULLYING": {"severity": 2, "modifiers": ["empathetic_tone", "no_curiosity_invite"]},
    "AMBIGUOUS_RISK": {"severity": 2, "modifiers": ["clarification_required", "no_curiosity_invite"]},
    "DANGEROUS": {"severity": 3, "modifiers": ["no_curiosity_invite", "no_content_engagement"]},
    "GROOMING": {"severity": 3, "modifiers": ["no_curiosity_invite", "zero_engagement", "safeguarding_concern"]},
    "UNSAFE_CONTENT": {"severity": 3, "modifiers": ["no_curiosity_invite", "no_content_engagement", "no_reason_given", "zero_engagement"]},
    "SELF_HARM": {"severity": 3, "modifiers": ["no_curiosity_invite", "empathetic_tone"]},
    "COERCIVE_CONTROL": {"severity": 3, "modifiers": ["no_curiosity_invite", "safeguarding_concern"]},
    "VULN_EXPLOIT": {"severity": 3, "modifiers": ["no_curiosity_invite", "safeguarding_concern"]},
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


def classify_g2(text: str) -> list[str]:
    labels: list[str] = []
    for label, patterns in G2_RULES.items():
        if any(re.search(pattern, text) for pattern in patterns):
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
    if "UNSAFE_CONTENT" in g2_labels or "GROOMING" in g2_labels:
        return "BLOCK_HARD"
    if "SELF_HARM" in g2_labels:
        return "BLOCK_ESCALATE"
    if "PD" in g2_labels and g1 in {"BELIEF", "DEATH_GRIEF"}:
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
    if "COMPARATIVE" in g2_labels and g1 == "BELIEF":
        tags.add("GL-02")
    if "PD" in g2_labels:
        tags.add("GL-03")
    if "LP" in g2_labels:
        tags.add("GL-04")
    if "HATE_GROUP" in g2_labels or g1 == "VIOLENCE" or "DANGEROUS" in g2_labels:
        tags.add("GL-05")
    if g1 == "DEATH_GRIEF" or "EMOTIONAL" in g2_labels or "SELF_HARM" in g2_labels:
        tags.add("GL-06")
    if is_complex_for_age(question, age_band):
        tags.add("GL-07")
    if "BULLYING" in g2_labels:
        tags.add("GL-09")
    if "GROOMING" in g2_labels:
        tags.add("GL-10")
    if "UNSAFE_CONTENT" in g2_labels:
        tags.add("GL-11")
    if "COERCIVE_CONTROL" in g2_labels:
        tags.add("GL-12")
    if "VULN_EXPLOIT" in g2_labels:
        tags.add("GL-13")
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
    topic = classify_topic(clean_question)
    g1 = classify_g1(clean_question)
    g2 = classify_g2(clean_question) or ["NEUTRAL_FACT"]
    g3, modifiers = compute_g3(g2)
    g4 = compute_g4(g1, g2, g3, modifiers)
    guidelines = assign_gl(age_band, g1, g2, message)
    prompt = build_generated_prompt(age_band, g1, g2, g3, modifiers, g4, message)
    contract = _age_contract(age_band)
    contract["modifiers"] = modifiers
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
    gates = {"topic": topic, "G1": g1, "G2": g2[0], "G2_all": g2, "G3": g3, "G4": g4}

    return GuardrailDecision(
        input={"question": message, "age_band": age_band, "language": language, "recent_context": recent_context},
        gl_signals=_gl_signals(guidelines, age_band),
        active_gls=guidelines,
        gates=gates,
        decision=decision_fields,
        policy_bucket=policy_bucket,
        safety_category=g2[0],
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
            "head_confidences": {
                "GL": {gl_id: (0.99 if gl_id in guidelines else 0.01) for gl_id in GUIDELINES},
                "G1": 0.99,
                "G2": 0.99,
                "G3": 0.99,
                "G4": 0.99,
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


def classify_slm(normalized: dict[str, object], core: str | None = None) -> GuardrailDecision:
    from training.slm_classifier.slm_backend import build_decision_from_slm

    return build_decision_from_slm(normalized, core=core)


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
