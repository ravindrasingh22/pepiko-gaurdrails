from training.slm_classifier.codebook import CODEBOOK_CONFIG_DIR, codebook_config_paths, codebook_fingerprint, parse_codebook
from training.slm_classifier.data_pipeline import FLAG_VOCAB, G2_VOCAB


def test_codebook_parses_age_policy_runtime_block() -> None:
    codebook = parse_codebook()

    assert codebook.age_bands["5-6"].max_words == 90
    assert codebook.age_bands["5-6"].max_answer_style == "Warm, concrete, one idea"
    assert codebook.age_bands["5-6"].depth == "CONCRETE_ONE_STEP"
    assert codebook.age_bands["9-10"].max_answer_style == "Clear, cause-effect, brief steps"
    assert codebook.age_bands["17"].tone == "age_calibrated"
    assert codebook.parent_visibility.force_visible_if_age_lte == 10
    assert codebook.parent_visibility.risk_levels == ["medium", "high", "critical"]


def test_codebook_drives_training_flag_vocab() -> None:
    codebook = parse_codebook()

    assert FLAG_VOCAB == list(codebook.flag_mappings)
    assert codebook.flag_mappings["has_self_harm"].action == "safety_check"
    assert codebook.flag_mappings["has_self_harm"].escalation == "encourage_help_seeking"
    assert codebook.flag_mappings["has_clinical_concern"].action == "boundary_setting"
    assert codebook.flag_mappings["has_significant_impairment"].action == "safety_check"
    assert codebook.flag_mappings["has_medical_concern"].escalation == "encourage_help_seeking"
    assert codebook.flag_mappings["has_substance_use_concern"].tone == "cautious"
    assert codebook.flag_mappings["has_privacy_risk"].tone == "firm"
    assert "has_personal_direction" not in FLAG_VOCAB


def test_unknown_g2_is_codebook_only_not_training_vocab() -> None:
    codebook = parse_codebook()

    assert "UNKNOWN" in codebook.g2_specs
    assert "UNKNOWN" not in G2_VOCAB


def test_codebook_parses_block_k_modifier_tags() -> None:
    codebook = parse_codebook()

    assert codebook.modifier_tags["tone"]["supportive"].description.startswith("Warm, kind")
    assert codebook.modifier_tags["action"]["boundary_setting"].description.startswith("Refuse harmful")
    assert codebook.modifier_tags["escalation"]["encourage_help_seeking"].description.startswith("Encourage the child")
    assert codebook.modifier_tags["escalation"]["none"].description == "No special escalation."


def test_flag_modifier_mapping_references_known_block_k_tags() -> None:
    codebook = parse_codebook()

    for mapping in codebook.flag_mappings.values():
        assert mapping.tone in codebook.modifier_tags["tone"]
        assert mapping.action in codebook.modifier_tags["action"]
        assert mapping.escalation in codebook.modifier_tags["escalation"]


def test_g2_specs_do_not_emit_legacy_modifiers() -> None:
    codebook = parse_codebook()

    assert all(not spec.modifiers for spec in codebook.g2_specs.values())


def test_codebook_is_loaded_from_yaml_config_directory() -> None:
    codebook = parse_codebook()

    assert CODEBOOK_CONFIG_DIR.name == "codebook-config"
    config_names = {path.name for path in codebook_config_paths()}
    assert "g3.yml" in config_names
    assert "g4.yml" in config_names
    assert "gl-rules.yml" in config_names
    assert "gl-rules.yaml" not in config_names
    assert "prompt-dictionary.yaml" in config_names
    assert "prompt-master-template.yml" in config_names
    assert "prompt-rules.yaml" in config_names
    assert codebook_fingerprint()
    assert codebook.gl_specs["GL-T1"].name == "TonePriorityGL"


def test_codebook_carries_g2_classifier_boundary_guidance() -> None:
    codebook = parse_codebook()

    assert "individual or non-protected group" in codebook.g2_specs["HATE_GROUP"].notes_for_classifier
    assert "ordinary experiments or curiosity" in codebook.g2_specs["DANGEROUS"].notes_for_classifier
    assert "clear self-harm language" in codebook.g2_specs["EMOTIONAL"].notes_for_classifier
    assert "only sad or stressed" in codebook.g2_specs["SELF_HARM"].notes_for_classifier
    assert "major harm or serious illegal damage" in codebook.g2_specs["SAFETY_HAZARD"].notes_for_classifier


