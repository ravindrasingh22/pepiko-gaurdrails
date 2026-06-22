from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
CODEBOOK_CONFIG_DIR = ROOT / "configs" / "codebook-config"
CODEBOOK_CONFIG_FILES = (
    "g1.yaml",
    "g2.yaml",
    "g3.yml",
    "g4.yml",
    "gl-rules.yml",
    "age-policy.yaml",
    "intent-lexicon.yaml",
    "flag-mappings.yaml",
    "flag-precendence-order.yml",
    "modifier-tags.yaml",
    "prompt-dictionary.yaml",
    "prompt-master-template.yml",
    "prompt-rules.yaml",
)


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping in codebook config: {path}")
    return payload


def _list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if isinstance(item, dict) and len(item) == 1:
            prefix, suffix = next(iter(item.items()))
            text = f"{prefix}: {suffix}"
        else:
            text = str(item)
        if text.strip():
            normalized.append(text.strip())
    return normalized


def codebook_config_paths(config_dir: Path = CODEBOOK_CONFIG_DIR) -> list[Path]:
    return [config_dir / filename for filename in CODEBOOK_CONFIG_FILES]


def codebook_fingerprint(config_dir: Path = CODEBOOK_CONFIG_DIR) -> str:
    digest = hashlib.sha256()
    for path in codebook_config_paths(config_dir):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def codebook_latest_mtime(config_dir: Path = CODEBOOK_CONFIG_DIR) -> float:
    return max(path.stat().st_mtime for path in codebook_config_paths(config_dir))


@dataclass
class G1Spec:
    lov_id: str
    name: str
    definition: str
    notes_for_classifier: str = ""


@dataclass
class G2Spec:
    lov_id: str
    name: str
    definition: str
    severity_floor: str
    modifiers: list[str] = field(default_factory=list)
    associated_flags: list[str] = field(default_factory=list)
    notes_for_classifier: str = ""

    @property
    def description(self) -> str:
        return self.definition


@dataclass
class G3ElementSpec:
    element_id: str
    name: str
    computation_rule: str
    example: str
    help_text: str


@dataclass
class G3Spec:
    block: str
    gate: str
    name: str
    owner: str
    question: str
    note: str
    elements: dict[str, G3ElementSpec]


@dataclass
class G4SeverityActionSpec:
    severity: str
    action: str
    full_description: str


@dataclass
class G4Spec:
    block: str
    gate: str
    name: str
    owner: str
    question: str
    note: str
    how_to_read: list[str] = field(default_factory=list)
    severity_actions: dict[str, G4SeverityActionSpec] = field(default_factory=dict)


@dataclass
class GLSpec:
    gl_id: str
    name: str
    applies_when: str
    uses_g1_lovs: list[str] = field(default_factory=list)
    uses_g2_lovs: list[str] = field(default_factory=list)
    special_rules: str = ""
    emits: list[str] = field(default_factory=list)

    @property
    def purpose(self) -> str:
        return self.special_rules


@dataclass
class AgeBandSpec:
    age_band: str
    max_answer_style: str
    max_words: int
    depth: str
    tone: str = "age_calibrated"


@dataclass
class IntentLexiconSpec:
    lov: str
    families: list[str] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)


@dataclass
class ModifierTagSpec:
    category: str
    tag: str
    description: str


@dataclass
class FlagModifierSpec:
    flag: str
    tone: str
    action: str
    escalation: str


@dataclass
class FlagPrecedenceOrderSpec:
    block: str
    name: str
    rule: str
    rankings: dict[str, int]


@dataclass
class PromptRuntimeVariableSpec:
    key: str
    definition: str
    behavioral_rules: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)


@dataclass
class FlagPromptSpec:
    flag: str
    context: str
    guidance: str
    example_start: str


@dataclass
class PromptChecklistSpec:
    check_id: str
    item: str
    how_to_verify: str
    applies_to: str
    fail_condition: str


@dataclass
class PromptAuthoringRuleSpec:
    rule_id: str
    name: str
    description: str
    applies_to: str
    violation_pattern: str
    corrective_action: str


@dataclass
class PromptDictionarySpec:
    runtime_variables: dict[str, PromptRuntimeVariableSpec]
    flag_prompts: dict[str, FlagPromptSpec]


@dataclass
class PromptRulesSpec:
    compliance_checklist: dict[str, PromptChecklistSpec]
    authoring_rules: dict[str, PromptAuthoringRuleSpec]


@dataclass
class PromptMasterTemplateSpec:
    template_id: str
    name: str
    source: str
    placeholders: list[str] = field(default_factory=list)
    template: str = ""


@dataclass
class ParentVisibilitySpec:
    force_visible_if_age_lte: int
    risk_levels: list[str] = field(default_factory=list)


