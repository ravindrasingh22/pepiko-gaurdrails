from fastapi import APIRouter

from app.guardrails import normalizer, prompt_contract, slm_classifier
from app.guardrails.runtime_contracts import (
    classifier_output_from_decision,
    gate_output_from_classifier,
    safety_envelope_from_runtime,
)
from app.models.schemas import (
    ClassificationPromptResponse,
    ClassificationTestRequest,
    ClassificationTestResponse,
)
from training.slm_classifier.codebook import parse_codebook


CODEBOOK = parse_codebook()

router = APIRouter()


def _head_confidences(decision_metadata: dict[str, object]) -> dict[str, object]:
    values = decision_metadata.get("head_confidences", {})
    return values if isinstance(values, dict) else {}


def _score_map(heads: dict[str, object], *keys: str) -> dict[str, float]:
    for key in keys:
        raw = heads.get(key, {})
        if isinstance(raw, dict):
            return {str(label): float(score) for label, score in raw.items()}
    return {}


def _active_flags(
    metadata: dict[str, object],
    threshold: float,
) -> list[dict[str, object]]:
    heads = _head_confidences(metadata)
    flag_scores = _score_map(heads, "flags")
    active: dict[str, dict[str, object]] = {}
    for flag, score in sorted(flag_scores.items(), key=lambda item: item[0]):
        if score >= threshold:
            active[flag] = {"id": flag, "score": score, "source": "trained_flag_head"}
    return list(active.values())


def _tag_payload(category: str, tag: str) -> dict[str, str]:
    spec = CODEBOOK.modifier_tags.get(category, {}).get(tag)
    return {
        "tag": tag,
        "description": spec.description if spec else "",
    }


def _modifier_tags(active_flags: list[dict[str, object]]) -> dict[str, object]:
    mapped_flag_ids = {str(item["id"]) for item in active_flags if str(item.get("id", "")) in CODEBOOK.flag_mappings}
    mappings: list[dict[str, object]] = []
    tone_tags: set[str] = set()
    action_tags: set[str] = set()
    escalation_tags: set[str] = set()
    for flag in sorted(mapped_flag_ids):
        mapping = CODEBOOK.flag_mappings[flag]
        tone_tags.add(mapping.tone)
        action_tags.add(mapping.action)
        escalation_tags.add(mapping.escalation)
        mappings.append(
            {
                "flag": flag,
                "tone": _tag_payload("tone", mapping.tone),
                "action": _tag_payload("action", mapping.action),
                "escalation": _tag_payload("escalation", mapping.escalation),
            }
        )
    return {
        "mappings": mappings,
        "tone": [_tag_payload("tone", tag) for tag in sorted(tone_tags)],
        "action": [_tag_payload("action", tag) for tag in sorted(action_tags)],
        "escalation": [_tag_payload("escalation", tag) for tag in sorted(escalation_tags)],
    }


def _primary_g2_score(metadata: dict[str, object], g2_id: str) -> tuple[float | None, dict[str, float]]:
    heads = _head_confidences(metadata)
    scores = _score_map(heads, "G2_primary", "G2")
    return scores.get(g2_id), scores


def _selected_g2_score(
    metadata: dict[str, object],
    classifier_output: dict[str, object],
    g2_id: str,
    threshold: float,
    active_flags: list[dict[str, object]],
) -> dict[str, object]:
    raw_score, _ = _primary_g2_score(metadata, g2_id)
    if raw_score is None:
        return {"score": None, "model_score": None, "score_source": "none"}
    return {"score": float(raw_score), "model_score": float(raw_score), "score_source": "g2_head"}


def _g4_response(raw_g4: dict[str, object]) -> dict[str, object]:
    raw_action = str(raw_g4.get("action", "TRANSFORM"))
    action_map = {
        "BLOCK_HARD": ("BLOCK", "hard"),
        "BLOCK_ESCALATE": ("BLOCK", "escalate"),
        "TRANSFORM_HOLD": ("TRANSFORM", "hold"),
        "TRANSFORM_ESCALATE": ("TRANSFORM", "escalate"),
    }
    action, variant = action_map.get(raw_action, (raw_action, "base"))
    return {
        "action": action,
        "variant": variant,
        "ending": raw_g4.get("ending", ""),
        "style": raw_g4.get("style", ""),
    }


def _g2_reason_text(g2_id: str, raw_reason: str) -> str:
    spec = CODEBOOK.g2_specs.get(g2_id)
    if not spec:
        return raw_reason
    parts = [f"{g2_id}: {spec.name}."]
    if spec.definition:
        parts.append(spec.definition.rstrip(".") + ".")
    parts.append(f"Severity floor is {spec.severity_floor}.")
    if spec.modifiers:
        parts.append("Modifier packet emits: " + ", ".join(spec.modifiers) + ".")
    if raw_reason:
        parts.append("Classifier evidence: " + raw_reason.rstrip(".") + ".")
    return " ".join(parts)


def _g1_score(metadata: dict[str, object], g1_id: str) -> tuple[float | None, dict[str, float]]:
    heads = _head_confidences(metadata)
    scores = _score_map(heads, "G1")
    return scores.get(g1_id), scores


def _usage_payload(metadata: dict[str, object], payload: ClassificationTestRequest) -> dict[str, int]:
    raw_usage = metadata.get("usage", {})
    if isinstance(raw_usage, dict):
        prompt_tokens = int(raw_usage.get("prompt_tokens", 0))
        completion_tokens = int(raw_usage.get("completion_tokens", 0))
        total_tokens = int(raw_usage.get("total_tokens", prompt_tokens + completion_tokens))
        if prompt_tokens or completion_tokens or total_tokens:
            return {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
    fallback_text = " ".join([payload.message, *[str(item) for item in payload.recent_context]]).strip()
    prompt_tokens = len(fallback_text.split())
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": 0,
        "total_tokens": prompt_tokens,
    }


