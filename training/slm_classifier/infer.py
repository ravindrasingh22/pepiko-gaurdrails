from __future__ import annotations

import argparse
import json

from app.guardrails import slm_classifier
from training.slm_classifier.artifact_backend import build_decision_from_artifact, load_artifact


def _normalize_input(question: str, age_band: str, language: str, recent_context: str) -> dict[str, object]:
    age_lookup = {"5-8": 8, "8-10": 9, "9-12": 10, "13-17": 15}
    return {
        "text": question,
        "recent_context": [] if recent_context == "none" else [recent_context],
        "child_profile": {
            "age": age_lookup.get(age_band, 10),
            "age_group": age_band,
            "language": language,
        },
    }


def _run_classifier(mode: str, question: str, age_band: str, language: str, recent_context: str) -> dict[str, object]:
    normalized = _normalize_input(question, age_band, language, recent_context)
    backend = "heuristic"
    if mode == "artifact":
        artifact = load_artifact()
        if artifact is not None:
            decision = build_decision_from_artifact(
                question=question,
                age_band=age_band,
                language=language,
                recent_context=recent_context,
                artifact=artifact,
            )
            backend = "artifact"
        else:
            decision = slm_classifier.classify_heuristic(normalized)
            backend = "artifact_missing_fallback"
    else:
        decision = slm_classifier.classify_heuristic(normalized)

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
