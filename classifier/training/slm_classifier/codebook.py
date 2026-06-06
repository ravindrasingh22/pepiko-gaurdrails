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
    "gl-rules.yaml",
    "age-policy.yaml",
    "intent-lexicon.yaml",
    "flag-mappings.yaml",
    "modifier-tags.yaml",
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
    return [str(item).strip() for item in value if str(item).strip()]


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
class ParentVisibilitySpec:
    force_visible_if_age_lte: int
    risk_levels: list[str] = field(default_factory=list)


@dataclass
class CodebookSpec:
    g1_specs: dict[str, G1Spec]
    g2_specs: dict[str, G2Spec]
    gl_specs: dict[str, GLSpec]
    age_bands: dict[str, AgeBandSpec]
    intent_lexicon: dict[str, IntentLexiconSpec]
    flag_mappings: dict[str, FlagModifierSpec]
    modifier_tags: dict[str, dict[str, ModifierTagSpec]]
    parent_visibility: ParentVisibilitySpec

    @property
    def labels(self) -> list[GLSpec]:
        return list(self.gl_specs.values())


def parse_codebook(config_dir: Path = CODEBOOK_CONFIG_DIR) -> CodebookSpec:
    g1_raw = _read_yaml(config_dir / "g1.yaml").get("g1_lovs", {})
    g2_raw = _read_yaml(config_dir / "g2.yaml").get("g2_lovs", {})
    gl_raw = _read_yaml(config_dir / "gl-rules.yaml").get("gl_rules", {})
    age_raw = _read_yaml(config_dir / "age-policy.yaml")
    intent_raw = _read_yaml(config_dir / "intent-lexicon.yaml").get("intent_lexicon", {})
    flags_raw = _read_yaml(config_dir / "flag-mappings.yaml").get("flag_mappings", {})
    modifier_tags_raw = _read_yaml(config_dir / "modifier-tags.yaml").get("modifier_tags", {})

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
        parent_visibility=ParentVisibilitySpec(
            force_visible_if_age_lte=int(age_raw.get("parent_visibility", {}).get("force_visible_if_age_lte", 10)),
            risk_levels=_list(age_raw.get("parent_visibility", {}).get("risk_levels", ["medium", "high", "critical"])),
        ),
    )


def label_columns(config_dir: Path = CODEBOOK_CONFIG_DIR) -> list[str]:
    return list(parse_codebook(config_dir).gl_specs.keys())
