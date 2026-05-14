from __future__ import annotations

import argparse
import json

from app.guardrails import slm_classifier
from app.guardrails.runtime_contracts import classifier_output_from_decision
from app.models.child_profile import ChildProfile
from training.slm_classifier.runtime_config import load_classifier_runtime_config


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
    age = age_lookup.get(age_band, 12)
    return {
        "text": question,
        "recent_context": [] if recent_context == "none" else [recent_context],
        "child_profile": {
            "age": age,
            "age_group": age_band,
            "language": language,
        },
        "resolved_age_band": age_band,
    }


def _classify(mode: str, normalized: dict[str, object]):
    if mode == "slm":
        return slm_classifier.classify_slm(normalized)
    if mode == "artifact":
        return slm_classifier.classify_artifact(normalized)
    if mode == "auto":
        return slm_classifier.classify(normalized)
    return slm_classifier.classify_heuristic(normalized)


def run_infer(mode: str, question: str, age_band: str, language: str, recent_context: str) -> dict[str, object]:
    normalized = _normalize_input(question, age_band, language, recent_context)
    decision = _classify(mode, normalized)
    profile = ChildProfile(age=int(normalized["child_profile"]["age"]), age_group=age_band, language=language)
    payload = classifier_output_from_decision(question, profile, decision)
    payload["backend"] = mode if mode != "auto" else load_classifier_runtime_config().selected_backend
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Print pure classifier output using the final runtime contract.")
    parser.add_argument("--mode", choices=["auto", "heuristic", "artifact", "slm"], default="auto")
    parser.add_argument("--question", required=True)
    parser.add_argument("--age-band", default="9-10")
    parser.add_argument("--language", default="en")
    parser.add_argument("--recent-context", default="none")
    args = parser.parse_args()
    print(json.dumps(run_infer(args.mode, args.question, args.age_band, args.language, args.recent_context), indent=2))


if __name__ == "__main__":
    main()
