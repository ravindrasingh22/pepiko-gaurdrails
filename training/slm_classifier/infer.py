from __future__ import annotations

import argparse
import json

from app.guardrails import slm_classifier
from app.guardrails.gate_mapper import age_band_from_age, resolve_age_band
from training.slm_classifier.slm_backend import available_cores, resolve_core


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


def _serialize_decision(mode: str, backend: str, question: str, age_band: str, language: str, recent_context: str, decision: object, core: str | None = None) -> dict[str, object]:
    return {
        "mode": mode,
        "backend": backend,
        "core_model": core,
        "input": {
            "question": question,
            "age_band": age_band,
            "language": language,
            "recent_context": recent_context,
        },
        "active_gls": decision.active_gls or decision.guideline_tags,
        "gates": decision.gates or decision.gate_values,
        "decision": decision.decision,
        "confidence": decision.confidence,
        "classifier_metadata": decision.classifier_metadata,
    }


def _run_classifier(mode: str, question: str, age_band: str, language: str, recent_context: str, core: str = "smol") -> dict[str, object]:
    normalized = _normalize_input(question, age_band, language, recent_context)
    if mode == "slm":
        if core == "both":
            results = {}
            for item in available_cores():
                decision = slm_classifier.classify_slm(normalized, core=item)
                results[item] = _serialize_decision(mode, "slm", question, age_band, language, recent_context, decision, core=item)
            return {"mode": mode, "backend": "slm", "core_model": "both", "results": results}
        resolved_core = resolve_core(core)
        decision = slm_classifier.classify_slm(normalized, core=resolved_core)
        backend = "slm"
        return _serialize_decision(mode, backend, question, age_band, language, recent_context, decision, core=resolved_core)
    elif mode == "artifact":
        decision = slm_classifier.classify_artifact(normalized)
        backend = "artifact"
    else:
        decision = slm_classifier.classify_heuristic(normalized)
        backend = "heuristic"
    return _serialize_decision(mode, backend, question, age_band, language, recent_context, decision)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the guardrail classifier for a single question.")
    parser.add_argument("--mode", choices=["slm", "artifact", "heuristic"], default="slm")
    parser.add_argument("--question", required=True)
    parser.add_argument("--age-band", default="9-12")
    parser.add_argument("--language", default="en")
    parser.add_argument("--recent-context", default="none")
    parser.add_argument("--core", choices=["smol", "deberta", "both"], default="smol")
    args = parser.parse_args()

    print(
        json.dumps(
            _run_classifier(
                mode=args.mode,
                question=args.question,
                age_band=args.age_band,
                language=args.language,
                recent_context=args.recent_context,
                core=args.core,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
