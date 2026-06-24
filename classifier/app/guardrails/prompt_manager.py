from __future__ import annotations

from typing import Any

from app.guardrails.runtime_contracts import (
    classifier_output_from_decision,
    gate_output_from_classifier,
    prompt_contract_payload,
    safety_envelope_from_runtime,
)
from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision
from training.slm_classifier.codebook import parse_codebook


CODEBOOK = parse_codebook()


RUNTIME_MODIFIER_RULES = {
    "clarification_required": "Ask exactly one safe clarification question before answering.",
    "empathetic_tone": "Use a warm, empathetic tone.",
    "emotional_support_required": "Acknowledge feelings briefly without acting like a therapist.",
    "escalate": "Include a trusted-adult help-seeking direction.",
    "flag_for_review": "Avoid endorsing the premise and keep the response conservative.",
    "needs_debiasing": "Correct or neutralize biased assumptions before answering.",
    "no_content_engagement": "Do not explain, describe, or provide details about the unsafe content.",
    "no_curiosity_invite": "Do not end with a curiosity or follow-up question.",
    "safeguarding_concern": "Prioritize the child's safety and point them toward a trusted adult.",
    "zero_engagement": "Do not engage with the unsafe request beyond a brief safety boundary.",
}

TONE_PRIORITY = ("firm", "cautious", "supportive", "neutral")
ACTION_PRIORITY = ("safety_check", "boundary_setting", "clarify_context", "de_escalate", "normal_advice")
ESCALATION_PRIORITY = ("encourage_help_seeking", "none")


def _codebook_modifier_descriptions() -> dict[str, str]:
    descriptions: dict[str, str] = {}
    for tags in CODEBOOK.modifier_tags.values():
        for tag, spec in tags.items():
            descriptions[tag] = spec.description
    return descriptions


def _modifier_rules(modifiers: list[str]) -> str:
    codebook_rules = _codebook_modifier_descriptions()
    rules = [
        codebook_rules.get(modifier) or RUNTIME_MODIFIER_RULES.get(modifier) or modifier.replace("_", " ").capitalize() + "."
        for modifier in modifiers
    ]
    if not rules:
        return "Use standard safe-learning behavior: be accurate, calm, age-appropriate, and do not add unnecessary risk detail."
    return " ".join(rule.rstrip(".") + "." for rule in rules)


def _prompt_policy_instruction(envelope: dict[str, Any]) -> str:
    notes = [str(note).strip() for note in envelope.get("prompt_policy_notes", []) if str(note).strip()]
    if not notes:
        return "No additional prompt-policy notes are active."
    return "Follow these prompt-policy notes exactly: " + " ".join(note.rstrip(".") + "." for note in notes)


def build_safety_envelope(child_profile: ChildProfile, message: str, decision: GuardrailDecision) -> dict[str, Any]:
    classifier_output = classifier_output_from_decision(message, child_profile, decision)
    gate_output = gate_output_from_classifier(classifier_output)
    return safety_envelope_from_runtime(classifier_output, gate_output)


def _pick_template(envelope: dict[str, Any]) -> dict[str, str]:
    return {
        "id": CODEBOOK.prompt_master_template.template_id,
        "template": CODEBOOK.prompt_master_template.template,
    }


def _apply_prompt_rules(envelope: dict[str, Any], rendered: str) -> str:
    modifiers = set(envelope["g3"]["modifiers"])
    if "no_curiosity_invite" in modifiers and rendered.rstrip().endswith("?"):
        rendered = rendered.rstrip().rstrip("?")
    return rendered


def _format_g3_forward(envelope: dict[str, Any]) -> str:
    g3_forward = envelope["g3_forward"]
    modifiers = g3_forward.get("modifiers") or g3_forward.get("modifier_packet", {}).get("modifier_tags", [])
    modifier_text = ", ".join(modifiers) if modifiers else "none"
    return f"{g3_forward['severity']} + {{{modifier_text}}}"


def _resolve_modifier(modifiers: set[str], priority: tuple[str, ...], fallback: str) -> str:
    for item in priority:
        if item in modifiers:
            return item
    return fallback


def _runtime_variable_instruction(key: str) -> str:
    spec = CODEBOOK.prompt_dictionary.runtime_variables.get(key)
    if not spec:
        return "No special runtime instruction."
    rules = " ".join(rule.rstrip(".") + "." for rule in spec.behavioral_rules)
    return f"{spec.definition.rstrip('.')}." + (f" {rules}" if rules else "")


def _active_flag_ids(envelope: dict[str, Any]) -> list[str]:
    return [str(flag) for flag in envelope["g3"].get("source_flags", []) if str(flag) in CODEBOOK.prompt_dictionary.flag_prompts]


