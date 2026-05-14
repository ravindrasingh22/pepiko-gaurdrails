from app.guardrails.prompt_manager import build_safety_envelope
from app.models.child_profile import ChildProfile
from app.models.guardrail_decision import GuardrailDecision


def test_build_safety_envelope_uses_primary_g2_only_for_g3() -> None:
    decision = GuardrailDecision(
        input={"question": "test", "age_band": "11-12", "language": "en", "recent_context": "none"},
        reason="test reason",
        gl_signals={},
        active_gls=["GL-01", "GL-03"],
        gates={"G1": "BELIEF", "G2": "PD", "G2_all": ["PD", "GROOMING"], "G3": "SV2", "G4": "TRANSFORM"},
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

    assert envelope["g2"]["active_lovs"] == [
        {"id": "PD", "reason": "test reason"},
        {"id": "GROOMING", "reason": "test reason"},
    ]
    assert envelope["g3"]["severity"] == "SV2"
    assert envelope["g3"]["modifiers"] == []
    assert envelope["g3"]["source_g2"] == ["PD"]
