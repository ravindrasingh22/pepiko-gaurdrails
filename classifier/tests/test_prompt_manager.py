from app.guardrails.prompt_manager import _modifier_rules, build_safety_envelope, render_prompt
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
    assert envelope["g3"]["modifiers"] == []
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
        "modifiers": [],
    }
    assert envelope["codebook_flow"]["block_c"]["G3_FORWARD"] == envelope["g3_forward"]
    assert envelope["codebook_flow"]["block_d"]["G4_ACTION"] == "BLOCK"
    assert payload["gates"]["codebook_flow"]["block_d"]["input"] == envelope["g3_forward"]
    assert "Codebook flow: Block C G3_FORWARD=SV3" not in rendered["prompt"]
    assert "[Age:" not in rendered["prompt"]
    assert "The child is in age band 11-12" in rendered["prompt"]
    assert "Active safety rules:" in rendered["prompt"]
    assert "Question:" not in rendered["prompt"]
    assert rendered["checklist"]["passed"] is True
