from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path

from app.guardrails import slm_classifier
from training.slm_classifier.artifact_backend import build_decision_from_artifact, load_artifact
from training.slm_classifier.data_pipeline import (
    CANONICAL_DATASET,
    G2_VOCAB,
    load_dataset_splits,
    parse_g2_values,
    primary_g2_label,
    select_rows_for_split,
)
from training.slm_classifier.infer import _normalize_input
from training.slm_classifier.slm_backend import available_cores, build_decision_from_slm, resolve_core
from training.slm_classifier.source_normalizer import write_canonical_jsonl_with_metadata


def _iter_rows(path: Path) -> list[dict[str, object]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [{str(key): value for key, value in row.items()} for row in reader]
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _expected_g1(row: dict[str, object]) -> str:
    return str(row.get("g1", row.get("expected_g1", "")))


def _expected_g2(row: dict[str, object]) -> str:
    raw_value = str(row.get("g2", row.get("expected_g2", ""))).replace(";", ",")
    return primary_g2_label(raw_value)


def _metrics(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _accuracy(correct: int, total: int) -> float:
    return correct / total if total else 0.0


def _macro_average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _print_row_header() -> None:
    print("row_index\tsample_id\tgold_g1\tpred_g1\tgold_g2\tpred_g2\tmatch\tquestion")


def _print_row_result(
    row_index: int,
    row: dict[str, object],
    *,
    gold_g1: str,
    predicted_g1: str,
    gold_g2: str,
    predicted_g2: str,
) -> None:
    question = str(row.get("question", "")).replace("\t", " ").replace("\n", " ").strip()
    sample_id = str(row.get("sample_id", "")).replace("\t", " ").replace("\n", " ").strip()
    match = "yes" if gold_g1 == predicted_g1 and gold_g2 == predicted_g2 else "no"
    print(
        f"{row_index}\t{sample_id}\t{gold_g1}\t{predicted_g1}\t{gold_g2}\t{predicted_g2}\t{match}\t{question}"
    )


def _write_row_results_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "row_index",
        "sample_id",
        "question",
        "language",
        "recent_context",
        "g1",
        "pred_g1",
        "g2",
        "pred_g2",
        "g1_match",
        "g2_match",
        "exact_match",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def evaluate_classifier(
    dataset_path: Path = CANONICAL_DATASET,
    mode: str = "heuristic",
    max_rows: int | None = None,
    split: str = "test",
    core: str = "smol",
    print_rows: bool = False,
    output_csv: Path | None = None,
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
        "gate_metrics": {},
        "g2_metrics": {"per_label": {}, "macro_f1": 0.0, "weighted_f1": 0.0},
        "confusion": {"G1": collections.Counter(), "G2": collections.Counter()},
        "slices": {},
    }
    row_results: list[dict[str, object]] = []
    artifact = load_artifact() if mode == "artifact" else None
    gate_correct = {"G1": 0, "G2": 0, "exact_match": 0}
    gate_total = len(rows)
    g2_counts = {
        label: {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        for label in G2_VOCAB
    }
    slice_totals: dict[str, dict[str, int]] = {
        "dangerous_violence": {"rows": 0, "correct_g2": 0},
        "civic_law_integrity": {"rows": 0, "correct_g2": 0},
        "technology": {"rows": 0, "correct_g2": 0},
        "safety_hazard": {"rows": 0, "correct_g2": 0},
        "grief_emotional": {"rows": 0, "correct_g2": 0},
        "grooming_unsafe_content": {"rows": 0, "correct_g2": 0},
    }
    for label in G2_VOCAB:
        slice_totals[f"g2_{label.lower()}"] = {"rows": 0, "correct_g2": 0}
    header_printed = False
    for row_index, row in enumerate(rows, start=1):
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
        predicted_gates = decision.gates or decision.gate_values
        gold_gates = {
            "G1": _expected_g1(row),
            "G2": _expected_g2(row),
        }
        predicted_g1 = str(predicted_gates.get("G1", ""))
        predicted_g2 = str(predicted_gates.get("G2", ""))
        g1_match = predicted_g1 == gold_gates["G1"]
        g2_match = predicted_g2 == gold_gates["G2"]
        exact_match = g1_match and g2_match
        row_results.append(
            {
                "row_index": row_index,
                "sample_id": str(row.get("sample_id", "")),
                "question": question,
                "language": language,
                "recent_context": recent_context,
                "g1": gold_gates["G1"],
                "pred_g1": predicted_g1,
                "g2": gold_gates["G2"],
                "pred_g2": predicted_g2,
                "g1_match": g1_match,
                "g2_match": g2_match,
                "exact_match": exact_match,
            }
        )
        if print_rows:
            if not header_printed:
                _print_row_header()
                header_printed = True
            _print_row_result(
                row_index,
                row,
                gold_g1=gold_gates["G1"],
                predicted_g1=predicted_g1,
                gold_g2=gold_gates["G2"],
                predicted_g2=predicted_g2,
            )
        if g1_match:
            gate_correct["G1"] += 1
        if g2_match:
            gate_correct["G2"] += 1
        if exact_match:
            gate_correct["exact_match"] += 1
        for label in G2_VOCAB:
            gold = gold_gates["G2"] == label
            pred = predicted_g2 == label
            if gold and pred:
                g2_counts[label]["tp"] += 1
            elif (not gold) and pred:
                g2_counts[label]["fp"] += 1
            elif gold and (not pred):
                g2_counts[label]["fn"] += 1
            else:
                g2_counts[label]["tn"] += 1
        summary["confusion"]["G1"][f"{gold_gates['G1']}->{predicted_g1}"] += 1
        summary["confusion"]["G2"][f"{gold_gates['G2']}->{predicted_g2}"] += 1

        slice_names: list[str] = []
        if gold_gates["G2"] == "DANGEROUS" or gold_gates["G1"] == "VIOLENCE":
            slice_names.append("dangerous_violence")
        if gold_gates["G1"] == "CIVIC_LAW":
            slice_names.append("civic_law_integrity")
        if gold_gates["G1"] == "TECHNOLOGY":
            slice_names.append("technology")
        if gold_gates["G1"] == "SAFETY_HAZARD":
            slice_names.append("safety_hazard")
        if gold_gates["G1"] == "DEATH_GRIEF" or gold_gates["G2"] == "EMOTIONAL":
            slice_names.append("grief_emotional")
        if gold_gates["G2"] in {"GROOMING", "UNSAFE_SEXUAL_CONTENT"}:
            slice_names.append("grooming_unsafe_content")
        for slice_name in slice_names:
            slice_totals[slice_name]["rows"] += 1
            if predicted_g2 == gold_gates["G2"]:
                slice_totals[slice_name]["correct_g2"] += 1
        label_slice_name = f"g2_{gold_gates['G2'].lower()}"
        slice_totals[label_slice_name]["rows"] += 1
        if predicted_g2 == gold_gates["G2"]:
            slice_totals[label_slice_name]["correct_g2"] += 1

    summary["gate_metrics"] = {
        "G1_accuracy": _accuracy(gate_correct["G1"], gate_total),
        "G2_accuracy": _accuracy(gate_correct["G2"], gate_total),
        "gate_exact_match": _accuracy(gate_correct["exact_match"], gate_total),
    }
    g2_f1s: list[float] = []
    weighted_f1_numerator = 0.0
    weighted_support = 0
    for label in G2_VOCAB:
        tp = g2_counts[label]["tp"]
        fp = g2_counts[label]["fp"]
        fn = g2_counts[label]["fn"]
        tn = g2_counts[label]["tn"]
        metrics = {
            **_metrics(tp, fp, fn),
            "support": tp + fn,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
        }
        summary["g2_metrics"]["per_label"][label] = metrics
        g2_f1s.append(float(metrics["f1"]))
        weighted_f1_numerator += float(metrics["f1"]) * int(metrics["support"])
        weighted_support += int(metrics["support"])
    summary["g2_metrics"]["macro_f1"] = _macro_average(g2_f1s)
    summary["g2_metrics"]["weighted_f1"] = (
        weighted_f1_numerator / weighted_support if weighted_support else 0.0
    )
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
    if output_csv is not None:
        _write_row_results_csv(output_csv, row_results)
        summary["output_csv"] = str(output_csv)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the current runtime classifier against the canonical dataset.")
    parser.add_argument("--mode", choices=["slm", "heuristic", "artifact"], default="slm")
    parser.add_argument("--dataset", default=str(CANONICAL_DATASET))
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--split", choices=["train", "dev", "test"], default="test")
    parser.add_argument("--core", choices=available_cores(), default="smol")
    parser.add_argument("--print-rows", action="store_true", help="Print one TSV row per evaluated sample with a single header row.")
    parser.add_argument("--output-csv", default="", help="Write per-row evaluation results to this CSV path.")
    args = parser.parse_args()

    max_rows = args.max_rows if args.max_rows > 0 else None
    core = resolve_core(args.core)
    results = evaluate_classifier(
        dataset_path=Path(args.dataset),
        mode=args.mode,
        max_rows=max_rows,
        split=args.split,
        core=core,
        print_rows=args.print_rows,
        output_csv=Path(args.output_csv) if args.output_csv else None,
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
