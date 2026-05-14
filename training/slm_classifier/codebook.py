from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC_CODEBOOK_PATH = ROOT / "docs" / "GL-codebook.csv"


def _normalize_cell(value: str) -> str:
    return " ".join((value or "").replace("\u2009", " ").replace("\u2011", "-").split())


def _normalize_dash(value: str) -> str:
    return re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2212]", "-", value or "")


def _normalize_id(value: str) -> str:
    return _normalize_dash(_normalize_cell(value)).strip()


def _split_csv_list(raw: str) -> list[str]:
    cleaned = _normalize_id(raw)
    if not cleaned or cleaned.lower() in {"none", "(none)", "any"}:
        return []
    return [item.strip() for item in cleaned.split(",") if item.strip()]


def _parse_int(raw: str) -> int | None:
    cleaned = _normalize_cell(raw)
    return int(cleaned) if cleaned.isdigit() else None


@dataclass
class G1Spec:
    lov_id: str
    name: str
    definition: str
    notes_for_classifier: str


@dataclass
class G2Spec:
    lov_id: str
    name: str
    definition: str
    severity_floor: str
    modifiers: list[str] = field(default_factory=list)
    notes_for_classifier: str = ""


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
    parent_visibility: ParentVisibilitySpec

    @property
    def labels(self) -> list[GLSpec]:
        return list(self.gl_specs.values())


def parse_codebook(path: Path = DOC_CODEBOOK_PATH) -> CodebookSpec:
    g1_specs: dict[str, G1Spec] = {}
    g2_specs: dict[str, G2Spec] = {}
    gl_specs: dict[str, GLSpec] = {}
    age_bands: dict[str, AgeBandSpec] = {}
    intent_lexicon: dict[str, IntentLexiconSpec] = {}
    parent_visibility = ParentVisibilitySpec(force_visible_if_age_lte=10, risk_levels=["medium", "high", "critical"])
    section = ""

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            first = _normalize_cell(row[0] if row else "")
            if not first:
                continue
            if first.startswith("BLOCK A"):
                section = "g1"
                continue
            if first.startswith("BLOCK B"):
                section = "g2"
                continue
            if first.startswith("BLOCK E"):
                section = "gl"
                continue
            if first.startswith("BLOCK I"):
                section = "age"
                continue
            if first.startswith("BLOCK J"):
                section = "intent"
                continue
            if first.startswith("BLOCK "):
                section = ""
                continue

            normalized_first = _normalize_id(first)
            if section == "g1" and normalized_first not in {"G1_LOV_ID", "NOTE"} and re.match(r"^[A-Z_]+$", normalized_first):
                g1_specs[normalized_first] = G1Spec(
                    lov_id=normalized_first,
                    name=_normalize_cell(row[1] if len(row) > 1 else ""),
                    definition=_normalize_cell(row[2] if len(row) > 2 else ""),
                    notes_for_classifier=_normalize_cell(row[3] if len(row) > 3 else ""),
                )
                continue

            if section == "g2" and normalized_first not in {"G2_LOV_ID", "NOTE"} and re.match(r"^[A-Z_]+$", normalized_first):
                g2_specs[normalized_first] = G2Spec(
                    lov_id=normalized_first,
                    name=_normalize_cell(row[1] if len(row) > 1 else ""),
                    definition=_normalize_cell(row[2] if len(row) > 2 else ""),
                    severity_floor=_normalize_id(row[3] if len(row) > 3 else "SV0"),
                    modifiers=_split_csv_list(row[4] if len(row) > 4 else ""),
                    notes_for_classifier=_normalize_cell(row[5] if len(row) > 5 else ""),
                )
                continue

            if section == "gl" and normalized_first not in {"GL_ID", "HOW TO READ"} and re.match(r"^GL-[A-Z]\d+$", normalized_first):
                gl_specs[normalized_first] = GLSpec(
                    gl_id=normalized_first,
                    name=_normalize_cell(row[1] if len(row) > 1 else ""),
                    applies_when=_normalize_dash(_normalize_cell(row[2] if len(row) > 2 else "")),
                    uses_g1_lovs=_split_csv_list(row[3] if len(row) > 3 else ""),
                    uses_g2_lovs=_split_csv_list(row[4] if len(row) > 4 else ""),
                    special_rules=_normalize_dash(_normalize_cell(row[5] if len(row) > 5 else "")),
                )
                continue

            if section == "age" and normalized_first != "AGE_BAND" and re.match(r"^\d{1,2}(?:-\d{1,2})?$", normalized_first):
                max_words = _parse_int(row[2] if len(row) > 2 else "") or 0
                age_bands[normalized_first] = AgeBandSpec(
                    age_band=normalized_first,
                    max_answer_style=_normalize_cell(row[1] if len(row) > 1 else ""),
                    max_words=max_words,
                    depth=_normalize_id(row[3] if len(row) > 3 else ""),
                )
                continue

            if section == "intent" and normalized_first != "LOV" and re.match(r"^[A-Z_]+$", normalized_first):
                families_raw = _normalize_cell(row[1] if len(row) > 1 else "")
                phrases_raw = _normalize_cell(row[2] if len(row) > 2 else "")
                intent_lexicon[normalized_first] = IntentLexiconSpec(
                    lov=normalized_first,
                    families=[item.strip() for item in families_raw.split(";") if item.strip()],
                    phrases=[item.strip() for item in phrases_raw.split(";") if item.strip()],
                )
                continue

            if section == "age" and normalized_first == "force_visible_if_age_lte":
                threshold = _parse_int(row[1] if len(row) > 1 else "")
                if threshold is not None:
                    parent_visibility.force_visible_if_age_lte = threshold
                continue

            if section == "age" and normalized_first == "risk_levels":
                parent_visibility.risk_levels = _split_csv_list(row[1] if len(row) > 1 else "")

    return CodebookSpec(
        g1_specs=g1_specs,
        g2_specs=g2_specs,
        gl_specs=gl_specs,
        age_bands=age_bands,
        intent_lexicon=intent_lexicon,
        parent_visibility=parent_visibility,
    )


def label_columns(path: Path = DOC_CODEBOOK_PATH) -> list[str]:
    return list(parse_codebook(path).gl_specs.keys())
