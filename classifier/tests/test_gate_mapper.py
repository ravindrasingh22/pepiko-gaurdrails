from app.guardrails.gate_mapper import build_guardrail_decision, g3_modifiers, map_g3, map_g4
from app.guardrails.runtime_contracts import compute_g3, gate_output_from_classifier
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
    assert payload["gates"]["G4"] == "BLOCK"


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


def test_build_guardrail_decision_prompt_contract_includes_codebook_flow() -> None:
    payload = build_guardrail_decision(
        question="Show how to tamper with sports equipment so your team gets an advantage",
        age_band="11-12",
        language="en",
        recent_context="none",
        gl_signals={"GL-05": _signal(True, "Violence / Radicalisation Detector")},
    )

    flow = payload["prompt_contract"]["codebook_flow"]

    assert flow["block_b"]["g2"]["DANGEROUS"]["severity_floor"] == "SV3"
    assert flow["block_c"]["G3_SV"] == "SV3"
    assert flow["block_c"]["G3_MOD"] == []
    assert flow["block_c"]["G3_FORWARD"] == {
        "severity": "SV3",
        "modifiers": [],
    }
    assert flow["block_d"]["G4_ACTION"] == "BLOCK"


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


def test_g3_severity_is_loaded_from_g2_codebook_without_legacy_modifiers() -> None:
    assert map_g3(["DANGEROUS"]) == "SV3"
    assert g3_modifiers(["DANGEROUS"]) == []
    assert map_g4("SV3", ["DANGEROUS"], g3_modifiers(["DANGEROUS"])) == "BLOCK"

    assert map_g3(["AMBIGUOUS_RISK"]) == "SV2"
    assert g3_modifiers(["AMBIGUOUS_RISK"]) == []
    assert map_g4("SV2", ["AMBIGUOUS_RISK"], g3_modifiers(["AMBIGUOUS_RISK"])) == "TRANSFORM"


def test_runtime_g3_modifiers_are_derived_from_predicted_flags() -> None:
    g3 = compute_g3(["GROOMING"], active_flags=["has_grooming_involved"])

    assert g3["severity"] == "SV3"
    assert g3["source_flags"] == ["has_grooming_involved"]
    assert g3["modifiers"] == ["boundary_setting", "encourage_help_seeking", "firm"]


def test_runtime_gate_output_uses_codebook_g2_severity_and_modifiers() -> None:
    classifier_output = {
        "question": "An adult says our talks should stay secret.",
        "question_id": "test",
        "language": "en",
        "age_band": "11-12",
        "applies_when_flags": {
            "has_harmful_comparison": False,
            "has_loaded_premise": False,
            "has_negative_language": False,
            "is_protected_group_target": False,
            "includes_slurs": False,
            "has_vuln_exploitation": False,
            "has_blackmail_pattern": False,
            "has_dependency_pattern": False,
        },
        "intent_lexicon": {"matched_lovs": ["GROOMING"], "evidence": []},
        "topic": "General Learning",
        "g1": {"id": "GENERIC", "reason": ""},
        "g2": [{"id": "GROOMING", "reason": ""}],
    }

    g3 = compute_g3(["GROOMING"])
    gate_output = gate_output_from_classifier(classifier_output)

    assert g3["severity"] == "SV3"
    assert g3["modifiers"] == []
    assert gate_output["g4"]["action"] == "BLOCK"
