from __future__ import annotations

from app.guardrails.gate_mapper import GUIDELINES, build_guardrail_decision
from app.models.guardrail_decision import GLSignal, GuardrailDecision
from training.slm_classifier.artifact_backend import build_decision_from_artifact, load_artifact


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _contains_all(text: str, terms: tuple[str, ...]) -> bool:
    return all(term in text for term in terms)


def _signal(name: str, triggered: bool, confidence: float, emits: dict[str, bool | str]) -> GLSignal:
    return GLSignal(name=name, triggered=triggered, confidence=confidence, emits=emits if triggered else {})


def _emit_values(gl_id: str, age_band: str) -> dict[str, bool | str]:
    payload = dict(GUIDELINES[gl_id].get("emits", {}))
    if "age_band" in payload:
        payload["age_band"] = age_band
    return payload


def _is_sharp_tool_request(full_text: str) -> bool:
    action_terms = ("cut", "slice", "chop", "carve", "use a knife", "knife")
    target_terms = ("meat", "chicken", "fish", "steak", "blade", "sharp")
    asks_how = _contains_any(full_text, ("how to", "how do i", "can i", "what is the way to"))
    return (_contains_any(full_text, action_terms) and _contains_any(full_text, target_terms)) or (asks_how and _contains_all(full_text, ("cut", "meat")))


def _heuristic_scores(message: str, full_text: str, age_band: str) -> dict[str, float]:
    return {
        "GL-01": 0.99,
        "GL-02": 0.94 if _contains_any(full_text, ("better religion", "true religion", "best religion", "which religion is best", "which religion is right")) else 0.0,
        "GL-03": 0.92 if _contains_any(full_text, ("should i", "what should i", "which should i", "what religion should i", "what should i believe")) else 0.0,
        "GL-04": 0.82 if _contains_any(full_text, ("superior", "inferior", "bad people", "those people", "best religion")) else 0.0,
        "GL-05": 0.97 if _contains_any(full_text, ("kill", "hurt", "attack", "bomb", "radical", "terror")) or (age_band == "5-8" and _is_sharp_tool_request(full_text)) else 0.0,
        "GL-06": 0.93 if _contains_any(full_text, ("death", "died", "die", "grief", "loss", "funeral", "miss them")) else 0.0,
        "GL-07": 0.76 if len(message.split()) > 30 or (age_band == "5-8" and _contains_any(full_text, ("quantum", "metaphysics", "neuroscience", "philosophy"))) else 0.0,
        "GL-08": 0.91 if _contains_any(full_text, ("hate", "dirty", "stupid religion", "those people are")) else 0.0,
        "GL-09": 0.94 if _contains_any(full_text, ("who is god", "why do people pray", "temple", "church", "mosque", "religion", "faith", "belief")) else 0.0,
        "GL-10": 0.96 if _contains_any(full_text, ("don't tell your parents", "dont tell your parents", "online friend told me not to tell", "secret chat", "older friend", "keep this secret")) else 0.0,
        "GL-11": 0.97 if _contains_any(full_text, ("porn", "nude", "explicit", "make a bomb", "how do i make a bomb", "sex with")) else 0.0,
        "GL-12": 0.94 if _contains_any(full_text, ("controls me", "threatens me", "force me", "won't let me", "wont let me")) else 0.0,
        "GL-13": 0.89 if _contains_any(full_text, ("using me", "taking advantage", "manipulate me", "targeting me", "online friend told me not to tell")) else 0.0,
    }


def _build_gl_signals(scores: dict[str, float], age_band: str, threshold: float = 0.5) -> dict[str, GLSignal]:
    gl_signals: dict[str, GLSignal] = {}
    for gl_id, guideline in GUIDELINES.items():
        confidence = float(scores.get(gl_id, 0.0))
        triggered = confidence >= threshold
        gl_signals[gl_id] = _signal(guideline["name"], triggered, confidence if triggered else max(confidence, 0.01), _emit_values(gl_id, age_band))
    return gl_signals


def classify_heuristic(normalized: dict[str, object]) -> GuardrailDecision:
    message = str(normalized["text"])
    recent_context = " ".join(str(item) for item in normalized.get("recent_context", []))
    full_text = f"{message} {recent_context}".lower().strip()
    age_band = str(normalized.get("child_profile", {}).get("age_group", "5-8"))
    language = str(normalized.get("child_profile", {}).get("language", "en"))

    scores = _heuristic_scores(message, full_text, age_band)
    gl_signals = _build_gl_signals(scores, age_band)
    secrecy_from_parent = _contains_any(full_text, ("hide bad marks", "hide this", "mummy se kaise chupaun", "chupaun", "don't tell my parents", "dont tell my parents"))
    payload = build_guardrail_decision(question=message, age_band=age_band, language=language, recent_context=recent_context or "none", gl_signals=gl_signals)
    decision_fields = payload["decision"]
    gates = payload["gates"]
    if secrecy_from_parent and gates["G4"] == "ALLOW":
        gates["G4"] = "TRANSFORM"
        gates["G3"] = "SV2"
        gates["G2"] = "PD"
        gates["G2_all"] = ["PD"]
        decision_fields = {"allow_llm": False, "allow_rag": False, "response_mode": "guide_or_redirect", "risk_level": "medium", "parent_visible": True}
    gl_confidences = [signal.confidence for signal in gl_signals.values() if signal.triggered]
    confidence = min(gl_confidences) if gl_confidences else 0.8
    policy_bucket = "allowed" if decision_fields["allow_llm"] else "soft_block"
    return GuardrailDecision(
        input=payload["input"],
        gl_signals=gl_signals,
        active_gls=payload["active_gls"],
        gates=gates,
        decision=decision_fields,
        policy_bucket=policy_bucket,
        safety_category=gates["G2"],
        response_mode=str(decision_fields["response_mode"]),
        risk_level=str(decision_fields["risk_level"]),
        parent_visible=bool(decision_fields["parent_visible"]),
        confidence=confidence,
        guideline_tags=payload["active_gls"],
        signals={**{key: value for signal in gl_signals.values() for key, value in signal.emits.items()}, **({"secrecy_from_parent": True} if secrecy_from_parent else {})},
        gate_values=gates,
        prompt_contract=payload["prompt_contract"],
    )


def classify_artifact(normalized: dict[str, object]) -> GuardrailDecision:
    artifact = load_artifact()
    if artifact is None:
        return classify_heuristic(normalized)
    message = str(normalized["text"])
    recent_context = " ".join(str(item) for item in normalized.get("recent_context", []))
    age_band = str(normalized.get("child_profile", {}).get("age_group", "5-8"))
    language = str(normalized.get("child_profile", {}).get("language", "en"))
    return build_decision_from_artifact(
        question=message,
        age_band=age_band,
        language=language,
        recent_context=recent_context or "none",
        artifact=artifact,
    )


def classify(normalized: dict[str, object]) -> GuardrailDecision:
    artifact = load_artifact()
    if artifact is not None:
        return classify_artifact(normalized)
    return classify_heuristic(normalized)
