from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from app.guardrails import slm_classifier
from training.slm_classifier.artifact_backend import build_decision_from_artifact, load_artifact
from training.slm_classifier.data_pipeline import CANONICAL_DATASET, GL_COLUMNS, load_dataset_splits, parse_g2_values, select_rows_for_split
from training.slm_classifier.infer import _normalize_input
from training.slm_classifier.slm_backend import build_decision_from_slm, resolve_core
from training.slm_classifier.source_normalizer import write_canonical_jsonl_with_metadata


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


def _accuracy(correct: int, total: int) -> float:
    return correct / total if total else 0.0


def _macro_average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def evaluate_classifier(
    dataset_path: Path = CANONICAL_DATASET,
    mode: str = "heuristic",
    max_rows: int | None = None,
    split: str = "test",
    core: str = "smol",
) -> dict[str, object]:
    if not dataset_path.exists():
        write_canonical_jsonl_with_metadata(target_path=dataset_path)
    rows = _iter_rows(dataset_path)
    if dataset_path == CANONICAL_DATASET:
        split_rows = select_rows_for_split(rows, split, load_dataset_splits())
        if split_rows:
            rows = split_rows
    if max_rows is not None and max_rows > 0:
        rows = rows[:max_rows]
    summary: dict[str, object] = {
        "dataset_rows": len(rows),
        "mode": mode,
        "split": split,
        "core_model": core if mode == "slm" else None,
        "labels": {},
        "gate_metrics": {},
        "confusion": {"G1": collections.Counter(), "G2": collections.Counter()},
        "slices": {},
    }
    artifact = load_artifact() if mode == "artifact" else None

    counts = {gl_column: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for gl_column in GL_COLUMNS}
    gate_correct = {"G1": 0, "G2": 0, "exact_match": 0}
    gate_total = len(rows)
    slice_totals: dict[str, dict[str, int]] = {
        "dangerous_violence": {"rows": 0, "correct_g2": 0},
        "civic_law_integrity": {"rows": 0, "correct_g2": 0},
        "technology": {"rows": 0, "correct_g2": 0},
        "safety_hazard": {"rows": 0, "correct_g2": 0},
        "grief_emotional": {"rows": 0, "correct_g2": 0},
        "grooming_unsafe_content": {"rows": 0, "correct_g2": 0},
    }
    for row in rows:
        question = str(row["question"])
        language = str(row.get("language", "en"))
        recent_context = str(row.get("recent_context", "none"))
        if mode == "artifact" and artifact is not None:
            decision = build_decision_from_artifact(
                question=question,
                age_band="11-12",
                language=language,
                recent_context=recent_context,
                artifact=artifact,
            )
        elif mode == "slm":
            decision = build_decision_from_slm(
                normalized=_normalize_input(
                    question=question,
                    age_band="11-12",
                    language=language,
                    recent_context=recent_context,
                ),
                core=core,
            )
        else:
            normalized = _normalize_input(
                question=question,
                age_band="11-12",
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

        predicted_gates = decision.gates or decision.gate_values
        gold_gates = {
            "G1": str(row["g1"]),
            "G2": str(row["g2"]),
            "G2_all": parse_g2_values(row.get("g2_all", row.get("g2", ""))),
        }
        predicted_g1 = str(predicted_gates.get("G1", ""))
        predicted_g2 = str(predicted_gates.get("G2", ""))
        predicted_g2_all = parse_g2_values(predicted_gates.get("G2_all", predicted_g2))
        if predicted_g1 == gold_gates["G1"]:
            gate_correct["G1"] += 1
        if set(predicted_g2_all) == set(gold_gates["G2_all"]):
            gate_correct["G2"] += 1
        if all(
            (
                predicted_g1 == gold_gates["G1"],
                set(predicted_g2_all) == set(gold_gates["G2_all"]),
            )
        ):
            gate_correct["exact_match"] += 1
        summary["confusion"]["G1"][f"{gold_gates['G1']}->{predicted_g1}"] += 1
        summary["confusion"]["G2"][f"{';'.join(gold_gates['G2_all'])}->{';'.join(predicted_g2_all)}"] += 1

        gold_g2_set = set(gold_gates["G2_all"])
        slice_names: list[str] = []
        if "DANGEROUS" in gold_g2_set or gold_gates["G1"] == "VIOLENCE":
            slice_names.append("dangerous_violence")
        if gold_gates["G1"] == "CIVIC_LAW":
            slice_names.append("civic_law_integrity")
        if gold_gates["G1"] == "TECHNOLOGY":
            slice_names.append("technology")
        if gold_gates["G1"] == "SAFETY_HAZARD":
            slice_names.append("safety_hazard")
        if gold_gates["G1"] == "DEATH_GRIEF" or "EMOTIONAL" in gold_g2_set:
            slice_names.append("grief_emotional")
        if gold_g2_set.intersection({"GROOMING", "UNSAFE_CONTENT"}):
            slice_names.append("grooming_unsafe_content")
        for slice_name in slice_names:
            slice_totals[slice_name]["rows"] += 1
            if set(predicted_g2_all) == gold_g2_set:
                slice_totals[slice_name]["correct_g2"] += 1

    gl_f1s: list[float] = []
    micro_tp = micro_fp = micro_fn = 0
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
        gl_f1s.append(float(summary["labels"][gl_id]["f1"]))
        micro_tp += tp
        micro_fp += fp
        micro_fn += fn
    summary["gl_summary"] = {
        "macro_f1": _macro_average(gl_f1s),
        "micro_f1": _metrics(micro_tp, micro_fp, micro_fn)["f1"],
    }
    summary["gate_metrics"] = {
        "G1_accuracy": _accuracy(gate_correct["G1"], gate_total),
        "G2_accuracy": _accuracy(gate_correct["G2"], gate_total),
        "gate_exact_match": _accuracy(gate_correct["exact_match"], gate_total),
    }
    summary["confusion"] = {
        key: dict(value)
        for key, value in summary["confusion"].items()
    }
    summary["slices"] = {
        key: {
            "rows": value["rows"],
            "g2_accuracy": _accuracy(value["correct_g2"], value["rows"]),
        }
        for key, value in slice_totals.items()
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the current runtime classifier against the canonical dataset.")
    parser.add_argument("--mode", choices=["slm", "heuristic", "artifact"], default="slm")
    parser.add_argument("--dataset", default=str(CANONICAL_DATASET))
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--split", choices=["train", "dev", "test"], default="test")
    parser.add_argument("--core", choices=["smol", "deberta"], default="smol")
    args = parser.parse_args()

    max_rows = args.max_rows if args.max_rows > 0 else None
    core = resolve_core(args.core)
    results = evaluate_classifier(dataset_path=Path(args.dataset), mode=args.mode, max_rows=max_rows, split=args.split, core=core)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
