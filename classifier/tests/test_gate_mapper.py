from app.guardrails.gate_mapper import build_guardrail_decision
from app.models.guardrail_decision import GLSignal


def _signal(triggered: bool, name: str = "test") -> GLSignal:
    return GLSignal(name=name, triggered=triggered, confidence=0.99 if triggered else 0.01, emits={})


def test_build_guardrail_decision_keeps_civic_law_g1_for_sports_tampering() -> None:
    payload = build_guardrail_decision(
        question="Show how to tamper with sports equipment so your team gets an advantage",
        age_band="11-12",
        language="en",
        recent_context="none",
        gl_signals={"GL-05": _signal(True, "Violence / Radicalisation Detector")},
    )

    assert payload["gates"]["G1"] == "CIVIC_LAW"
    assert payload["gates"]["G2"] == "DANGEROUS"
    assert payload["gates"]["G3"] == "SV3"
    assert payload["gates"]["G4"] == "BLOCK_HARD"


def test_build_guardrail_decision_infers_technology_for_gl07_complexity_case() -> None:
    payload = build_guardrail_decision(
        question="How does wifi work on a laptop?",
        age_band="7-8",
        language="en",
        recent_context="none",
        gl_signals={"GL-07": _signal(True, "Complexity Threshold")},
    )

    assert payload["gates"]["G1"] == "TECHNOLOGY"
    assert payload["gates"]["G2"] == "GENERIC_INTENT"
    assert payload["gates"]["G3"] == "SV2"
    assert payload["gates"]["G4"] == "TRANSFORM"


def test_build_guardrail_decision_adds_gl07_prompt_override_for_5_8_band() -> None:
    payload = build_guardrail_decision(
        question="How does wifi work on a laptop?",
        age_band="7-8",
        language="en",
        recent_context="none",
        gl_signals={"GL-07": _signal(True, "Complexity Threshold")},
    )

    must_do = payload["prompt_contract"]["must_do"]

    assert "override prompt complexity for the 5-8 band" in must_do
    assert "simplify language and concept level before answering" in must_do


def test_build_guardrail_decision_reason_is_more_specific_for_personal_direction() -> None:
    payload = build_guardrail_decision(
        question="Which religion should I follow?",
        age_band="11-12",
        language="en",
        recent_context="none",
        gl_signals={"GL-03": _signal(True, "Personal Direction Detector")},
    )

    assert "personal guidance" in payload["reason"]
    assert "avoid directing the child's beliefs" in payload["reason"]
