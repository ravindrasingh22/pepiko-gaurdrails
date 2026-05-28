from __future__ import annotations

from uuid import uuid4

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
from app.guardrails.runtime_contracts import classifier_output_from_decision, gate_output_from_classifier
from app.llm.model_router import select
from app.llm.ollama_client import generate
from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision
from app.models.schemas import GuardrailRunResponse
from training.slm_classifier.runtime_config import load_classifier_runtime_config

CLASSIFIER_RUNTIME = load_classifier_runtime_config()


def _terminal_answer(decision: GuardrailDecision) -> str:
    gates = decision.gates or decision.gate_values
    g4 = str(gates.get("G4", "BLOCK"))
    modifiers = set(decision.prompt_contract.get("modifiers", []))
    if g4 == "BLOCK_HARD" or "no_content_engagement" in modifiers:
        return "I can't help with that."
    if "safeguarding_concern" in modifiers or g4 == "BLOCK_ESCALATE":
        return "I can't help with that. Please talk to a trusted adult you can reach right now."
    if "empathetic_tone" in modifiers:
        return "I'm sorry you're dealing with this. I can't help with that, but you can talk to a trusted adult."
    return "I can't help with that, but we can talk about something safer."


def _g2_score_payload(decision: GuardrailDecision) -> dict[str, object]:
    classifier_metadata = dict(decision.classifier_metadata or {})
    head_confidences = dict(classifier_metadata.get("head_confidences", {}))
    raw_g2_scores = head_confidences.get("G2_primary", {})
    if isinstance(raw_g2_scores, dict):
        g2_scores = {str(label): float(score) for label, score in raw_g2_scores.items()}
    else:
        g2_scores = {}
    active_g2 = [str((decision.gates or decision.gate_values).get("G2", ""))]
    threshold = float(classifier_metadata.get("g2_threshold", 0.5))
    ranked = [
        {"id": label, "score": score, "active": label in active_g2}
        for label, score in sorted(g2_scores.items(), key=lambda item: item[1], reverse=True)
    ]
    active_ranked = [item for item in ranked if item["active"]]
    return {
        "threshold": threshold,
        "active_lovs": active_ranked,
        "all_lovs": ranked,
    }


def _compact_decision(decision: GuardrailDecision) -> dict[str, object]:
    active_gls = decision.active_gls or decision.guideline_tags
    active_signals = {
        gl_id: signal.model_dump()
        for gl_id, signal in decision.gl_signals.items()
        if gl_id in set(active_gls)
    }
    g2_scores = _g2_score_payload(decision)
    return {
        "input": decision.input,
        "reason": decision.reason,
        "g1_reason": decision.g1_reason,
        "g2_reasons": decision.g2_reasons,
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
        "g2_scores": g2_scores,
        "prompt_contract": decision.prompt_contract,
        "classifier_metadata": decision.classifier_metadata,
    }


def _decision_mismatches(primary: GuardrailDecision, shadow: GuardrailDecision) -> list[str]:
    mismatches: list[str] = []
    if set(primary.active_gls or primary.guideline_tags) != set(shadow.active_gls or shadow.guideline_tags):
        mismatches.append("gl_mismatch")
    primary_gates = primary.gates or primary.gate_values
    shadow_gates = shadow.gates or shadow.gate_values
    if primary_gates.get("G1") != shadow_gates.get("G1") or primary_gates.get("G2") != shadow_gates.get("G2"):
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


def _run_response_from_decision(
    decision: GuardrailDecision,
    child_profile: ChildProfile,
    message: str,
    recent_context: list[str],
) -> GuardrailRunResponse:
    prompt = str(decision.prompt_contract.get("generated_prompt") or _final_prompt_for_decision(child_profile, message, decision))
    return GuardrailRunResponse(
        question=message,
        context=list(recent_context),
        age_band=child_profile.age_group,
        prompt=prompt,
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
    trace_id = uuid4().hex
    audit_log = []
    stage_outputs: dict[str, object] = {"trace_id": trace_id}

    context = await context_builder.build(child_profile, message, session_id, recent_context)
    stage_outputs["context_builder"] = context
    audit_logger.log(audit_log, trace_id, "context_builder", {"session_id": session_id, "question": message}, "input")

    normalized = normalizer.normalize(context)
    stage_outputs["normalizer"] = normalized
    audit_logger.log(audit_log, trace_id, "normalizer", {"text": normalized["text"], "resolved_age_band": normalized["resolved_age_band"]}, "output")

    rule_decision = rule_filter.check(normalized)
    stage_outputs["rule_filter"] = rule_decision.model_dump() if rule_decision else None
    audit_logger.log(audit_log, trace_id, "rule_filter", {"triggered": rule_decision is not None}, "output")
    if rule_decision and rule_decision.is_terminal:
        return rule_decision, stage_outputs, audit_log

    primary_decision = slm_classifier.classify(normalized)
    stage_outputs["slm_classifier"] = _compact_decision(primary_decision)
    classifier_output = classifier_output_from_decision(message, ChildProfile(**normalized["child_profile"]), primary_decision)
    gate_output = gate_output_from_classifier(classifier_output)
    stage_outputs["classifier_output"] = classifier_output
    stage_outputs["gate_engine"] = gate_output
    audit_logger.log(audit_log, trace_id, "classifier", classifier_output, "output")
    audit_logger.log(audit_log, trace_id, "gate_engine", gate_output, "output")

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
    audit_logger.log(audit_log, trace_id, "llm_safety_classifier", {"used_fallback": safety_decision != primary_decision}, "output")

    age_decision = age_policy_engine.apply(child_profile, safety_decision)
    stage_outputs["age_policy_engine"] = _compact_decision(age_decision)
    audit_logger.log(audit_log, trace_id, "age_policy_engine", {"parent_visible": age_decision.parent_visible}, "output")

    conversation_decision = conversation_guard.check(session_id, age_decision, context)
    stage_outputs["conversation_guard"] = _compact_decision(conversation_decision)
    audit_logger.log(audit_log, trace_id, "conversation_guard", {"safety_category": conversation_decision.safety_category}, "output")
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
    audit_logger.log(audit_log, stage_outputs["trace_id"], "rag_guard", {"chunk_count": len(rag_context)}, "output")

    prompt = prompt_contract.build(child_profile, message, decision, rag_context)
    stage_outputs["prompt_contract"] = dict(decision.prompt_contract.get("prompt_contract_payload", {}))
    audit_logger.log(audit_log, stage_outputs["trace_id"], "prompt_contract", {"template_id": decision.prompt_contract.get("template_id", ""), "prompt_preview": prompt[:220]}, "output")

    model_name = select(decision)
    stage_outputs["model_router"] = {"model_name": model_name}
    audit_logger.log(audit_log, stage_outputs["trace_id"], "model_router", {"model_name": model_name}, "output")

    raw_answer = await generate(model_name, prompt)
    stage_outputs["answer_model"] = {"raw_answer": raw_answer}
    audit_logger.log(audit_log, stage_outputs["trace_id"], "answer_model", {"llm_called": True}, "output")
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
    prompt = prompt_contract.build(child_profile, message, decision, [])
    decision.prompt_contract["generated_prompt"] = prompt
    stage_outputs["audit_log"] = [event.model_dump() for event in audit_log]
    return _run_response_from_decision(decision, child_profile, message, recent_context)
