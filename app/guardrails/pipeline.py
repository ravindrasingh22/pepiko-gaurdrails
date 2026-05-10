from app.guardrails import (
    age_policy_engine,
    audit_logger,
    context_builder,
    conversation_guard,
    llm_safety_classifier,
    normalizer,
    output_validator,
    prompt_contract,
    rag_guard,
    rule_filter,
    safe_rewriter,
    slm_classifier,
)
from app.llm.model_router import select
from app.llm.ollama_client import generate
from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision
from app.models.schemas import GuardrailRunResponse
from training.slm_classifier.codebook import parse_codebook
from training.slm_classifier.runtime_config import load_classifier_runtime_config


CODEBOOK = parse_codebook()
CLASSIFIER_RUNTIME = load_classifier_runtime_config()
GL_NAME_MAP = {item.gl_id: item.name for item in CODEBOOK.labels}
GL_PURPOSE_MAP = {item.gl_id: item.purpose for item in CODEBOOK.labels}
G1_DESCRIPTION_MAP = {
    "FACT": "Pure descriptive or factual question about how the world works.",
    "BELIEF": "Question about religion, ideology, worldview, or belief systems.",
    "DEATH_GRIEF": "Question about death, loss, dying, or grief.",
    "VIOLENCE": "Question involving violence, conflict, harm, extremism, or dangerous acts.",
    "SCIENCE": "Question about biology, chemistry, physics, nature, or general science.",
    "TECHNOLOGY": "Question about computing, internet, AI, devices, or digital systems.",
    "SAFETY_HAZARD": "Question about dangerous real-world outcomes, accidents, or unsafe interactions.",
    "CIVIC_LAW": "Question about laws, rules, civic processes, or integrity.",
    "GENERIC": "Catch-all category for questions that do not clearly fit other G1 values.",
}
G4_DESCRIPTION_MAP = {
    "ALLOW": "Answer directly in an age-appropriate, calm, simple, and factual way.",
    "TRANSFORM": "Reframe the question safely and answer in an age-appropriate way without over-directing the child.",
    "TRANSFORM_HOLD": "Ask exactly one safe clarification question before answering.",
    "BLOCK": "Do not provide instructions or details. Give a safe minimal refusal.",
    "BLOCK_HARD": "Hard block: no content engagement, no instructions, no alternate topic discussion.",
    "BLOCK_ESCALATE": "Do not engage the content. Give a safe refusal and escalate toward trusted-adult support.",
}


def _compact_decision(decision: GuardrailDecision) -> dict[str, object]:
    active_gls = decision.active_gls or decision.guideline_tags
    active_signals = {
        gl_id: signal.model_dump()
        for gl_id, signal in decision.gl_signals.items()
        if gl_id in set(active_gls)
    }
    return {
        "input": decision.input,
        "active_gls": active_gls,
        "gl_signals": active_signals,
        "gates": decision.gates or decision.gate_values,
        "gate_values": decision.gates or decision.gate_values,
        "decision": decision.decision,
        "policy_bucket": decision.policy_bucket,
        "safety_category": decision.safety_category,
        "response_mode": decision.response_mode,
        "risk_level": decision.risk_level,
        "parent_visible": decision.parent_visible,
        "confidence": decision.confidence,
        "signals": decision.signals,
        "prompt_contract": decision.prompt_contract,
        "classifier_metadata": decision.classifier_metadata,
    }


def _decision_mismatches(primary: GuardrailDecision, shadow: GuardrailDecision) -> list[str]:
    mismatches: list[str] = []
    if set(primary.active_gls or primary.guideline_tags) != set(shadow.active_gls or shadow.guideline_tags):
        mismatches.append("gl_mismatch")
    primary_gates = primary.gates or primary.gate_values
    shadow_gates = shadow.gates or shadow.gate_values
    if primary_gates.get("G1") != shadow_gates.get("G1") or primary_gates.get("G2_all") != shadow_gates.get("G2_all"):
        mismatches.append("gate_mismatch")
    if primary_gates.get("G3") != shadow_gates.get("G3"):
        mismatches.append("severity_mismatch")
    if primary_gates.get("G4") != shadow_gates.get("G4"):
        mismatches.append("escalation_block_mismatch")
    return mismatches


def _final_prompt_for_decision(
    child_profile: ChildProfile,
    message: str,
    decision: GuardrailDecision,
) -> str:
    return prompt_contract.build(child_profile, message, decision, [])


def _templated_prompt(raw_prompt: str, age_band: str, g1: str, g2: list[str], g3: str, modifiers: list[str], g4: str, question: str) -> str:
    modifier_text = ", ".join(modifiers) if modifiers else "none"
    header = f"[Age: {age_band} | G1: {g1} | G2: {';'.join(g2)} | G3: {g3} | {modifier_text} | G4: {g4}]"
    templated = raw_prompt.replace(
        header,
        f"[Age: {{age_band}} | G1: {{g1}} | G2: {{g2}} | G3: {{g3}} | {{modifiers}} | G4: {{g4}}]",
    )
    return templated.replace(question, "{question}")