@dataclass
class CodebookSpec:
    g1_specs: dict[str, G1Spec]
    g2_specs: dict[str, G2Spec]
    g3: G3Spec
    g4: G4Spec
    gl_specs: dict[str, GLSpec]
    age_bands: dict[str, AgeBandSpec]
    intent_lexicon: dict[str, IntentLexiconSpec]
    flag_mappings: dict[str, FlagModifierSpec]
    flag_precedence_order: FlagPrecedenceOrderSpec
    modifier_tags: dict[str, dict[str, ModifierTagSpec]]
    prompt_dictionary: PromptDictionarySpec
    prompt_master_template: PromptMasterTemplateSpec
    prompt_rules: PromptRulesSpec
    parent_visibility: ParentVisibilitySpec

    @property
    def labels(self) -> list[GLSpec]:
        return list(self.gl_specs.values())


def parse_codebook(config_dir: Path = CODEBOOK_CONFIG_DIR) -> CodebookSpec:
    g1_raw = _read_yaml(config_dir / "g1.yaml").get("g1_lovs", {})
    g2_raw = _read_yaml(config_dir / "g2.yaml").get("g2_lovs", {})
    g3_raw = _read_yaml(config_dir / "g3.yml").get("g3", {})
    g4_raw = _read_yaml(config_dir / "g4.yml").get("g4", {})
    gl_raw = _read_yaml(config_dir / "gl-rules.yml").get("gl_rules", {})
    age_raw = _read_yaml(config_dir / "age-policy.yaml")
    intent_raw = _read_yaml(config_dir / "intent-lexicon.yaml").get("intent_lexicon", {})
    flags_raw = _read_yaml(config_dir / "flag-mappings.yaml").get("flag_mappings", {})
    flag_precedence_raw = _read_yaml(config_dir / "flag-precendence-order.yml").get("flag_precedence_order", {})
    modifier_tags_raw = _read_yaml(config_dir / "modifier-tags.yaml").get("modifier_tags", {})
    prompt_dictionary_raw = _read_yaml(config_dir / "prompt-dictionary.yaml").get("prompt_dictionary", {})
    prompt_master_template_raw = _read_yaml(config_dir / "prompt-master-template.yml").get("prompt_master_template", {})
    prompt_rules_raw = _read_yaml(config_dir / "prompt-rules.yaml").get("prompt_rules", {})

    return CodebookSpec(
        g1_specs={
            str(lov_id): G1Spec(
                lov_id=str(lov_id),
                name=str(spec.get("name", "")),
                definition=str(spec.get("definition", "")),
                notes_for_classifier=str(spec.get("notes_for_classifier", "")),
            )
            for lov_id, spec in g1_raw.items()
        },
        g2_specs={
            str(lov_id): G2Spec(
                lov_id=str(lov_id),
                name=str(spec.get("name", "")),
                definition=str(spec.get("definition", "")),
                severity_floor=str(spec.get("severity_floor", "SV0")),
                modifiers=_list(spec.get("modifiers", [])),
                associated_flags=_list(spec.get("associated_flags", [])),
                notes_for_classifier=str(spec.get("notes_for_classifier", "")),
            )
            for lov_id, spec in g2_raw.items()
        },
        g3=G3Spec(
            block=str(g3_raw.get("block", "")),
            gate=str(g3_raw.get("gate", "")),
            name=str(g3_raw.get("name", "")),
            owner=str(g3_raw.get("owner", "")),
            question=str(g3_raw.get("question", "")),
            note=str(g3_raw.get("note", "")),
            elements={
                str(element_id): G3ElementSpec(
                    element_id=str(element_id),
                    name=str(spec.get("name", "")),
                    computation_rule=str(spec.get("computation_rule", "")),
                    example=str(spec.get("example", "")),
                    help_text=str(spec.get("help_text", "")),
                )
                for element_id, spec in g3_raw.get("elements", {}).items()
                if isinstance(spec, dict)
            },
        ),
        g4=G4Spec(
            block=str(g4_raw.get("block", "")),
            gate=str(g4_raw.get("gate", "")),
            name=str(g4_raw.get("name", "")),
            owner=str(g4_raw.get("owner", "")),
            question=str(g4_raw.get("question", "")),
            note=str(g4_raw.get("note", "")),
            how_to_read=_list(g4_raw.get("how_to_read", [])),
            severity_actions={
                str(severity): G4SeverityActionSpec(
                    severity=str(severity),
                    action=str(spec.get("action", "")),
                    full_description=str(spec.get("full_description", "")),
                )
                for severity, spec in g4_raw.get("severity_actions", {}).items()
                if isinstance(spec, dict)
            },
        ),
        gl_specs={
            str(gl_id): GLSpec(
                gl_id=str(gl_id),
                name=str(spec.get("name", "")),
                applies_when=str(spec.get("applies_when", "")),
                uses_g1_lovs=_list(spec.get("uses_g1_lovs", [])),
                uses_g2_lovs=_list(spec.get("uses_g2_lovs", [])),
                special_rules=str(spec.get("special_rules", "")),
                emits=_list(spec.get("emits", [])),
            )
            for gl_id, spec in gl_raw.items()
            if isinstance(spec, dict) and str(spec.get("name", "")).strip()
        },
        age_bands={
            str(age_band): AgeBandSpec(
                age_band=str(age_band),
                max_answer_style=str(spec.get("max_answer_style", "")),
                max_words=int(spec.get("max_words", 0)),
                depth=str(spec.get("depth", "")),
                tone=str(spec.get("tone", "age_calibrated")),
            )
            for age_band, spec in age_raw.get("age_bands", {}).items()
        },
        intent_lexicon={
            str(lov): IntentLexiconSpec(
                lov=str(lov),
                families=_list(spec.get("families", [])),
                phrases=_list(spec.get("phrases", [])),
            )
            for lov, spec in intent_raw.items()
        },
        flag_mappings={
            str(flag): FlagModifierSpec(
                flag=str(flag),
                tone=str(spec.get("tone", "")),
                action=str(spec.get("action", "")),
                escalation=str(spec.get("escalation", "")),
            )
            for flag, spec in flags_raw.items()
        },
        flag_precedence_order=FlagPrecedenceOrderSpec(
            block=str(flag_precedence_raw.get("block", "")),
            name=str(flag_precedence_raw.get("name", "")),
            rule=str(flag_precedence_raw.get("rule", "")),
            rankings={
                str(flag): int(rank)
                for flag, rank in flag_precedence_raw.get("rankings", {}).items()
                if str(flag).strip()
            },
        ),
        modifier_tags={
            str(category): {
                str(tag): ModifierTagSpec(
                    category=str(category),
                    tag=str(tag),
                    description=str(spec.get("description", "")),
                )
                for tag, spec in tags.items()
                if isinstance(spec, dict)
            }
            for category, tags in modifier_tags_raw.items()
            if isinstance(tags, dict)
        },
        prompt_dictionary=PromptDictionarySpec(
            runtime_variables={
                str(key): PromptRuntimeVariableSpec(
                    key=str(key),
                    definition=str(spec.get("definition", "")),
                    behavioral_rules=_list(spec.get("behavioral_rules", [])),
                    examples=_list(spec.get("examples", [])),
                )
                for key, spec in prompt_dictionary_raw.get("runtime_variables", {}).items()
                if isinstance(spec, dict)
            },
            flag_prompts={
                str(flag): FlagPromptSpec(
                    flag=str(flag),
                    context=str(spec.get("context", "")),
                    guidance=str(spec.get("guidance", "")),
                    example_start=str(spec.get("example_start", "")),
                )
                for flag, spec in prompt_dictionary_raw.get("flag_prompts", {}).items()
                if isinstance(spec, dict)
            },
        ),
        prompt_master_template=PromptMasterTemplateSpec(
            template_id=str(prompt_master_template_raw.get("id", "")),
            name=str(prompt_master_template_raw.get("name", "")),
            source=str(prompt_master_template_raw.get("source", "")),
            placeholders=_list(prompt_master_template_raw.get("placeholders", [])),
            template=str(prompt_master_template_raw.get("template", "")),
        ),
        prompt_rules=PromptRulesSpec(
            compliance_checklist={
                str(check_id): PromptChecklistSpec(
                    check_id=str(check_id),
                    item=str(spec.get("item", "")),
                    how_to_verify=str(spec.get("how_to_verify", "")),
                    applies_to=str(spec.get("applies_to", "")),
                    fail_condition=str(spec.get("fail_condition", "")),
                )
                for check_id, spec in prompt_rules_raw.get("compliance_checklist", {}).items()
                if isinstance(spec, dict)
            },
            authoring_rules={
                str(rule_id): PromptAuthoringRuleSpec(
                    rule_id=str(rule_id),
                    name=str(spec.get("name", "")),
                    description=str(spec.get("description", "")),
                    applies_to=str(spec.get("applies_to", "")),
                    violation_pattern=str(spec.get("violation_pattern", "")),
                    corrective_action=str(spec.get("corrective_action", "")),
                )
                for rule_id, spec in prompt_rules_raw.get("authoring_rules", {}).items()
                if isinstance(spec, dict)
            },
        ),
        parent_visibility=ParentVisibilitySpec(
            force_visible_if_age_lte=int(age_raw.get("parent_visibility", {}).get("force_visible_if_age_lte", 10)),
            risk_levels=_list(age_raw.get("parent_visibility", {}).get("risk_levels", ["medium", "high", "critical"])),
        ),
    )


def label_columns(config_dir: Path = CODEBOOK_CONFIG_DIR) -> list[str]:
    return list(parse_codebook(config_dir).gl_specs.keys())
