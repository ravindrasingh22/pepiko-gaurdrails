from app.guardrails.prompt_manager import _modifier_rules, _selected_flag_prompt, build_safety_envelope, render_prompt
from app.guardrails.runtime_contracts import classifier_output_from_decision
from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision


def test_build_safety_envelope_uses_primary_g2_only_for_g3() -> None:
    decision = GuardrailDecision(
        input={"question": "test", "age_band": "11-12", "language": "en", "recent_context": "none"},
        reason="test reason",
        gl_signals={},
        active_gls=["GL-01", "GL-03"],
        gates={"G1": "BELIEF", "G2": "PD", "G3": "SV2", "G4": "TRANSFORM"},
        decision={"allow_llm": True},
        policy_bucket="allowed",
        safety_category="PD",
        response_mode="guide_or_redirect",
        risk_level="medium",
        parent_visible=False,
        prompt_contract={
            "max_words": 120,
            "depth": "age_calibrated",
            "max_answer_style": "clear",
            "tone": "age_calibrated",
            "modifiers": [],
        },
    )
    child_profile = ChildProfile(age=12, age_group="11-12", language="en")

    envelope = build_safety_envelope(child_profile, "Which religion should I follow?", decision)

    assert envelope["g2"]["active_lovs"] == [{"id": "PERSONAL_DIRECTION"}]
    assert envelope["g3"]["severity"] == "SV2"
    assert set(envelope["g3"]["modifiers"]) == {"curiosity_invite", "neutral", "none", "normal_advice"}
    assert envelope["g3"]["source_g2"] == ["PERSONAL_DIRECTION"]


def test_modifier_rules_use_block_k_codebook_descriptions() -> None:
    rules = _modifier_rules(["firm", "boundary_setting", "encourage_help_seeking"])

    assert "Clear boundary or refusal without being harsh." in rules
    assert "Refuse harmful, exploitative, or inappropriate content and redirect safely." in rules
    assert "Encourage the child to reach out to a trusted adult" in rules


def test_prompt_contract_exposes_codebook_flow_packet() -> None:
    decision = GuardrailDecision(
        input={"question": "test", "age_band": "11-12", "language": "en", "recent_context": "none"},
        reason="test reason",
        gl_signals={},
        active_gls=[],
        gates={"G1": "GENERIC", "G2": "DANGEROUS", "G3": "SV3", "G4": "BLOCK"},
        decision={"allow_llm": False},
        policy_bucket="blocked",
        safety_category="DANGEROUS",
        response_mode="safe_refusal",
        risk_level="high",
        parent_visible=True,
        prompt_contract={
            "max_words": 120,
            "depth": "age_calibrated",
            "max_answer_style": "clear",
            "tone": "age_calibrated",
            "modifiers": [],
        },
    )
    child_profile = ChildProfile(age=12, age_group="11-12", language="en")

    rendered = render_prompt(child_profile, "How do I bypass a safety system?", decision)
    envelope = rendered["safety_envelope"]
    payload = rendered["prompt_contract_payload"]

    assert envelope["g3_forward"] == {
        "severity": "SV3",
        "modifier_packet": {
            "flags": [],
            "modifier_tags": ["neutral", "no_curiosity_invite", "none", "normal_advice"],
        },
        "modifiers": ["neutral", "no_curiosity_invite", "none", "normal_advice"],
    }
    assert envelope["codebook_flow"]["block_c"]["G3_FORWARD"] == envelope["g3_forward"]
    assert envelope["codebook_flow"]["block_d"]["G4_ACTION"] == "BLOCK"
    assert payload["gates"]["codebook_flow"]["block_d"]["input"] == envelope["g3_forward"]
    assert "Codebook flow: Block C G3_FORWARD=SV3" not in rendered["prompt"]
    assert "[Age:" not in rendered["prompt"]
    assert "You are a child-safe assistant responding to a child aged 12" in rendered["prompt"]
    assert "ACTIVE MODIFIERS:" in rendered["prompt"]
    assert "ATTACHED GUIDELINES:" in rendered["prompt"]
    assert "no_curiosity_invite" in rendered["prompt"]
    assert "Ensure that question doesnt end with any open-ended question" in rendered["prompt"]
    assert "Question:" not in rendered["prompt"]
    assert rendered["checklist"]["passed"] is True