def test_codebook_parses_g3_gate_engine_config() -> None:
    codebook = parse_codebook()

    assert codebook.g3.gate == "G3"
    assert codebook.g3.owner == "GATE_ENGINE"
    assert codebook.g3.elements["G3_SV"].computation_rule == "G3_SV = Severity Floor of that G2"
    assert "Severity only goes up" in codebook.g3.elements["G3_SV"].help_text
    assert codebook.g3.elements["G3_FORWARD"].name == "Output to Gate 4"


def test_codebook_parses_g4_gate_engine_config() -> None:
    codebook = parse_codebook()

    assert codebook.g4.gate == "G4"
    assert codebook.g4.owner == "GATE_ENGINE"
    assert codebook.g4.severity_actions["SV0"].action == "ALLOW"
    assert codebook.g4.severity_actions["SV2"].action == "TRANSFORM"
    assert codebook.g4.severity_actions["SV3"].action == "BLOCK"
    assert "brief reason" in codebook.g4.severity_actions["SV3"].full_description


def test_codebook_parses_block_e_guideline_notes() -> None:
    codebook = parse_codebook()

    assert list(codebook.gl_specs) == ["GL-T1", "GL-A1", "GL-E1", "GL-CU1", "GL-O1"]
    assert codebook.gl_specs["GL-A1"].name == "ActionPriorityGL"
    assert "safety_check" in codebook.gl_specs["GL-A1"].special_rules
    assert codebook.gl_specs["GL-CU1"].applies_when == "Always"
    assert "trusted adult" in codebook.gl_specs["GL-O1"].special_rules


def test_codebook_parses_prompt_dictionary_runtime_variables() -> None:
    codebook = parse_codebook()
    prompt_dictionary = codebook.prompt_dictionary

    assert prompt_dictionary.runtime_variables["supportive"].definition.startswith("Use a warm")
    assert any(
        "Do not give medical advice" in rule
        for rule in prompt_dictionary.runtime_variables["cautious"].behavioral_rules
    )
    assert prompt_dictionary.runtime_variables["safety_check"].examples
    assert prompt_dictionary.runtime_variables["normal_advice"].key == "normal_advice"


def test_codebook_parses_prompt_dictionary_flag_prompts() -> None:
    codebook = parse_codebook()
    flag_prompts = codebook.prompt_dictionary.flag_prompts

    assert len(flag_prompts) == len(codebook.flag_mappings)
    assert "unsafe sexual content" in flag_prompts["has_unsafe_sexual_content"].context
    assert "substance use" in flag_prompts["has_substance_use_concern"].context
    assert "has_subsatance_use_concern" not in flag_prompts
    assert "biased or unfair assumption" in flag_prompts["has_loaded_premise"].context


def test_codebook_keeps_prompt_dictionary_dictionary_only() -> None:
    codebook = parse_codebook()
    prompt_dictionary = codebook.prompt_dictionary

    assert not hasattr(prompt_dictionary, "compliance_checklist")
    assert not hasattr(prompt_dictionary, "authoring_rules")


def test_codebook_parses_prompt_master_template() -> None:
    codebook = parse_codebook()
    template = codebook.prompt_master_template

    assert template.template_id == "MASTER_TEMPLATE"
    assert template.name == "Master Template"
    assert template.source == "classifier/docs/prompt-master-template.csv"
    assert "flag_context" in template.placeholders
    assert "attached_guidelines" in template.placeholders
    assert "You are a child-safe assistant responding to a child aged {age}" in template.template
    assert "{flag_example_start}" in template.template


def test_codebook_parses_prompt_rules_authoring_controls() -> None:
    codebook = parse_codebook()
    prompt_rules = codebook.prompt_rules

    assert prompt_rules.compliance_checklist["CHK-03"].item == "5-line limit instruction is present."
    assert "no topic content" in prompt_rules.compliance_checklist["CHK-05"].item
    assert prompt_rules.authoring_rules["PR-01"].name == "Gate Fidelity Rule"
    assert "5 lines or less" in prompt_rules.authoring_rules["PR-05"].description
