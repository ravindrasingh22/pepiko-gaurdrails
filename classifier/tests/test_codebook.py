from training.slm_classifier.codebook import CODEBOOK_CONFIG_DIR, codebook_fingerprint, parse_codebook
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
    assert codebook_fingerprint()
    assert codebook.gl_specs["GL-C1"].name == "Comparative Harmful Choice Detector"


def test_codebook_carries_g2_classifier_boundary_guidance() -> None:
    codebook = parse_codebook()

    assert "individual or non-protected group" in codebook.g2_specs["HATE_GROUP"].notes_for_classifier
    assert "ordinary experiments or curiosity" in codebook.g2_specs["DANGEROUS"].notes_for_classifier
    assert "clear self-harm language" in codebook.g2_specs["EMOTIONAL"].notes_for_classifier
    assert "only sad or stressed" in codebook.g2_specs["SELF_HARM"].notes_for_classifier
    assert "major harm or serious illegal damage" in codebook.g2_specs["SAFETY_HAZARD"].notes_for_classifier