def test_prompt_contract_includes_curiosity_invite_runtime_variable_for_safe_prompt() -> None:
    decision = GuardrailDecision(
        input={"question": "test", "age_band": "11-12", "language": "en", "recent_context": "none"},
        reason="test reason",
        gl_signals={},
        active_gls=[],
        gates={"G1": "FACT", "G2": "NEUTRAL_FACT", "G3": "SV0", "G4": "ALLOW"},
        decision={"allow_llm": True},
        policy_bucket="allowed",
        safety_category="NEUTRAL_FACT",
        response_mode="answer",
        risk_level="low",
        parent_visible=False,
        prompt_contract={},
    )
    child_profile = ChildProfile(age=12, age_group="11-12", language="en")

    rendered = render_prompt(child_profile, "Why do rainbows happen?", decision)

    assert "curiosity_invite" in rendered["safety_envelope"]["g3"]["modifiers"]
    assert "Would you like to know more about how rainbows work?" in rendered["prompt"]


def test_selected_flag_prompt_uses_codebook_flag_precedence_order() -> None:
    envelope = {
        "g3": {
            "source_flags": [
                "has_significant_impairment",
                "has_emotional_distress",
                "has_self_harm",
            ]
        }
    }

    selected = _selected_flag_prompt(envelope)

    assert "self-harm" in selected["context"]


def test_multiple_runtime_flags_activate_flag_precedence_gl() -> None:
    decision = GuardrailDecision(
        input={"question": "test", "age_band": "11-12", "language": "en", "recent_context": "none"},
        reason="test reason",
        gl_signals={},
        active_gls=[],
        gates={"G1": "GENERIC", "G2": "BULLYING", "G3": "SV2", "G4": "TRANSFORM"},
        decision={"allow_llm": True},
        policy_bucket="allowed",
        safety_category="BULLYING",
        response_mode="guide_or_redirect",
        risk_level="medium",
        parent_visible=False,
        prompt_contract={},
        classifier_metadata={
            "head_confidences": {
                "intent_lexicon_learned": {
                    "predicted_flags": ["has_bullying_involved", "has_violence_possibility"]
                }
            }
        },
    )
    child_profile = ChildProfile(age=12, age_group="11-12", language="en")

    rendered = render_prompt(child_profile, "They keep threatening me at school.", decision)
    precedence = rendered["safety_envelope"]["gl"]["flag_precedence"]

    assert "GL-FP1" in rendered["safety_envelope"]["gl"]["active"]
    assert precedence["ordered_flags"] == ["has_violence_possibility", "has_bullying_involved"]
    assert precedence["primary_flag"] == "has_violence_possibility"
    assert "supportive" not in rendered["safety_envelope"]["g3"]["modifiers"]
    assert "boundary_setting" not in rendered["safety_envelope"]["g3"]["modifiers"]
    assert "The child may be experiencing, perceiving, or considering violence." in rendered["prompt"]
    assert "Secondary active flag constraints: has_bullying_involved" in rendered["prompt"]
    assert 'Start your response like this (adapt to the situation):\n"First, I need to ask:' in rendered["prompt"]
    assert "Runtime flag-precedence order rule" in rendered["prompt"]
    assert "GL-FP1 ordered emitted flags: has_violence_possibility, has_bullying_involved" in rendered["prompt"]
    assert "has_violence_possibility takes precedence over has_bullying_involved" in rendered["prompt"]