def _expanded_prompt(decision: GuardrailDecision, message: str, age_band: str, topic: str, g1: str, g2: list[str], g3: str, modifiers: list[str], g4: str, guidelines: list[str]) -> str:
    contract = decision.prompt_contract
    g2_descriptions = [
        CODEBOOK.g2_specs[item].description
        for item in g2
        if item in CODEBOOK.g2_specs and CODEBOOK.g2_specs[item].description
    ]
    guideline_descriptions = [
        f"{gl}: {GL_NAME_MAP.get(gl, gl)}"
        for gl in guidelines
    ]
    modifier_text = ", ".join(modifiers) if modifiers else "none"
    guideline_text = "; ".join(guideline_descriptions) if guideline_descriptions else "GL-01: Age calibration"
    g2_text = "; ".join(g2)
    g2_desc_text = " ".join(g2_descriptions) if g2_descriptions else "No additional risk framing detected."
    max_words = int(contract.get("max_words", 120))
    depth = str(contract.get("depth", "age_calibrated"))
    style = str(contract.get("max_answer_style", "age-calibrated"))
    tone = str(contract.get("tone", "age_calibrated"))
    return (
        f"[Age: {age_band} | Topic: {topic} | G1: {g1} | G2: {g2_text} | G3: {g3} | Modifiers: {modifier_text} | G4: {g4}] "
        f"You are PikuAI, a child-safe learning assistant. "
        f"Question: {message} "
        f"Topic classification: {topic}. "
        f"G1 meaning: {G1_DESCRIPTION_MAP.get(g1, g1)} "
        f"G2 meaning: {g2_desc_text} "
        f"G3 meaning: severity {g3} with modifiers {modifier_text}. "
        f"G4 action: {G4_DESCRIPTION_MAP.get(g4, g4)} "
        f"Applicable guidelines: {guideline_text}. "
        f"Age band policy: {age_band}; keep under {max_words} words; depth {depth}; style {style}; tone {tone}. "
        f"Return a response that follows the G4 action exactly."
    )


def _run_response_from_decision(decision: GuardrailDecision, message: str, stage_outputs: dict[str, object] | None = None) -> GuardrailRunResponse:
    gates = decision.gates or decision.gate_values
    topic = str(gates.get("topic", "General Learning"))
    age_band = str(decision.input.get("age_band", "11-12"))
    guidelines = list(decision.active_gls or decision.guideline_tags)
    g1 = str(gates.get("G1", "GENERIC"))
    g2 = list(gates.get("G2_all", [gates.get("G2", "NEUTRAL_FACT")]))
    g3 = str(gates.get("G3", "SV0"))
    g4 = str(gates.get("G4", "ALLOW"))
    modifiers = list(decision.prompt_contract.get("modifiers", []))
    raw_prompt = str(decision.prompt_contract.get("generated_prompt", _final_prompt_for_decision(ChildProfile(age=12, age_group=age_band, language="en"), message, decision)))
    return GuardrailRunResponse(
        topic=topic,
        question=message,
        age_band=age_band,
        guidelines=guidelines,
        g1=g1,
        g2=g2,
        g3={"severity": g3, "modifiers": modifiers},
        g4=g4,
        raw_generated_prompt=raw_prompt,
        generated_prompt=_expanded_prompt(decision, message, age_band, topic, g1, g2, g3, modifiers, g4, guidelines),
        metadata={
            "age_band": age_band,
            "g1": g1,
            "g2": g2,
            "g3": g3,
            "modifiers": modifiers,
            "g4": g4,
            "question": message,
            "topic": topic,
            "guidelines": guidelines,
            "g1_description": G1_DESCRIPTION_MAP.get(g1, g1),
            "g2_descriptions": [CODEBOOK.g2_specs[item].description for item in g2 if item in CODEBOOK.g2_specs],
            "g4_description": G4_DESCRIPTION_MAP.get(g4, g4),
            "guideline_descriptions": {gl: {"name": GL_NAME_MAP.get(gl, gl), "purpose": GL_PURPOSE_MAP.get(gl, "")} for gl in guidelines},
            "prompt_template": _templated_prompt(raw_prompt, age_band, g1, g2, g3, modifiers, g4, message),
        },
        classifier={
            "active_gls": guidelines,
            "gl_signals": {
                gl_id: signal.model_dump()
                for gl_id, signal in decision.gl_signals.items()
                if gl_id in set(guidelines)
            },
            "gates": gates,
            "decision": decision.decision,
            "confidence": decision.confidence,
            "classifier_metadata": decision.classifier_metadata,
        },
        final_policy_bucket=decision.policy_bucket,
        stage_outputs=dict(stage_outputs or {}),
    )


def _should_call_llm_safety_classifier(decision: GuardrailDecision, normalized_text: str, recent_context: list[str]) -> bool:
    low_confidence = decision.confidence < 0.65
    high_risk = decision.gates.get("G3") in {"SV3", "SV4"}
    ambiguous = decision.gates.get("G2") == "GENERIC_INTENT" and decision.gates.get("G3") != "SV0"
    multi_turn = len(recent_context) > 1
    return low_confidence or high_risk or ambiguous or multi_turn or len(normalized_text.split()) > 40


