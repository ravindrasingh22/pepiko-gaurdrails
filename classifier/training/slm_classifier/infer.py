from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.guardrails import slm_classifier
from training.slm_classifier.runtime_config import load_classifier_runtime_config
from training.slm_classifier.slm_backend import available_cores

DEFAULT_THRESHOLD = 0.8
AGE_LOOKUP = {
    "5-6": 6,
    "7-8": 8,
    "9-10": 10,
    "11-12": 12,
    "13-14": 14,
    "15-16": 16,
    "17": 17,
}


def _normalize_input(question: str, age_band: str, language: str, context: str) -> dict[str, object]:
    age = AGE_LOOKUP.get(age_band, 12)
    return {
        "text": question,
        "recent_context": [] if context == "none" else [context],
        "child_profile": {
            "age": age,
            "age_group": age_band,
            "language": language,
        },
        "resolved_age_band": age_band,
    }


def _backend_for_auto_mode() -> str:
    return load_classifier_runtime_config().selected_backend


def _classify(mode: str, normalized: dict[str, object], threshold: float, core: str | None = None):
    if mode == "slm_pure":
        return slm_classifier.classify_slm_pure(normalized, core=core, threshold=threshold)
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


def _normalize_g2_values(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    if isinstance(raw, str):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return []


def _g2_selection_reasons(
    *,
    question: str,
    context: str,
    head_confidences: dict[str, object],
    g2_all: list[str],
    threshold: float,
    g2_reasons: dict[str, str],
) -> dict[str, list[str]]:
    g2_primary_scores = _sorted_scores(head_confidences.get("G2_primary", {}))
    if g2_primary_scores:
        primary_label = max(g2_primary_scores, key=g2_primary_scores.get)
    else:
        primary_label = "GENERIC_INTENT"
    model_threshold_labels = {
        label for label, score in g2_primary_scores.items()
        if float(score) >= threshold
    }
    normalized_question = slm_classifier.normalize(question)
    normalized_context = slm_classifier.normalize("" if context == "none" else context)
    heuristic_labels = set(slm_classifier.classify_g2(normalized_question, normalized_context))
    lexicon = dict(head_confidences.get("intent_lexicon", {}))
    lexicon_labels = {str(item) for item in lexicon.get("matched_lovs", []) if str(item).strip()}

    selection_reasons: dict[str, list[str]] = {}
    for label in g2_all:
        reasons: list[str] = []
        if label in model_threshold_labels:
            reasons.append(f"source=model_threshold score={g2_primary_scores[label]:.3f} threshold={threshold:.3f}")
        elif label == primary_label:
            reasons.append(f"source=primary_fallback score={g2_primary_scores.get(label, 0.0):.3f} threshold={threshold:.3f}")
        if label in heuristic_labels and label not in model_threshold_labels:
            reasons.append("source=heuristic_fusion")
        if label in lexicon_labels:
            reasons.append("source=lexicon_fusion")
        if not reasons:
            reasons.append("source=final_g2_list")
        explanation = str(g2_reasons.get(label, "")).strip()
        if explanation:
            reasons.append(explanation)
        selection_reasons[label] = reasons
    return selection_reasons


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


def _build_pure_g2_reason(
    *,
    g2_id: str,
    g2_scores: dict[str, float],
    flag_scores: dict[str, float],
    threshold: float,
) -> str:
    if not g2_id:
        return ""
    ordered_g2 = sorted(g2_scores.items(), key=lambda item: float(item[1]), reverse=True)
    top_score = float(g2_scores.get(g2_id, 0.0))
    second_score = float(ordered_g2[1][1]) if len(ordered_g2) > 1 else 0.0
    margin = top_score - second_score
    active_flags = [
        label for label, score in sorted(flag_scores.items(), key=lambda item: float(item[1]), reverse=True)
        if float(score) >= threshold
    ][:3]
    reason = f"Selected {g2_id} from the highest G2 head score ({top_score:.3f})"
    reason += f" with margin {margin:.3f} over the next label."
    if active_flags:
        reason += f" Supporting flags above threshold: {', '.join(active_flags)}."
    return reason


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
    if mode == "slm_pure":
        classifier_metadata = dict(decision.classifier_metadata or {})
        head_confidences = dict(classifier_metadata.get("head_confidences", {}))
        flag_scores = _sorted_scores(head_confidences.get("flags", {}))
        active_flags = [
            label for label, score in flag_scores.items()
            if float(score) >= effective_threshold
        ]
        result = {
            "question": question,
            "context": context,
            "language": language,
            "backend": "slm_pure",
            "core_model": str(classifier_metadata.get("core_model", core or "")),
            "trained": bool(classifier_metadata.get("trained", False)),
            "threshold": effective_threshold,
            "g1": {
                "id": str((decision.gates or decision.gate_values).get("G1", "")),
                "scores": _sorted_scores(head_confidences.get("G1", {})),
            },
            "g2": {
                "id": str((decision.gates or decision.gate_values).get("G2", "")),
                "scores": _sorted_scores(head_confidences.get("G2", {})),
                "reason": _build_question_grounded_g2_reason(
                    question=question,
                    g1_id=str((decision.gates or decision.gate_values).get("G1", "")),
                    g2_id=str((decision.gates or decision.gate_values).get("G2", "")),
                ),
                "decision_basis": _build_pure_g2_reason(
                    g2_id=str((decision.gates or decision.gate_values).get("G2", "")),
                    g2_scores=_sorted_scores(head_confidences.get("G2", {})),
                    flag_scores=flag_scores,
                    threshold=effective_threshold,
                ),
            },
            "flags": {
                "active": active_flags,
                "scores": flag_scores,
            },
        }
        if thresholds is not None:
            result["thresholds"] = thresholds
        return result
    gates = decision.gates or decision.gate_values
    classifier_metadata = dict(decision.classifier_metadata or {})
    head_confidences = dict(classifier_metadata.get("head_confidences", {}))
    learned_intent = dict(head_confidences.get("intent_lexicon_learned", {}))
    g2_primary_scores = _sorted_scores(head_confidences.get("G2_primary", {}))
    g2_all_scores = _sorted_scores(head_confidences.get("G2_all", {}))
    primary_g2 = str(gates.get("G2", "GENERIC_INTENT"))
    g2_all = _normalize_g2_values(gates.get("G2_all", []))
    g2_reasons = dict(getattr(decision, "g2_reasons", {}) or {})
    result = {
        "question": question,
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
        "g2_all": {
            "ids": g2_all,
            "scores": g2_all_scores,
            "selection_reasons": _g2_selection_reasons(
                question=question,
                context=context,
                head_confidences=head_confidences,
                g2_all=g2_all,
                threshold=effective_threshold,
                g2_reasons=g2_reasons,
            ),
        },
        "backend": mode if mode != "auto" else _backend_for_auto_mode(),
        "core_model": str(classifier_metadata.get("core_model", core or "")),
        "trained": bool(classifier_metadata.get("trained", False)),
        "threshold": effective_threshold,
        "flags": _flag_scores(head_confidences.get("flags", {})),
        "predicted_families": [str(item) for item in learned_intent.get("predicted_families", []) if str(item).strip()],
        "predicted_phrases": [str(item) for item in learned_intent.get("predicted_phrases", []) if str(item).strip()],
    }
    if thresholds is not None:
        result["thresholds"] = thresholds
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Print pure classifier output.")
    parser.add_argument("--mode", choices=["auto", "heuristic", "artifact", "slm", "slm_pure"], default="auto")
    parser.add_argument("--core", choices=available_cores(), default=None)
    parser.add_argument("--question", required=True)
    parser.add_argument("--context", default="none")
    parser.add_argument("--age-band", default="9-10")
    parser.add_argument("--language", default="en")
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
