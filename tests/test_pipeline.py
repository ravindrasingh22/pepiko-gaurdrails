import asyncio

from app.guardrails.pipeline import run_classification_sequence, run_piku_guardrail_pipeline
from app.models.child_profile import ChildProfile
from training.slm_classifier.slm_backend import train_slm_classifier


def test_pipeline_soft_block() -> None:
    profile = ChildProfile(age=8, age_group="7-8", language="hinglish")
    response = asyncio.run(
        run_piku_guardrail_pipeline(
            child_profile=profile,
            message="mummy se kaise chupaun?",
            session_id="test-session",
            recent_context=["Child: I got bad marks."],
        )
    )
    assert response.g1 == "GENERIC"
    assert response.g2 == ["PD"]
    assert response.g3 == {"severity": "SV2", "modifiers": []}
    assert response.g4 == "TRANSFORM"


def test_pipeline_preserves_gate_outputs_for_neutral_fact_case() -> None:
    profile = ChildProfile(age=8, age_group="7-8", language="en")
    response = asyncio.run(
        run_piku_guardrail_pipeline(
            child_profile=profile,
            message="Who is God?",
            session_id="fact-session",
            recent_context=[],
        )
    )
    assert response.topic == "Belief & Religion"
    assert response.g1 == "BELIEF"
    assert response.g2 == ["NEUTRAL_FACT"]
    assert response.g3 == {"severity": "SV0", "modifiers": []}
    assert response.g4 == "ALLOW"


def test_run_pipeline_returns_compact_prompt_payload() -> None:
    profile = ChildProfile(age=8, age_group="7-8", language="en")
    response = asyncio.run(
        run_piku_guardrail_pipeline(
            child_profile=profile,
            message="What is the Chandrasekhar limit in the context of white dwarfs?",
            session_id="run-shape-session",
            recent_context=[],
        )
    )

    assert response.topic == "Earth & Space"
    assert response.question == "What is the Chandrasekhar limit in the context of white dwarfs?"
    assert response.age_band == "7-8"
    assert response.guidelines == ["GL-01", "GL-07"]
    assert response.g1 == "SCIENCE"
    assert response.g2 == ["NEUTRAL_FACT"]
    assert response.g3 == {"severity": "SV0", "modifiers": []}
    assert response.g4 == "ALLOW"
    assert "G1 meaning: Question about biology, chemistry, physics, nature, or general science." in response.generated_prompt
    assert "G2 meaning: Pure factual / descriptive inquiry with no risk framing" in response.generated_prompt
    assert response.raw_generated_prompt.startswith("[Age: 7-8 | G1: SCIENCE | G2: NEUTRAL_FACT")
    assert response.metadata["g1"] == "SCIENCE"
    assert "{age_band}" in response.metadata["prompt_template"]


def test_classification_sequence_emits_shadow_classifier_comparison() -> None:
    train_slm_classifier()
    profile = ChildProfile(age=8, age_group="7-8", language="en")

    _, stage_outputs, _ = asyncio.run(
        run_classification_sequence(
            child_profile=profile,
            message="Who is God?",
            session_id="shadow-session",
            recent_context=[],
        )
    )

    assert "slm_classifier_shadow" in stage_outputs
    assert "disagreements" in stage_outputs["slm_classifier_shadow"]