def _is_actor(envelope: dict[str, Any]) -> bool:
    role = envelope.get("role", {})
    return isinstance(role, dict) and bool(role.get("is_actor"))


def _flag_prompt_variant(flag: str, envelope: dict[str, Any]) -> Any:
    spec = CODEBOOK.prompt_dictionary.flag_prompts[flag]
    if _is_actor(envelope) and spec.role_reversed:
        return spec.role_reversed
    return spec


def _flag_priority(flag: str) -> tuple[int, int, int, str]:
    precedence = CODEBOOK.flag_precedence_order.rankings.get(flag)
    if precedence is not None:
        return (precedence, 0, 0, flag)
    mapping = CODEBOOK.flag_mappings.get(flag)
    if not mapping:
        return (len(ACTION_PRIORITY), len(TONE_PRIORITY), len(ESCALATION_PRIORITY), flag)
    action_rank = ACTION_PRIORITY.index(mapping.action) if mapping.action in ACTION_PRIORITY else len(ACTION_PRIORITY)
    tone_rank = TONE_PRIORITY.index(mapping.tone) if mapping.tone in TONE_PRIORITY else len(TONE_PRIORITY)
    escalation_rank = ESCALATION_PRIORITY.index(mapping.escalation) if mapping.escalation in ESCALATION_PRIORITY else len(ESCALATION_PRIORITY)
    return (action_rank, tone_rank, escalation_rank, flag)


def _selected_flag_prompt(envelope: dict[str, Any]) -> dict[str, str]:
    active_flags = sorted(_active_flag_ids(envelope), key=_flag_priority)
    if active_flags:
        spec = _flag_prompt_variant(active_flags[0], envelope)
        return {
            "flag": active_flags[0],
            "context": spec.context,
            "guidance": spec.guidance,
            "example_start": spec.example_start,
        }
    return {
        "flag": "",
        "context": "The child's message does not activate a specific risk flag.",
        "guidance": "Give ordinary, age-appropriate help. Stay clear, practical, and safe.",
        "example_start": "Here is a simple way to think about it...",
    }


def _secondary_flag_context(envelope: dict[str, Any], primary_flag: str) -> list[str]:
    secondary: list[str] = []
    for flag in _active_flag_ids(envelope):
        if flag == primary_flag:
            continue
        if flag in CODEBOOK.prompt_dictionary.flag_prompts:
            spec = _flag_prompt_variant(flag, envelope)
            secondary.append(f"{flag}: {spec.context}")
    return secondary


def _first_example_for(key: str) -> str:
    spec = CODEBOOK.prompt_dictionary.runtime_variables.get(key)
    if not spec or not spec.examples:
        return ""
    example = spec.examples[0]
    if isinstance(example, dict) and len(example) == 1:
        prefix, suffix = next(iter(example.items()))
        return f"{prefix}: {suffix}"
    return str(example)


def _prompt_fields(envelope: dict[str, Any]) -> dict[str, str]:
    modifiers = set(envelope["g3"].get("modifiers", []))
    selected = _selected_flag_prompt(envelope)
    primary_flag = selected["flag"]
    context_lines = [selected["context"]]
    secondary = _secondary_flag_context(envelope, primary_flag)
    if secondary:
        context_lines.append("Secondary active flag constraints: " + "; ".join(secondary))

    guidance_parts = [selected["guidance"]]
    example_start = selected["example_start"]

    if "safety_check" in modifiers:
        safety_example = _first_example_for("safety_check")
        guidance_parts.insert(0, "ResponseOrderGL: start with a safety check before any explanation, refusal, or advice.")
        if safety_example:
            example_start = safety_example
    elif "clarify_context" in modifiers:
        clarify_example = _first_example_for("clarify_context")
        guidance_parts.insert(0, "ResponseOrderGL: ask exactly one brief clarifying question before giving a full answer.")
        if clarify_example:
            example_start = clarify_example

    if "boundary_setting" in modifiers:
        guidance_parts.append("ActionPriorityGL: apply the boundary or refusal clearly after any required safety check.")
    if "de_escalate" in modifiers:
        guidance_parts.append("ActionPriorityGL: reduce conflict and steer away from escalation.")
    if "encourage_help_seeking" in modifiers:
        guidance_parts.append("EscalationPriorityGL: end with a clear direction to contact a trusted adult or appropriate professional.")

    if "no_curiosity_invite" in modifiers:
        guidance_parts.append(_runtime_variable_instruction("no_curiosity_invite"))
    elif "curiosity_invite" in modifiers:
        curiosity_example = _first_example_for("curiosity_invite")
        suffix = f" Example curiosity ending: {curiosity_example}" if curiosity_example else ""
        guidance_parts.append(_runtime_variable_instruction("curiosity_invite") + suffix)

    return {
        "flag_context": "\n".join(context_lines),
        "flag_guidance": " ".join(part.strip() for part in guidance_parts if part.strip()),
        "flag_example_start": example_start,
    }


