from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.guardrails import slm_classifier
from training.slm_classifier.flag_logic import apply_flag_logic
from training.slm_classifier.runtime_config import load_classifier_runtime_config

DEFAULT_THRESHOLD = 0.8


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


def _classify(mode: str, normalized: dict[str, object], threshold: float):
    if mode == "slm":
        return slm_classifier.classify_slm(normalized, threshold=threshold)
    if mode == "artifact":
        return slm_classifier.classify_artifact(normalized)
    if mode == "auto":
        selected = load_classifier_runtime_config().selected_backend
        if selected == "slm":
            return slm_classifier.classify_slm(normalized, threshold=threshold)
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


def _filtered_scores(raw: object, threshold: float) -> dict[str, float]:
    return {
        label: score
        for label, score in _sorted_scores(raw).items()
        if score >= threshold
    }


def _g2_all_reason(
    g2_id: str,
    g2_all_scores: dict[str, float],
    g2_reasons: dict[str, str],
    threshold: float,
) -> str:
    if g2_id in g2_all_scores:
        return f"Selected by classifier head score above threshold ({g2_all_scores[g2_id]:.3f} >= {threshold:.3f})."
    return str(g2_reasons.get(g2_id, ""))


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


def run_infer(
    mode: str,
    question: str,
    age_band: str,
    language: str,
    recent_context: str,
    threshold: float | None = None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, object]:
    effective_threshold = _resolve_threshold(threshold, thresholds)
    normalized = _normalize_input(question, age_band, language, recent_context)
    decision = _classify(mode, normalized, effective_threshold)
    gates = decision.gates or decision.gate_values
    classifier_metadata = dict(decision.classifier_metadata or {})
    head_confidences = dict(classifier_metadata.get("head_confidences", {}))
    topic_scores = _filtered_scores(head_confidences.get("topic", {}), effective_threshold)
    g2_primary_scores = _filtered_scores(head_confidences.get("G2_primary", {}), effective_threshold)
    g2_all_scores = _filtered_scores(head_confidences.get("G2_all", {}), effective_threshold)
    primary_g2 = str(gates.get("G2", "GENERIC_INTENT"))
    g2_all = [label for label, score in g2_all_scores.items() if score >= effective_threshold]
    g2_reasons = dict(getattr(decision, "g2_reasons", {}) or {})
    if primary_g2 and primary_g2 not in g2_all:
        g2_all.insert(0, primary_g2)
    topic_id = str(gates.get("topic") or decision.signals.get("topic") or "General Learning")
    result = {
        "question": question,
        "context": recent_context,
        "language": language,
        "topic": {
            "id": topic_id,
            "scores": topic_scores,
        },
        "g1": {
            "id": str(gates.get("G1", "GENERIC")),
            "reason": str(getattr(decision, "g1_reason", "") or ""),
        },
        "g2": {
            "id": primary_g2,
            "scores": g2_primary_scores,
            "reason": str(g2_reasons.get(primary_g2, "")),
        },
        "g2_all": {
            "ids": g2_all,
            "scores": g2_all_scores,
            "reasons": {
                g2_id: _g2_all_reason(g2_id, g2_all_scores, g2_reasons, effective_threshold)
                for g2_id in g2_all
            },
        },
        "backend": mode if mode != "auto" else load_classifier_runtime_config().selected_backend,
        "trained": bool(classifier_metadata.get("trained", False)),
        "threshold": effective_threshold,
    }
    if thresholds is not None:
        result["thresholds"] = thresholds
    return apply_flag_logic(result, classifier_metadata)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print pure classifier output.")
    parser.add_argument("--mode", choices=["auto", "heuristic", "artifact", "slm"], default="auto")
    parser.add_argument("--question", required=True)
    parser.add_argument("--age-band", default="9-10")
    parser.add_argument("--language", default="en")
    parser.add_argument("--recent-context", default="none")
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--thresholds", default=None, help="JSON object of thresholds. Uses threshold/default/global when present.")
    args = parser.parse_args()
    print(
        json.dumps(
            run_infer(
                args.mode,
                args.question,
                args.age_band,
                args.language,
                args.recent_context,
                threshold=args.threshold,
                thresholds=_parse_thresholds(args.thresholds),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
