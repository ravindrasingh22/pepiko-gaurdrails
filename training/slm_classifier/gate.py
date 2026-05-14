from __future__ import annotations

import argparse
import json

from app.guardrails import slm_classifier
from app.guardrails.runtime_contracts import classifier_output_from_decision, gate_output_from_classifier
from app.models.child_profile import ChildProfile
from training.slm_classifier.infer import _classify, _normalize_input


def run_gate(mode: str, question: str, age_band: str, language: str, recent_context: str) -> dict[str, object]:
    normalized = _normalize_input(question, age_band, language, recent_context)
    decision = _classify(mode, normalized)
    profile = ChildProfile(age=int(normalized["child_profile"]["age"]), age_group=age_band, language=language)
    classifier_output = classifier_output_from_decision(question, profile, decision)
    gate_output = gate_output_from_classifier(classifier_output)
    return {
        "classifier_output": classifier_output,
        "gate_output": gate_output,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Print classifier plus gate-engine output using the final runtime contract.")
    parser.add_argument("--mode", choices=["auto", "heuristic", "artifact", "slm"], default="auto")
    parser.add_argument("--question", required=True)
    parser.add_argument("--age-band", default="9-10")
    parser.add_argument("--language", default="en")
    parser.add_argument("--recent-context", default="none")
    args = parser.parse_args()
    print(json.dumps(run_gate(args.mode, args.question, args.age_band, args.language, args.recent_context), indent=2))


if __name__ == "__main__":
    main()