def _attached_guidelines(envelope: dict[str, Any]) -> str:
    guideline_lines: list[str] = []
    for gl_id in envelope.get("gl", {}).get("active", []):
        spec = CODEBOOK.gl_specs.get(str(gl_id))
        if spec and spec.special_rules:
            guideline_lines.append(f"- {spec.gl_id}: {spec.special_rules}")
            if spec.gl_id == "GL-FP1":
                precedence = envelope.get("gl", {}).get("flag_precedence", {})
                ordered_flags = precedence.get("ordered_flags", [])
                instructions = precedence.get("instructions", [])
                if ordered_flags:
                    guideline_lines.append(f"- GL-FP1 ordered emitted flags: {', '.join(ordered_flags)}")
                for instruction in instructions:
                    guideline_lines.append(f"- GL-FP1 precedence instruction: {instruction}")
    modifiers = set(envelope["g3"].get("modifiers", []))
    if "curiosity_invite" in modifiers:
        curiosity = CODEBOOK.prompt_dictionary.runtime_variables.get("curiosity_invite")
        example = f" Example: {curiosity.examples[0]}" if curiosity and curiosity.examples else ""
        guideline_lines.append(f"- curiosity_invite: {_runtime_variable_instruction('curiosity_invite')}{example}")
    if "no_curiosity_invite" in modifiers:
        guideline_lines.append(f"- no_curiosity_invite: {_runtime_variable_instruction('no_curiosity_invite')}")
    if not guideline_lines:
        return "- No additional GL rules are active."
    return "\n".join(guideline_lines)


def _checklist(envelope: dict[str, Any], rendered: str) -> dict[str, Any]:
    modifiers = set(envelope["g3"]["modifiers"])
    checks = {
        "CHK-01": "You are a child-safe assistant responding to a child aged" in rendered,
        "CHK-02": all(token not in rendered for token in ["[Age:", "G1:", "G2:", "G3:", "G4:", "Codebook flow:"]),
        "CHK-03": "ACTIVE MODIFIERS:" in rendered,
        "CHK-04": ("Ask one brief clarifying question" in rendered) if "clarify_context" in modifiers else True,
        "CHK-05": ("Refuse harmful" in rendered or "Do not help" in rendered) if "boundary_setting" in modifiers else True,
        "CHK-06": (not rendered.rstrip().endswith("?")) if "no_curiosity_invite" in modifiers else True,
        "CHK-07": f"child aged {envelope['user_context'].get('age', envelope['user_context']['age_band'])}" in rendered,
        "CHK-08": "ATTACHED GUIDELINES:" in rendered,
        "CHK-09": "Question:" not in rendered,
    }
    return {"passed": all(checks.values()), "checks": checks}


def render_prompt(child_profile: ChildProfile, message: str, decision: GuardrailDecision) -> dict[str, Any]:
    envelope = build_safety_envelope(child_profile, message, decision)
    template = _pick_template(envelope)
    modifiers = set(envelope["g3"]["modifiers"])
    tone = _resolve_modifier(modifiers, TONE_PRIORITY, "neutral")
    action = _resolve_modifier(modifiers, ACTION_PRIORITY, "normal_advice")
    escalation = _resolve_modifier(modifiers, ESCALATION_PRIORITY, "none")
    prompt_fields = _prompt_fields(envelope)
    rendered = template["template"].format(
        age=child_profile.age,
        flag_context=prompt_fields["flag_context"],
        tone_instructions=_runtime_variable_instruction(tone),
        action_instructions=_runtime_variable_instruction(action),
        escalation_instructions=_runtime_variable_instruction(escalation),
        flag_guidance=prompt_fields["flag_guidance"],
        flag_example_start=prompt_fields["flag_example_start"],
        attached_guidelines=_attached_guidelines(envelope),
    )
    rendered = _apply_prompt_rules(envelope, rendered)
    checklist = _checklist(envelope, rendered)
    payload = prompt_contract_payload(message, child_profile, decision, rendered, template["id"])
    payload["prompt_template"] = {
        "id": template["id"],
        "template": template["template"],
    }
    return {
        "safety_envelope": envelope,
        "template_id": template["id"],
        "checklist": checklist,
        "prompt": rendered,
        "prompt_contract_payload": payload,
    }
