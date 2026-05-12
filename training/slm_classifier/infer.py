from __future__ import annotations

import argparse
import json

from app.guardrails import prompt_contract, slm_classifier
from app.guardrails.gate_mapper import age_band_from_age, resolve_age_band
from app.models.child_profile import ChildProfile
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
    child_profile = ChildProfile(
        age=int(decision.input.get("age", 12) if isinstance(getattr(decision, "input", {}), dict) else 12),
        age_group=str(decision.input.get("age_band", age_band) if isinstance(getattr(decision, "input", {}), dict) else age_band),
        language=language,
    )
    prompt = prompt_contract.build(child_profile, question, decision, [])
    gates = decision.gates or decision.gate_values
    classifier_metadata = dict(decision.classifier_metadata or {})
    head_confidences = dict(classifier_metadata.get("head_confidences", {}))
    raw_g2_scores = head_confidences.get("G2", {})
    contract = dict(decision.prompt_contract or {})
    g2_scores = (
        [
            {"id": str(label), "score": float(score), "active": str(label) in set(gates.get("G2_all", []))}
            for label, score in sorted(raw_g2_scores.items(), key=lambda item: float(item[1]), reverse=True)
        ]
        if isinstance(raw_g2_scores, dict)
        else []
    )
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
        "reason": decision.reason,
        "active_gls": decision.active_gls or decision.guideline_tags,
        "gates": gates,
        "decision": decision.decision,
        "confidence": decision.confidence,
        "g2_scores": {
            "threshold": float(classifier_metadata.get("g2_threshold", 0.5)),
            "active_lovs": [item for item in g2_scores if item["active"]],
        },
        "policy": {
            "severity": str(gates.get("G3", "")),
            "modifiers": list(contract.get("modifiers", [])),
            "action": str(gates.get("G4", "")),
            "response_mode": str(decision.response_mode),
            "risk_level": str(decision.risk_level),
            "parent_visible": bool(decision.parent_visible),
        },
        "special_rules": {
            "template_id": contract.get("template_id", ""),
            "safety_envelope": contract.get("safety_envelope", {}),
            "checklist": contract.get("checklist", {}),
        },
        "prompt": prompt,
        "classifier": {
            "backend_version": classifier_metadata.get("backend_version"),
            "inference_device": classifier_metadata.get("inference_device"),
            "trained": classifier_metadata.get("trained"),
            "core_model": classifier_metadata.get("core_model", core),
        },
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
