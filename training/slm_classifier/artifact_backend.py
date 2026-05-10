from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from app.guardrails.gate_mapper import GUIDELINES, build_guardrail_decision
from app.models.guardrail_decision import GLSignal, GuardrailDecision
from training.slm_classifier.codebook import DOC_CODEBOOK_PATH
from training.slm_classifier.data_pipeline import CANONICAL_DATASET, GL_COLUMNS, build_input_text


ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "models" / "slm_classifier_artifact.json"
TOKEN_RE = re.compile(r"[a-z0-9']+")
MAX_FEATURES_PER_LABEL = 32
MIN_FEATURE_SCORE = 1.0
MIN_POSITIVE_SAMPLES = 2
ARTIFACT_VERSION = 3


def _codebook_fingerprint() -> str:
    return hashlib.sha256(DOC_CODEBOOK_PATH.read_bytes()).hexdigest()[:16]


def _tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _iter_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _feature_score(pos_count: int, neg_count: int, pos_total: int, neg_total: int) -> float:
    pos_rate = (pos_count + 1) / (pos_total + 2)
    neg_rate = (neg_count + 1) / (neg_total + 2)
    return math.log(pos_rate / neg_rate)


def train_artifact(dataset_path: Path = CANONICAL_DATASET, target_path: Path = ARTIFACT_PATH) -> dict[str, object]:
    rows = _iter_rows(dataset_path)
    if not rows:
        raise ValueError(f"No training rows found in {dataset_path}")

    texts = [build_input_text(row) for row in rows]
    token_sets = [set(_tokenize(text)) for text in texts]
    labels: list[dict[str, object]] = []
    for gl_column in GL_COLUMNS:
        gl_id = gl_column.upper().replace("_", "-")
        positive_indices = [idx for idx, row in enumerate(rows) if int(row.get(gl_column, 0)) == 1]
        negative_indices = [idx for idx, row in enumerate(rows) if int(row.get(gl_column, 0)) == 0]
        bias = len(positive_indices) / len(rows)
        if len(positive_indices) < MIN_POSITIVE_SAMPLES or not negative_indices:
            labels.append({"id": gl_id, "bias": round(bias, 4), "threshold": 0.5, "rules": []})
            continue

        pos_counter: Counter[str] = Counter()
        neg_counter: Counter[str] = Counter()
        for idx in positive_indices:
            pos_counter.update(token_sets[idx])
        for idx in negative_indices:
            neg_counter.update(token_sets[idx])

        ranked: list[tuple[str, float]] = []
        for token, count in pos_counter.items():
            score = _feature_score(count, neg_counter[token], len(positive_indices), len(negative_indices))
            if score >= MIN_FEATURE_SCORE:
                ranked.append((token, score))
        ranked.sort(key=lambda item: item[1], reverse=True)

        rules = [{"contains_any": [token], "score": round(min(0.55 + (score / 5.0), 0.99), 4)} for token, score in ranked[:MAX_FEATURES_PER_LABEL]]
        labels.append({"id": gl_id, "bias": round(bias, 4), "threshold": 0.5, "rules": rules})

    artifact = {
        "version": ARTIFACT_VERSION,
        "codebook_fingerprint": _codebook_fingerprint(),
        "model_type": "lexical-multilabel-artifact",
        "source_dataset": str(dataset_path),
        "labels": labels,
    }
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact


def load_artifact(path: Path = ARTIFACT_PATH) -> dict[str, object] | None:
    if not path.exists():
        return None
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if int(artifact.get("version", 0)) != ARTIFACT_VERSION:
        return None
    if str(artifact.get("codebook_fingerprint", "")) != _codebook_fingerprint():
        return None
    return artifact


def predict_scores(text: str, artifact: dict[str, object]) -> dict[str, float]:
    tokens = set(_tokenize(text))
    scores: dict[str, float] = {}
    for label in artifact.get("labels", []):
        score = float(label.get("bias", 0.0))
        for rule in label.get("rules", []):
            contains_any = {str(item).lower() for item in rule.get("contains_any", [])}
            contains_all = {str(item).lower() for item in rule.get("contains_all", [])}
            if contains_any and not (tokens & contains_any):
                continue
            if contains_all and not contains_all.issubset(tokens):
                continue
            score = max(score, float(rule.get("score", 0.0)))
        scores[str(label["id"])] = min(score, 1.0)
    return scores


def _signal(name: str, triggered: bool, confidence: float, emits: dict[str, bool | str]) -> GLSignal:
    return GLSignal(name=name, triggered=triggered, confidence=confidence, emits=emits if triggered else {})


def _emit_values(gl_id: str, age_band: str) -> dict[str, bool | str]:
    payload = dict(GUIDELINES[gl_id].get("emits", {}))
    if "age_band" in payload:
        payload["age_band"] = age_band
    return payload


def build_decision_from_artifact(
    question: str,
    age_band: str,
    language: str,
    recent_context: str,
    artifact: dict[str, object],
) -> GuardrailDecision:
    full_text = f"{question} {recent_context if recent_context != 'none' else ''}".lower().strip()
    scores = predict_scores(full_text, artifact)
    gl_signals: dict[str, GLSignal] = {}
    for gl_id, guideline in GUIDELINES.items():
        confidence = float(scores.get(gl_id, 0.0))
        triggered = confidence >= 0.5
        gl_signals[gl_id] = _signal(
            guideline["name"],
            triggered,
            confidence if triggered else max(confidence, 0.01),
            _emit_values(gl_id, age_band),
        )
    payload = build_guardrail_decision(
        question=question,
        age_band=age_band,
        language=language,
        recent_context=recent_context,
        gl_signals=gl_signals,
    )
    decision_fields = payload["decision"]
    confidence = min([signal.confidence for signal in gl_signals.values() if signal.triggered], default=0.0)
    return GuardrailDecision(
        input=payload["input"],
        gl_signals=gl_signals,
        active_gls=payload["active_gls"],
        gates=payload["gates"],
        decision=decision_fields,
        policy_bucket="allowed" if decision_fields["allow_llm"] else "soft_block",
        safety_category=payload["gates"]["G2"],
        response_mode=str(decision_fields["response_mode"]),
        risk_level=str(decision_fields["risk_level"]),
        parent_visible=bool(decision_fields["parent_visible"]),
        confidence=confidence,
        guideline_tags=payload["active_gls"],
        gate_values=payload["gates"],
        prompt_contract=payload["prompt_contract"],
        classifier_metadata={
            "backend": "artifact",
            "backend_version": f"lexical-artifact-v{ARTIFACT_VERSION}",
            "codebook_fingerprint": _codebook_fingerprint(),
            "dataset_fingerprint": str(artifact.get("codebook_fingerprint", "")),
        },
    )