async def run_classification_sequence(
    child_profile: ChildProfile,
    message: str,
    session_id: str,
    recent_context: list[str],
) -> tuple[GuardrailDecision, dict[str, object], list[object]]:
    audit_log = []
    stage_outputs: dict[str, object] = {}

    context = await context_builder.build(child_profile, message, session_id, recent_context)
    stage_outputs["context_builder"] = context
    audit_logger.log(audit_log, "context_builder", {"session_id": session_id})

    normalized = normalizer.normalize(context)
    stage_outputs["normalizer"] = normalized
    audit_logger.log(audit_log, "normalizer", {"text": normalized["text"]})

    rule_decision = rule_filter.check(normalized)
    stage_outputs["rule_filter"] = rule_decision.model_dump() if rule_decision else None
    audit_logger.log(audit_log, "rule_filter", {"triggered": rule_decision is not None})
    if rule_decision and rule_decision.is_terminal:
        return rule_decision, stage_outputs, audit_log

    primary_decision = slm_classifier.classify(normalized)
    stage_outputs["slm_classifier"] = _compact_decision(primary_decision)
    audit_logger.log(audit_log, "slm_classifier", {"confidence": primary_decision.confidence})

    if CLASSIFIER_RUNTIME.rollout_mode == "shadow":
        shadow_backend = "slm" if CLASSIFIER_RUNTIME.selected_backend != "slm" else "heuristic"
        try:
            shadow_decision = slm_classifier.classify_slm(normalized) if shadow_backend == "slm" else slm_classifier.classify_heuristic(normalized)
            stage_outputs["slm_classifier_shadow"] = {
                "backend": shadow_backend,
                "decision": _compact_decision(shadow_decision),
                "disagreements": _decision_mismatches(primary_decision, shadow_decision),
            }
        except Exception as exc:
            stage_outputs["slm_classifier_shadow"] = {
                "backend": shadow_backend,
                "error": str(exc),
                "disagreements": ["shadow_failed"],
            }

    safety_decision = primary_decision
    if _should_call_llm_safety_classifier(primary_decision, str(normalized["text"]), list(context.get("recent_context", []))):
        safety_decision = llm_safety_classifier.classify(normalized)
    stage_outputs["llm_safety_classifier"] = _compact_decision(safety_decision)
    audit_logger.log(audit_log, "llm_safety_classifier", {"used_fallback": safety_decision != primary_decision})

    age_decision = age_policy_engine.apply(child_profile, safety_decision)
    stage_outputs["age_policy_engine"] = _compact_decision(age_decision)
    audit_logger.log(audit_log, "age_policy_engine", {"parent_visible": age_decision.parent_visible})

    conversation_decision = conversation_guard.check(session_id, age_decision, context)
    stage_outputs["conversation_guard"] = _compact_decision(conversation_decision)
    audit_logger.log(audit_log, "conversation_guard", {"safety_category": conversation_decision.safety_category})
    return conversation_decision, stage_outputs, audit_log


async def run_llm_sequence(
    child_profile: ChildProfile,
    message: str,
    session_id: str,
    recent_context: list[str],
) -> tuple[GuardrailDecision, dict[str, object], list[object], list[dict[str, object]], str, str]:
    decision, stage_outputs, audit_log = await run_classification_sequence(
        child_profile=child_profile,
        message=message,
        session_id=session_id,
        recent_context=recent_context,
    )

    if not bool(decision.decision.get("allow_llm", decision.policy_bucket == "allowed")):
        return decision, stage_outputs, audit_log, [], "", _terminal_answer(decision)

    rag_context = rag_guard.retrieve_if_allowed(message, child_profile, decision)
    stage_outputs["rag_guard"] = rag_context
    audit_logger.log(audit_log, "rag_guard", {"chunk_count": len(rag_context)})

    prompt = prompt_contract.build(child_profile, message, decision, rag_context)
    stage_outputs["prompt_contract"] = {"prompt_preview": prompt[:220], "prompt": prompt}
    audit_logger.log(audit_log, "prompt_contract", {"built": True})

    model_name = select(decision)
    stage_outputs["model_router"] = {"model_name": model_name}
    audit_logger.log(audit_log, "model_router", {"model_name": model_name})

    raw_answer = await generate(model_name, prompt)
    stage_outputs["answer_model"] = {"raw_answer": raw_answer}
    audit_logger.log(audit_log, "answer_model", {"llm_called": True})
    return decision, stage_outputs, audit_log, rag_context, prompt, raw_answer


async def run_piku_guardrail_pipeline(
    child_profile: ChildProfile,
    message: str,
    session_id: str,
    recent_context: list[str],
) -> GuardrailRunResponse:
    decision, stage_outputs, audit_log = await run_classification_sequence(
        child_profile=child_profile,
        message=message,
        session_id=session_id,
        recent_context=recent_context,
    )
    stage_outputs.setdefault("output_validator", {"safe_to_show": True, "source": "pipeline_summary"})

    return _run_response_from_decision(decision, message, stage_outputs)
