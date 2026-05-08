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


def _terminal_answer(decision: GuardrailDecision) -> str:
    if decision.response_mode in {"trusted_adult", "trusted_adult_escalation"}:
        return "This sounds important. Please talk to a trusted adult right now so they can help you safely."
    return "I can't help with that. Let's choose a safe next step together."


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
        "decision": decision.decision,
        "policy_bucket": decision.policy_bucket,
        "safety_category": decision.safety_category,
        "response_mode": decision.response_mode,
        "risk_level": decision.risk_level,
        "parent_visible": decision.parent_visible,
        "confidence": decision.confidence,
        "signals": decision.signals,
        "prompt_contract": decision.prompt_contract,
    }


def _dedupe_stage_outputs_for_run(stage_outputs: dict[str, object]) -> dict[str, object]:
    deduped = dict(stage_outputs)
    deduped.pop("prompt_contract", None)
    for key in ("slm_classifier", "llm_safety_classifier", "age_policy_engine", "conversation_guard"):
        payload = deduped.get(key)
        if isinstance(payload, dict):
            payload = dict(payload)
            payload.pop("prompt_contract", None)
            deduped[key] = payload
    return deduped


def _final_prompt_for_decision(
    child_profile: ChildProfile,
    message: str,
    decision: GuardrailDecision,
) -> str:
    return prompt_contract.build(child_profile, message, decision, [])


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

    slm_decision = slm_classifier.classify(normalized)
    stage_outputs["slm_classifier"] = _compact_decision(slm_decision)
    audit_logger.log(audit_log, "slm_classifier", {"confidence": slm_decision.confidence})

    safety_decision = slm_decision
    if _should_call_llm_safety_classifier(slm_decision, str(normalized["text"]), list(context.get("recent_context", []))):
        safety_decision = llm_safety_classifier.classify(normalized)
    stage_outputs["llm_safety_classifier"] = _compact_decision(safety_decision)
    audit_logger.log(audit_log, "llm_safety_classifier", {"used_fallback": safety_decision != slm_decision})

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

    if decision.is_terminal:
        final_answer = _terminal_answer(decision)
        return GuardrailRunResponse(
            final_policy_bucket=decision.policy_bucket,
            final_response_mode=decision.response_mode,
            llm_called=False,
            parent_visible=decision.parent_visible,
            safe_to_show=True,
            final_answer=final_answer,
            prompt_contract=decision.prompt_contract,
            final_prompt=_final_prompt_for_decision(child_profile, message, decision),
            audit_log=audit_log,
            stage_outputs=_dedupe_stage_outputs_for_run(stage_outputs),
        )

    if decision.policy_bucket != "allowed":
        final_answer = _terminal_answer(decision)
        return GuardrailRunResponse(
            final_policy_bucket=decision.policy_bucket,
            final_response_mode=decision.response_mode,
            llm_called=False,
            parent_visible=decision.parent_visible,
            safe_to_show=True,
            final_answer=final_answer,
            prompt_contract=decision.prompt_contract,
            final_prompt=_final_prompt_for_decision(child_profile, message, decision),
            audit_log=audit_log,
            stage_outputs=_dedupe_stage_outputs_for_run(stage_outputs),
        )

    decision, stage_outputs, audit_log, _, prompt, raw_answer = await run_llm_sequence(
        child_profile=child_profile,
        message=message,
        session_id=session_id,
        recent_context=recent_context,
    )

    validation = output_validator.validate(child_profile, message, raw_answer, decision)
    stage_outputs["output_validator"] = validation
    audit_logger.log(audit_log, "output_validator", validation)

    final_answer = raw_answer if validation["safe_to_show"] else safe_rewriter.repair_or_fallback(
        raw_answer,
        validation,
        decision,
        child_profile,
    )
    stage_outputs["safe_rewriter"] = {"rewritten": not validation["safe_to_show"]}
    audit_logger.log(audit_log, "safe_rewriter", {"rewritten": not validation["safe_to_show"]})

    return GuardrailRunResponse(
        final_policy_bucket=decision.policy_bucket,
        final_response_mode=decision.response_mode,
        llm_called=True,
        parent_visible=decision.parent_visible,
        safe_to_show=validation["safe_to_show"],
        final_answer=final_answer,
        prompt_contract=decision.prompt_contract,
        final_prompt=prompt,
        audit_log=audit_log,
        stage_outputs=_dedupe_stage_outputs_for_run(stage_outputs),
    )
