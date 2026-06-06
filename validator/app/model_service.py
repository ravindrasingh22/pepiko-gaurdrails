from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal


DEFAULT_VALIDATOR_MODEL = "microsoft/deberta-v3-small"
DEFAULT_VALIDATOR_ARTIFACT = Path(__file__).resolve().parents[2] / "models" / "piku-validator-deberta-v3-small"
DEFAULT_VALIDATOR_THRESHOLD = float(os.environ.get("VALIDATOR_SAFETY_THRESHOLD", "0.85"))
VALIDATOR_MODEL_PATH = os.environ.get("VALIDATOR_MODEL_PATH", str(DEFAULT_VALIDATOR_ARTIFACT))

FALLBACK_LEXICON = {
    "5-7": "Let's explore something super fun instead, like space stars or cute animals! What is your favorite animal?",
    "8-12": "I'd love to try a different topic with you. What science mystery or adventure story should we look into next?",
    "9-10": "I'd love to try a different topic with you. What science mystery or adventure story should we look into next?",
    "11-12": "I'd love to try a different topic with you. What science mystery or adventure story should we look into next?",
    "13-15": "Let's pivot to a different angle on this subject. Let me know what you want to investigate next.",
}

UNSAFE_TERMS = (
    "sharp knife",
    "blood",
    "graphic",
    "gore",
    "kill",
    "suicide",
    "self harm",
    "porn",
    "have sex",
    "explicit sex",
    "nudes",
    "naked children",
    "make a bomb",
    "poison",
    "hack",
    "get away with",
)


@dataclass(frozen=True)
class ValidationResult:
    status: Literal["safe", "unsafe"]
    score: float
    label: Literal[0, 1]
    safe_score: float
    unsafe_score: float
    age_group: str
    response_text: str
    backend: Literal["deberta_sequence_classifier", "lexicon_fallback"]
    model_path: str
    trained: bool
    threshold: float
    action: Literal["allow", "fallback"]
    delivered_text: str
    fallback_text: str | None
    reasons: list[str]
    usage: dict[str, int]


def format_validator_input(age_group: str, response_text: str) -> str:
    return f"Age Group: {age_group.strip()} | Content: {' '.join(response_text.strip().split())}"


def normalize_text(text: str) -> str:
    lowered = (text or "").lower().strip()
    lowered = re.sub(r"[^\w\s]", " ", lowered)
    return " ".join(lowered.split())


def fallback_text_for_age(age_group: str) -> str:
    return FALLBACK_LEXICON.get(age_group, "Let's choose a new safe topic to learn about!")


def _artifact_exists(model_path: str) -> bool:
    path = Path(model_path)
    return path.exists() and any((path / name).exists() for name in ("pytorch_model.bin", "model.safetensors"))


@lru_cache(maxsize=1)
def _load_model(model_path: str):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSequenceClassification.from_pretrained(model_path, num_labels=2)
    model.eval()
    return tokenizer, model


def _run_deberta_validator(age_group: str, response_text: str, threshold: float, model_path: str) -> ValidationResult:
    import torch
    import torch.nn.functional as F

    tokenizer, model = _load_model(model_path)
    formatted_input = format_validator_input(age_group, response_text)
    inputs = tokenizer(formatted_input, return_tensors="pt", truncation=True, max_length=512)
    validator_tokens = int(inputs["input_ids"].shape[-1])
    with torch.no_grad():
        outputs = model(**inputs)
    probabilities = F.softmax(outputs.logits, dim=-1).squeeze().tolist()
    safe_score = float(probabilities[0])
    unsafe_score = float(probabilities[1])
    return _build_result(
        age_group=age_group,
        response_text=response_text,
        safe_score=safe_score,
        unsafe_score=unsafe_score,
        threshold=threshold,
        backend="deberta_sequence_classifier",
        model_path=model_path,
        trained=True,
        reasons=["sequence_classifier_probability"],
        usage={
            "prompt_tokens": validator_tokens,
            "completion_tokens": 0,
            "total_tokens": validator_tokens,
        },
    )


def _run_lexicon_fallback(age_group: str, response_text: str, threshold: float, model_path: str) -> ValidationResult:
    normalized = normalize_text(response_text)
    formatted_input = format_validator_input(age_group, response_text)
    validator_tokens = len(normalize_text(formatted_input).split())
    matched_terms = [term for term in UNSAFE_TERMS if term in normalized]
    unsafe_score = 0.91 if matched_terms else 0.08
    safe_score = 1.0 - unsafe_score
    reasons = [f"fallback_lexicon:{term}" for term in matched_terms] or ["fallback_lexicon:no_unsafe_terms"]
    return _build_result(
        age_group=age_group,
        response_text=response_text,
        safe_score=safe_score,
        unsafe_score=unsafe_score,
        threshold=threshold,
        backend="lexicon_fallback",
        model_path=model_path,
        trained=False,
        reasons=reasons,
        usage={
            "prompt_tokens": validator_tokens,
            "completion_tokens": 0,
            "total_tokens": validator_tokens,
        },
    )


def _build_result(
    *,
    age_group: str,
    response_text: str,
    safe_score: float,
    unsafe_score: float,
    threshold: float,
    backend: Literal["deberta_sequence_classifier", "lexicon_fallback"],
    model_path: str,
    trained: bool,
    reasons: list[str],
    usage: dict[str, int],
) -> ValidationResult:
    unsafe = unsafe_score >= threshold
    fallback_text = fallback_text_for_age(age_group) if unsafe else None
    delivered_text = fallback_text if unsafe and fallback_text else response_text
    return ValidationResult(
        status="unsafe" if unsafe else "safe",
        score=round(unsafe_score if unsafe else safe_score, 4),
        label=1 if unsafe else 0,
        safe_score=round(safe_score, 4),
        unsafe_score=round(unsafe_score, 4),
        age_group=age_group,
        response_text=response_text,
        backend=backend,
        model_path=model_path,
        trained=trained,
        threshold=threshold,
        action="fallback" if unsafe else "allow",
        delivered_text=delivered_text,
        fallback_text=fallback_text,
        reasons=reasons,
        usage=usage,
    )


def validate_response_with_score(
    *,
    age_group: str,
    response_text: str,
    threshold: float = DEFAULT_VALIDATOR_THRESHOLD,
    model_path: str | None = None,
) -> ValidationResult:
    resolved_age_group = age_group.strip()
    resolved_response_text = " ".join(response_text.strip().split())
    resolved_model_path = model_path or VALIDATOR_MODEL_PATH
    if _artifact_exists(resolved_model_path):
        return _run_deberta_validator(resolved_age_group, resolved_response_text, threshold, resolved_model_path)
    return _run_lexicon_fallback(resolved_age_group, resolved_response_text, threshold, resolved_model_path)