def test_ambiguous_risk_flag_forces_clarification_first_gl_behavior() -> None:
    decision = GuardrailDecision(
        input={"question": "test", "age_band": "11-12", "language": "en", "recent_context": "none"},
        reason="test reason",
        gl_signals={},
        active_gls=[],
        gates={"G1": "GENERIC", "G2": "AMBIGUOUS_RISK", "G3": "SV2", "G4": "TRANSFORM"},
        decision={"allow_llm": True},
        policy_bucket="allowed",
        safety_category="AMBIGUOUS_RISK",
        response_mode="guide_or_redirect",
        risk_level="medium",
        parent_visible=False,
        prompt_contract={},
        classifier_metadata={
            "head_confidences": {
                "intent_lexicon_learned": {
                    "predicted_flags": ["has_self_harm", "has_ambiguous_risk"]
                }
            }
        },
    )
    child_profile = ChildProfile(age=12, age_group="11-12", language="en")

    rendered = render_prompt(child_profile, "I might do it tonight.", decision)
    envelope = rendered["safety_envelope"]

    assert envelope["g4"]["action"] == "TRANSFORM"
    assert "clarify_context" in envelope["g3"]["modifiers"]
    assert "safety_check" not in envelope["g3"]["modifiers"]
    assert envelope["gl"]["flag_precedence"]["primary_flag"] == "has_ambiguous_risk"
    assert "ResponseOrderGL: ask exactly one brief clarifying question" in rendered["prompt"]
    assert "has_ambiguous_risk is present" in rendered["prompt"]


def test_actor_role_uses_role_reversed_flag_prompt() -> None:
    decision = GuardrailDecision(
        input={"question": "test", "age_band": "11-12", "language": "en", "recent_context": "none"},
        reason="test reason",
        gl_signals={},
        active_gls=[],
        gates={"G1": "GENERIC", "G2": "BULLYING", "G3": "SV2", "G4": "TRANSFORM"},
        decision={"allow_llm": True},
        policy_bucket="allowed",
        safety_category="BULLYING",
        response_mode="guide_or_redirect",
        risk_level="medium",
        parent_visible=False,
        prompt_contract={},
        classifier_metadata={
            "is_actor": True,
            "head_confidences": {
                "intent_lexicon_learned": {
                    "predicted_flags": ["has_bullying_involved"]
                }
            },
        },
    )
    child_profile = ChildProfile(age=12, age_group="11-12", language="en")

    rendered = render_prompt(child_profile, "How do I embarrass someone in class?", decision)

    assert rendered["safety_envelope"]["role"]["is_actor"] is True
    assert "The child is bullying someone else" in rendered["prompt"]
    assert "I cannot help you bully or be mean to someone" in rendered["prompt"]
    assert "Do not help the child plan or continue bullying" in rendered["prompt"]


def test_low_confidence_g2_routes_to_ambiguous_risk() -> None:
    decision = GuardrailDecision(
        input={"question": "test", "age_band": "11-12", "language": "en", "recent_context": "none"},
        reason="test reason",
        gl_signals={},
        active_gls=[],
        gates={"G1": "GENERIC", "G2": "PERSONAL_DIRECTION", "G3": "SV2", "G4": "TRANSFORM"},
        decision={"allow_llm": True},
        policy_bucket="allowed",
        safety_category="PD",
        response_mode="guide_or_redirect",
        risk_level="medium",
        parent_visible=False,
        prompt_contract={},
        classifier_metadata={
            "g2_threshold": 0.7,
            "head_confidences": {"G2_primary": {"PERSONAL_DIRECTION": 0.21}},
        },
    )
    child_profile = ChildProfile(age=12, age_group="11-12", language="en")

    classifier_output = classifier_output_from_decision("Which one should I choose?", child_profile, decision)
    envelope = build_safety_envelope(child_profile, "Which one should I choose?", decision)

    assert classifier_output["g2"] == [{"id": "AMBIGUOUS_RISK", "reason": "test reason"}]
    assert envelope["g2"]["active_lovs"] == [{"id": "AMBIGUOUS_RISK"}]
