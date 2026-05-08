from __future__ import annotations

import argparse

from app.guardrails import prompt_contract, slm_classifier
from app.models.child_profile import ChildProfile

from training.slm_classifier.infer import _normalize_input


def _final_prompt(mode: str, question: str, age_band: str, language: str, recent_context: str) -> str:
    normalized = _normalize_input(question, age_band, language, recent_context)
    decision = slm_classifier.classify(normalized)
    profile = ChildProfile(
        age=int(normalized["child_profile"]["age"]),
        age_group=age_band,
        language=language,
    )
    return prompt_contract.build(profile, question, decision, [])


def main() -> None:
    parser = argparse.ArgumentParser(description="Print the final assembled child-facing prompt.")
    parser.add_argument("--mode", choices=["artifact", "heuristic"], default="artifact")
    parser.add_argument("--question", required=True)
    parser.add_argument("--age-band", default="9-12")
    parser.add_argument("--language", default="en")
    parser.add_argument("--recent-context", default="none")
    args = parser.parse_args()

    print(
        _final_prompt(
            mode=args.mode,
            question=args.question,
            age_band=args.age_band,
            language=args.language,
            recent_context=args.recent_context,
        )
    )


if __name__ == "__main__":
    main()
