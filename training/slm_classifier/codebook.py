from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC_CODEBOOK_PATH = ROOT / "docs" / "GL-codebook.csv"


@dataclass
class LabelSpec:
    gl_id: str
    key: str
    name: str
    purpose: str
    emits: list[str]


@dataclass
class G2Spec:
    code: str
    description: str
    severity_floor: str
    modifiers: list[str] = field(default_factory=list)


@dataclass
class CodebookSpec:
    labels: list[LabelSpec]
    g2_specs: dict[str, G2Spec]


def _normalize_cell(value: str) -> str:
    return " ".join((value or "").replace("\u2009", " ").replace("\u2011", "-").split())


def _label_key(gl_id: str) -> str:
    return gl_id.lower().replace("-", "_")


def _parse_emit_list(raw: str) -> list[str]:
    cleaned = _normalize_cell(raw)
    emits: list[str] = []
    for part in cleaned.split(","):
        token = part.strip()
        if not token:
            continue
        token = token.split("=", 1)[0].strip()
        token = token.replace(" true", "").strip()
        emits.append(token)
    return emits


def _parse_modifier_list(raw: str) -> list[str]:
    cleaned = _normalize_cell(raw)
    if not cleaned or cleaned.lower() == "none":
        return []
    return [item.strip() for item in cleaned.split(",") if item.strip()]


def parse_codebook(path: Path = DOC_CODEBOOK_PATH) -> CodebookSpec:
    labels: list[LabelSpec] = []
    g2_specs: dict[str, G2Spec] = {}
    section = ""
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            first = _normalize_cell(row[0] if row else "")
            if not first:
                continue
            if first.startswith("BLOCK B"):
                section = "g2"
                continue
            if first.startswith("BLOCK E"):
                section = "gl"
                continue
            if first.startswith("BLOCK C") or first.startswith("BLOCK F"):
                section = ""
                continue
            if section == "gl" and re.match(r"GL-\d{2}$", first):
                labels.append(
                    LabelSpec(
                        gl_id=first,
                        key=_label_key(first),
                        name=_normalize_cell(row[1] if len(row) > 1 else ""),
                        purpose=_normalize_cell(row[2] if len(row) > 2 else ""),
                        emits=_parse_emit_list(row[2] if len(row) > 2 else ""),
                    )
                )
            if section == "g2" and re.match(r"^[A-Z_]+$", first) and first not in {"G2_LOV_ID", "NOTE"}:
                g2_specs[first] = G2Spec(
                    code=first,
                    description=_normalize_cell(row[1] if len(row) > 1 else ""),
                    severity_floor=_normalize_cell(row[3] if len(row) > 3 else "SV0"),
                    modifiers=_parse_modifier_list(row[4] if len(row) > 4 else ""),
                )
    return CodebookSpec(labels=labels, g2_specs=g2_specs)


def label_columns(path: Path = DOC_CODEBOOK_PATH) -> list[str]:
    return [item.key for item in parse_codebook(path).labels]
