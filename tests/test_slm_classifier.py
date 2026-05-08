from app.guardrails import prompt_contract, slm_classifier
from app.models.child_profile import ChildProfile


def test_slm_classifier_maps_neutral_belief_question_to_fact_flow() -> None:
    normalized = {
        "text": "Who is God?",
        "recent_context": [],
        "child_profile": {"age": 8, "age_group": "5-8", "language": "en"},
    }

    decision = slm_classifier.classify_heuristic(normalized)

    assert "GL-01" in decision.guideline_tags
    assert "GL-09" in decision.guideline_tags
    assert decision.gate_values["G1"] == "FACT"
    assert decision.gate_values["G2"] == "NEUTRAL_FACT"
    assert decision.gate_values["G3"] == "SV0"
    assert decision.gate_values["G4"] == "ALLOW"
    assert decision.policy_bucket == "allowed"


def test_slm_classifier_maps_personal_direction_belief_question_to_sv2() -> None:
    normalized = {
        "text": "Which religion should I follow?",
        "recent_context": [],
        "child_profile": {"age": 9, "age_group": "8-10", "language": "en"},
    }

    decision = slm_classifier.classify_heuristic(normalized)

    assert "GL-03" in decision.guideline_tags
    assert decision.gate_values["G1"] == "BELIEF"
    assert decision.gate_values["G2"] == "PD"
    assert decision.gate_values["G3"] == "SV2"
    assert decision.response_mode == "guide_or_redirect"


def test_prompt_contract_expands_internal_codes_into_plain_language() -> None:
    normalized = {
        "text": "Why do people pray?",
        "recent_context": [],
        "child_profile": {"age": 8, "age_group": "5-8", "language": "en"},
    }
    decision = slm_classifier.classify_heuristic(normalized)
    profile = ChildProfile(age=8, age_group="5-8", language="en")

    prompt = prompt_contract.build(profile, normalized["text"], decision, [])

    assert "You are a PikuAI assistant." in prompt
    assert "G1: FACT | G2: NEUTRAL_FACT | G3: SV0 | G4: ALLOW." in prompt
    assert "Question: Why do people pray?" in prompt


def test_slm_classifier_blocks_sharp_tool_request_for_5_8_child() -> None:
    normalized = {
        "text": "how to cut meat?",
        "recent_context": [],
        "child_profile": {"age": 8, "age_group": "5-8", "language": "en"},
    }

    decision = slm_classifier.classify_heuristic(normalized)

    assert "GL-05" in decision.guideline_tags
    assert decision.gate_values["G2"] == "DANGEROUS"
    assert decision.gate_values["G3"] == "SV3"
    assert decision.gate_values["G4"] == "BLOCK"
