from __future__ import annotations

import json
import re
from typing import Any

from app.model_service import DEFAULT_CHAT_MODEL, generate_chat_response
from app.text_normalization_prompt import (
    TEXT_NORMALIZATION_SYSTEM_PROMPT,
    build_normalization_user_prompt,
)

_MOJIBAKE_REPLACEMENTS = (
    ("‚Äú", '"'),
    ("‚Äù", '"'),
    ("‚Äô", "'"),
    ("‚Äò", "'"),
    ("‚Äì", "-"),
    ("‚Äî", "-"),
    ("â€™", "'"),
    ("â€œ", '"'),
    ("â€\x9d", '"'),
    ("â€“", "-"),
    ("â€”", "-"),
    ("\u2018", "'"),
    ("\u2019", "'"),
    ("\u201c", '"'),
    ("\u201d", '"'),
    ("\u2013", "-"),
    ("\u2014", "-"),
)


def apply_deterministic_cleanup(text: str) -> str:
    cleaned = str(text)
    for source, target in _MOJIBAKE_REPLACEMENTS:
        cleaned = cleaned.replace(source, target)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("model did not return JSON")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("model JSON must be an object")
    return payload


def normalize_child_message(
    *,
    raw_message: str,
    child_profile: dict[str, Any],
    recent_context: list[str] | None = None,
    input_mode: str | None = None,
    system_prompt: str | None = None,
    model_name: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 256,
) -> dict[str, Any]:
    preprocessed = apply_deterministic_cleanup(raw_message)
    normalization_system_prompt = (system_prompt or "").strip() or TEXT_NORMALIZATION_SYSTEM_PROMPT
    generation = generate_chat_response(
        messages=[
            {"role": "system", "content": normalization_system_prompt},
            {
                "role": "user",
                "content": build_normalization_user_prompt(
                    raw_message=preprocessed,
                    child_profile=child_profile,
                    recent_context=recent_context or [],
                    input_mode=input_mode,
                ),
            },
        ],
        max_new_tokens=max_tokens,
        temperature=temperature,
        model_name=model_name,
    )
    answer = str(generation.get("answer", "")).strip()
    repairs: list[str] = []
    normalized_message = preprocessed
    try:
        payload = _extract_json_object(answer)
        candidate = str(payload.get("normalized_message", "")).strip()
        if candidate:
            normalized_message = apply_deterministic_cleanup(candidate)
        raw_repairs = payload.get("repairs", [])
        if isinstance(raw_repairs, list):
            repairs = [str(item).strip() for item in raw_repairs if str(item).strip()]
    except (ValueError, json.JSONDecodeError):
        normalized_message = apply_deterministic_cleanup(answer) or preprocessed
        repairs = ["llm_fallback_plain_text"]
    usage = dict(generation.get("usage", {}))
    return {
        "model_name": str(generation.get("model_name", model_name or DEFAULT_CHAT_MODEL)),
        "raw_message": raw_message,
        "preprocessed_message": preprocessed,
        "normalized_message": normalized_message or preprocessed,
        "repairs": repairs,
        "usage": usage,
    }
