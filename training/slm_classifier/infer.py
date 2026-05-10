from __future__ import annotations

import argparse
import json

from app.guardrails import slm_classifier
from app.guardrails.gate_mapper import age_band_from_age, resolve_age_band


def _normalize_input(question: str, age_band: str, language: str, recent_context: str) -> dict[str, object]:
    age_lookup = {
        "5-6": 6,
        "7-8": 8,
        "9-10": 10,
        "11-12": 12,
        "13-14": 14,
        "15-16": 16,
        "17": 17,
    }
    age = age_lookup.get(age_band)
    if age is None:
        resolved_band = resolve_age_band(12, age_band)
        age = age_lookup.get(resolved_band, 12)
    resolved_band = age_band_from_age(age)
    return {
        "text": question,
        "recent_context": [] if recent_context == "none" else [recent_context],
        "child_profile": {
            "age": age,
            "age_group": resolved_band,
            "language": language,
        },
        "resolved_age_band": resolved_band,
    }


def _run_classifier(mode: str, question: str, age_band: str, language: str, recent_context: str) -> dict[str, object]:
    normalized = _normalize_input(question, age_band, language, recent_context)
    if mode == "artifact":
        decision = slm_classifier.classify_artifact(normalized)
        backend = "artifact"
    else:
        decision = slm_classifier.classify_heuristic(normalized)
        backend = "heuristic"

    return {
        "mode": mode,
        "backend": backend,
        "input": {
            "question": question,
            "age_band": age_band,
            "language": language,
            "recent_context": recent_context,
        },
        "active_gls": decision.active_gls or decision.guideline_tags,
        "gates": decision.gates or decision.gate_values,
        "decision": decision.decision,
        "prompt_contract": decision.prompt_contract,
        "confidence": decision.confidence,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the guardrail classifier for a single question.")
    parser.add_argument("--mode", choices=["artifact", "heuristic"], default="artifact")
    parser.add_argument("--question", required=True)
    parser.add_argument("--age-band", default="9-12")
    parser.add_argument("--language", default="en")
    parser.add_argument("--recent-context", default="none")
    args = parser.parse_args()

    print(
        json.dumps(
            _run_classifier(
                mode=args.mode,
                question=args.question,
                age_band=args.age_band,
                language=args.language,
                recent_context=args.recent_context,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
