from fastapi import APIRouter

from app.guardrails import output_validator, safe_rewriter
from app.guardrails.pipeline import run_classification_sequence, run_llm_sequence, run_piku_guardrail_pipeline
from app.models.schemas import (
    ClassificationTestRequest,
    ClassificationTestResponse,
    GuardrailRunRequest,
    GuardrailRunResponse,
    LLMTestRequest,
    LLMTestResponse,
    ValidatorTestRequest,
    ValidatorTestResponse,
)

router = APIRouter()


@router.post("/guardrails/run", response_model=GuardrailRunResponse)
async def run_guardrails(payload: GuardrailRunRequest) -> GuardrailRunResponse:
    return await run_piku_guardrail_pipeline(
        child_profile=payload.child_profile,
        message=payload.message,
        session_id=payload.session_id,
        recent_context=payload.recent_context,
    )


@router.post("/guardrails/test/classification", response_model=ClassificationTestResponse)
async def test_classification(payload: ClassificationTestRequest) -> ClassificationTestResponse:
    decision, stage_outputs, _ = await run_classification_sequence(
        child_profile=payload.child_profile,
        message=payload.message,
        session_id=payload.session_id,
        recent_context=payload.recent_context,
    )
    return ClassificationTestResponse(decision=decision, stage_outputs=stage_outputs)


@router.post("/guardrails/test/llm-call", response_model=LLMTestResponse)
async def test_llm_call(payload: LLMTestRequest) -> LLMTestResponse:
    decision, stage_outputs, _, rag_context, prompt, raw_answer = await run_llm_sequence(
        child_profile=payload.child_profile,
        message=payload.message,
        session_id=payload.session_id,
        recent_context=payload.recent_context,
    )
    model_name = str(stage_outputs.get("model_router", {}).get("model_name", "not_called"))
    return LLMTestResponse(
        decision=decision,
        model_name=model_name,
        prompt=prompt,
        rag_context=rag_context,
        raw_answer=raw_answer,
        stage_outputs=stage_outputs,
    )


@router.post("/guardrails/test/validator", response_model=ValidatorTestResponse)
async def test_validator(payload: ValidatorTestRequest) -> ValidatorTestResponse:
    decision, stage_outputs, _, _, _, generated_answer = await run_llm_sequence(
        child_profile=payload.child_profile,
        message=payload.message,
        session_id=payload.session_id,
        recent_context=payload.recent_context,
    )
    answer_checked = payload.answer or generated_answer
    validation = output_validator.validate(payload.child_profile, payload.message, answer_checked, decision)
    repaired_answer = None
    if not validation["safe_to_show"]:
        repaired_answer = safe_rewriter.repair_or_fallback(
            answer_checked,
            validation,
            decision,
            payload.child_profile,
        )
    stage_outputs["output_validator"] = validation
    stage_outputs["safe_rewriter"] = {"rewritten": repaired_answer is not None}
    return ValidatorTestResponse(
        decision=decision,
        answer_checked=answer_checked,
        validation=validation,
        repaired_answer=repaired_answer,
        stage_outputs=stage_outputs,
    )