def _classify_response(
    payload: ClassificationTestRequest,
    decision_metadata: dict[str, object],
    classifier_output: dict[str, object],
    gate_output: dict[str, object],
) -> ClassificationTestResponse:
    threshold = float(decision_metadata.get("g2_threshold", 0.5))
    active_flags = _active_flags(decision_metadata, threshold)
    intent_lexicon = classifier_output.setdefault("intent_lexicon", {})
    if isinstance(intent_lexicon, dict):
        learned = intent_lexicon.setdefault("learned", {})
        if isinstance(learned, dict):
            learned["predicted_flags"] = [str(item["id"]) for item in active_flags]
    envelope = safety_envelope_from_runtime(classifier_output, gate_output)
    g2_ids = [str(item["id"]) for item in classifier_output.get("g2", []) if isinstance(item, dict)]
    primary_g2 = g2_ids[0] if g2_ids else "GENERIC_INTENT"
    g1_id = str(classifier_output.get("g1", {}).get("id", "GENERIC")) if isinstance(classifier_output.get("g1"), dict) else "GENERIC"
    g1_score, _ = _g1_score(decision_metadata, g1_id)
    g2_score = _selected_g2_score(decision_metadata, classifier_output, primary_g2, threshold, active_flags)
    age_settings = envelope["user_context"]["age_settings"]
    reason = ""
    for item in classifier_output.get("g2", []):
        if isinstance(item, dict) and item.get("id") == primary_g2:
            reason = str(item.get("reason", ""))
            break
    reason = _g2_reason_text(primary_g2, reason)

    return ClassificationTestResponse(
        input={
            "user_input": payload.message,
            "context": list(payload.recent_context),
        },
        classifier={
            "trained": bool(decision_metadata.get("trained", False)),
            "backend": decision_metadata.get("backend", "unknown"),
            "core_model": decision_metadata.get("core_model"),
            "threshold": threshold,
        },
        g1={
            "id": g1_id,
            "score": g1_score,
            "reason": str(classifier_output.get("g1", {}).get("reason", "")) if isinstance(classifier_output.get("g1"), dict) else "",
        },
        g2={
            "id": primary_g2,
            **g2_score,
            "reason_code": primary_g2,
            "reason": reason,
        },
        g3={
            "G3_SV": envelope["codebook_flow"]["block_c"]["G3_SV"],
            "G3_MOD": envelope["codebook_flow"]["block_c"]["G3_MOD"],
            "G3_FORWARD": envelope["codebook_flow"]["block_c"]["G3_FORWARD"],
        },
        g4=_g4_response(envelope["g4"]),
        active_flags=active_flags,
        age_policy={
            "age_band": envelope["user_context"]["age_band"],
            "Max_Answer_Style": age_settings["style"],
            "Max_Words": age_settings["max_words"],
            "Depth": age_settings["depth"],
        },
        usage=_usage_payload(decision_metadata, payload),
        modifier_tags=_modifier_tags(active_flags),
    )


def _normalize_for_classifier(payload: ClassificationTestRequest) -> dict[str, object]:
    return normalizer.normalize(
        {
            "child_profile": payload.child_profile.model_dump(),
            "message": payload.message,
            "session_id": payload.session_id,
            "recent_context": list(payload.recent_context),
        }
    )


async def _classification_payload(
    payload: ClassificationTestRequest,
) -> tuple[ClassificationTestResponse, object]:
    normalized = _normalize_for_classifier(payload)
    decision = slm_classifier.classify_slm(normalized)
    decision_metadata = dict(decision.classifier_metadata or {})
    classifier_output = classifier_output_from_decision(payload.message, payload.child_profile, decision)
    active_flags = _active_flags(decision_metadata, float(decision_metadata.get("g2_threshold", 0.5)))
    intent_lexicon = classifier_output.setdefault("intent_lexicon", {})
    if isinstance(intent_lexicon, dict):
        learned = intent_lexicon.setdefault("learned", {})
        if isinstance(learned, dict):
            learned["predicted_flags"] = [str(item["id"]) for item in active_flags]
    gate_output = gate_output_from_classifier(classifier_output)
    if decision.classifier_metadata is None:
        decision.classifier_metadata = {}
    decision.classifier_metadata["runtime_classifier_output"] = classifier_output
    return _classify_response(payload, decision_metadata, classifier_output, gate_output), decision


@router.post("/guardrail/classify", response_model=ClassificationTestResponse)
async def classify_guardrail(payload: ClassificationTestRequest) -> ClassificationTestResponse:
    response, _ = await _classification_payload(payload)
    return response


@router.post("/guardrail/classified/prompt", response_model=ClassificationPromptResponse)
async def classify_guardrail_prompt(payload: ClassificationTestRequest) -> ClassificationPromptResponse:
    classification, decision = await _classification_payload(payload)
    final_prompt = prompt_contract.build(payload.child_profile, payload.message, decision, [])
    return ClassificationPromptResponse(
        prompts=[
            {"role": "system", "content": final_prompt},
            {"role": "user", "content": payload.message},
        ],
        prompt_checklist=dict(decision.prompt_contract.get("checklist", {})),
        classifier_output=classification.model_dump(),
    )
