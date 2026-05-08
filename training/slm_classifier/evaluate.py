from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.guardrails import slm_classifier
from training.slm_classifier.artifact_backend import build_decision_from_artifact, load_artifact
from training.slm_classifier.data_pipeline import CANONICAL_DATASET, GL_COLUMNS
from training.slm_classifier.infer import _normalize_input


def _iter_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _metrics(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def evaluate_classifier(dataset_path: Path = CANONICAL_DATASET, mode: str = "heuristic") -> dict[str, object]:
    rows = _iter_rows(dataset_path)
    summary: dict[str, object] = {"dataset_rows": len(rows), "mode": mode, "labels": {}}
    artifact = load_artifact() if mode == "artifact" else None

    counts = {gl_column: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for gl_column in GL_COLUMNS}
    for row in rows:
        question = str(row["question"])
        age_band = str(row["age_band"])
        language = str(row.get("language", "en"))
        recent_context = str(row.get("recent_context", "none"))
        if mode == "artifact" and artifact is not None:
            decision = build_decision_from_artifact(
                question=question,
                age_band=age_band,
                language=language,
                recent_context=recent_context,
                artifact=artifact,
            )
        else:
            normalized = _normalize_input(
                question=question,
                age_band=age_band,
                language=language,
                recent_context=recent_context,
            )
            decision = slm_classifier.classify(normalized)
        predicted = set(decision.guideline_tags or decision.active_gls)
        for gl_column in GL_COLUMNS:
            gl_id = gl_column.upper().replace("_", "-")
            gold = int(row.get(gl_column, 0))
            pred = 1 if gl_id in predicted else 0
            if gold == 1 and pred == 1:
                counts[gl_column]["tp"] += 1
            elif gold == 0 and pred == 1:
                counts[gl_column]["fp"] += 1
            elif gold == 1 and pred == 0:
                counts[gl_column]["fn"] += 1
            else:
                counts[gl_column]["tn"] += 1

    for gl_column in GL_COLUMNS:
        gl_id = gl_column.upper().replace("_", "-")
        tp = counts[gl_column]["tp"]
        fp = counts[gl_column]["fp"]
        fn = counts[gl_column]["fn"]
        tn = counts[gl_column]["tn"]
        summary["labels"][gl_id] = {
            **_metrics(tp, fp, fn),
            "support": tp + fn,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the current runtime classifier against the canonical dataset.")
    parser.add_argument("--mode", choices=["heuristic", "artifact"], default="heuristic")
    parser.add_argument("--dataset", default=str(CANONICAL_DATASET))
    args = parser.parse_args()

    results = evaluate_classifier(dataset_path=Path(args.dataset), mode=args.mode)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
