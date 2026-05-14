from __future__ import annotations

import argparse
import json

from app.guardrails import prompt_contract
from app.guardrails.runtime_contracts import prompt_contract_payload
from app.models.child_profile import ChildProfile
from training.slm_classifier.infer import _classify, _normalize_input


def run_prompt_contract(mode: str, question: str, age_band: str, language: str, recent_context: str) -> dict[str, object]:
    normalized = _normalize_input(question, age_band, language, recent_context)
    decision = _classify(mode, normalized)
    profile = ChildProfile(age=int(normalized["child_profile"]["age"]), age_group=age_band, language=language)
    final_prompt = prompt_contract.build(profile, question, decision, [])
    payload = dict(decision.prompt_contract.get("prompt_contract_payload", {}))
    if not payload:
        payload = prompt_contract_payload(
            question=question,
            child_profile=profile,
            decision=decision,
            final_prompt=final_prompt,
            template_id=str(decision.prompt_contract.get("template_id", "")),
        )
    payload["final_prompt"] = final_prompt
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Print full prompt-contract JSON using the final runtime contract.")
    parser.add_argument("--mode", choices=["auto", "heuristic", "artifact", "slm"], default="auto")
    parser.add_argument("--question", required=True)
    parser.add_argument("--age-band", default="9-10")
    parser.add_argument("--language", default="en")
    parser.add_argument("--recent-context", default="none")
    args = parser.parse_args()
    print(json.dumps(run_prompt_contract(args.mode, args.question, args.age_band, args.language, args.recent_context), indent=2))


if __name__ == "__main__":
    main()
