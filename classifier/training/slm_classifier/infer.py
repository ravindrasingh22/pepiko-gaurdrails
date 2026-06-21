from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.guardrails import slm_classifier
from app.guardrails.normalizer import canonicalize_classifier_text
from training.slm_classifier.runtime_config import load_classifier_runtime_config
from training.slm_classifier.slm_backend import available_cores

DEFAULT_THRESHOLD = 0.8


def _normalize_input(question: str, age_band: str, language: str, context: str) -> dict[str, object]:
    return {
        "text": canonicalize_classifier_text(question),
        "recent_context": [] if context == "none" else [context],
        "language": language,
        "child_profile": {
            "age": 12,
            "age_group": age_band,
            "language": language,
        },
        "resolved_age_band": age_band,
    }


def _backend_for_auto_mode() -> str:
    return load_classifier_runtime_config().selected_backend


def _classify(mode: str, normalized: dict[str, object], threshold: float, core: str | None = None):
    if mode == "slm":
        return slm_classifier.classify_slm(normalized, core=core, threshold=threshold)
    if mode == "artifact":
        return slm_classifier.classify_artifact(normalized)
    if mode == "auto":
        selected = _backend_for_auto_mode()
        if selected == "slm":
            return slm_classifier.classify_slm(normalized, core=core, threshold=threshold)
        if selected == "artifact":
            return slm_classifier.classify_artifact(normalized)
        return slm_classifier.classify_heuristic(normalized)
    return slm_classifier.classify_heuristic(normalized)


def _sorted_scores(raw: object) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    return {
        str(label): float(score)
        for label, score in sorted(raw.items(), key=lambda item: float(item[1]), reverse=True)
    }


def _flag_scores(raw: object) -> dict[str, float]:
    return _sorted_scores(raw)


def _parse_thresholds(thresholds: str | None) -> dict[str, float] | None:
    if thresholds is None:
        return None
    raw = json.loads(thresholds)
    if not isinstance(raw, dict):
        raise ValueError("thresholds must be a JSON object")
    parsed: dict[str, float] = {}
    for key, value in raw.items():
        parsed[str(key)] = float(value)
    return parsed


def _resolve_threshold(threshold: float | None, thresholds: dict[str, float] | None) -> float:
    if threshold is not None:
        return threshold
    if not thresholds:
        return DEFAULT_THRESHOLD
    for key in ("threshold", "default", "global"):
        if key in thresholds:
            return float(thresholds[key])
    return float(next(iter(thresholds.values())))


def _build_question_grounded_g2_reason(*, question: str, g1_id: str, g2_id: str) -> str:
    if not g2_id:
        return ""
    semantic = slm_classifier.build_g2_reasons(g1_id, [g2_id], question, None).get(g2_id, "").strip()
    if semantic:
        return semantic
    return f"The question content is most consistent with the {g2_id} label."


def run_infer(
    mode: str,
    question: str,
    age_band: str,
    language: str,
    context: str,
    core: str | None = None,
    threshold: float | None = None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, object]:
    effective_threshold = _resolve_threshold(threshold, thresholds)
    normalized = _normalize_input(question, age_band, language, context)
    decision = _classify(mode, normalized, effective_threshold, core=core)
    gates = decision.gates or decision.gate_values
    classifier_metadata = dict(decision.classifier_metadata or {})
    head_confidences = dict(classifier_metadata.get("head_confidences", {}))
    learned_intent = dict(head_confidences.get("intent_lexicon_learned", {}))
    g2_primary_scores = _sorted_scores(head_confidences.get("G2_primary", {}))
    primary_g2 = str(gates.get("G2", "GENERIC_INTENT"))
    g2_reasons = dict(getattr(decision, "g2_reasons", {}) or {})
    result = {
        "question": question,
        "user_input": question,
        "context": context,
        "language": language,
        "g1": {
            "id": str(gates.get("G1", "GENERIC")),
            "reason": str(getattr(decision, "g1_reason", "") or ""),
        },
        "g2": {
            "id": primary_g2,
            "scores": g2_primary_scores,
            "reason": str(g2_reasons.get(primary_g2, "")),
        },
        "backend": mode if mode != "auto" else _backend_for_auto_mode(),
        "core_model": str(classifier_metadata.get("core_model", core or "")),
        "trained": bool(classifier_metadata.get("trained", False)),
        "threshold": effective_threshold,
        "flags": _flag_scores(head_confidences.get("flags", {})),
        "intent_families": {
            "active": [str(item) for item in learned_intent.get("predicted_intent_families", []) if str(item).strip()],
            # "scores": _sorted_scores(head_confidences.get("intent_families", {})),
        },
        "intent_phrases": {
            "active": [str(item) for item in learned_intent.get("predicted_phrases", []) if str(item).strip()],
            # "scores": _sorted_scores(learned_intent.get("phrase_scores", {})),
        },
    }
    if thresholds is not None:
        result["thresholds"] = thresholds
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Print classifier output.")
    parser.add_argument("--mode", choices=["auto", "heuristic", "artifact", "slm"], default="auto")
    parser.add_argument("--core", choices=available_cores(), default=None)
    parser.add_argument("--question", default=None)
    parser.add_argument("--user-input", dest="user_input", default=None)
    parser.add_argument("--input-text", dest="input_text", default=None)
    parser.add_argument("--context", default="none")
    parser.add_argument("--age-band", default="9-10")
    parser.add_argument("--language", default="en")
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--thresholds", default=None, help="JSON object of thresholds. Uses threshold/default/global when present.")
    args = parser.parse_args()
    question = args.question or args.user_input or args.input_text
    if not question:
        parser.error("one of --question, --user-input, or --input-text is required")
    print(
        json.dumps(
            run_infer(
                args.mode,
                question,
                args.age_band,
                args.language,
                args.context,
                core=args.core,
                threshold=args.threshold,
                thresholds=_parse_thresholds(args.thresholds),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
