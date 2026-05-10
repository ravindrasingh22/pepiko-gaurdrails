import csv
from pathlib import Path

from training.slm_classifier.source_normalizer import CANONICAL_COLUMNS, discover_source_files, expand_authoring_rows, write_normalized_csv


def _write_current_authoring_sheet(path: Path) -> None:
    rows = [
        ["Topic", "Question", "GL", "G1", "G2", "G3", "G4", "Generated Prompt"],
        ["School", "Should I tell my sports teacher that I did not finish library book?", "GL-01, GL-03", "GENERIC", "PD", "SV2 | none", "TRANSFORM", "prompt"],
        ["School", "How does unit test help me learn?", "", "FACT", "NEUTRAL_FACT", "SV0", "ALLOW", "prompt"],
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def test_source_normalizer_expands_authoring_sheet_into_canonical_rows(tmp_path: Path) -> None:
    source_path = tmp_path / "school-learning.csv"
    _write_current_authoring_sheet(source_path)
    rows = expand_authoring_rows(source_path)

    assert rows
    assert set(CANONICAL_COLUMNS).issubset(rows[0].keys())
    assert rows[0]["age_band"] == "5-6"
    assert rows[1]["age_band"] == "7-8"
    assert rows[2]["age_band"] == "9-10"
    assert rows[0]["reference_answer"] == ""
    assert rows[0]["gl_01"] == 1


def test_source_normalizer_infers_missing_guideline_tags_from_gates(tmp_path: Path) -> None:
    source_path = tmp_path / "school-learning.csv"
    _write_current_authoring_sheet(source_path)
    rows = expand_authoring_rows(source_path)

    inferred_rows = [row for row in rows if row["question"] == "How does unit test help me learn?"]
    assert inferred_rows
    assert all(row["guideline_tags"] for row in inferred_rows)
    assert all(row["gl_01"] == 1 for row in inferred_rows)
    assert all(row["gl_09"] == 0 for row in inferred_rows)


def test_source_discovery_skips_codebook_csv_and_picks_training_sheet(tmp_path: Path, monkeypatch) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_current_authoring_sheet(raw_dir / "Topics, Rules & Questions - School Learning.csv")
    (raw_dir / "GL-codebook.csv").write_text("codebook", encoding="utf-8")

    monkeypatch.setattr("training.slm_classifier.source_normalizer.RAW_DIR", raw_dir)
    monkeypatch.setattr("training.slm_classifier.source_normalizer.DEFAULT_SOURCE", tmp_path / "missing.csv")

    sources = discover_source_files()

    assert sources
    assert all(path.name != "GL-codebook.csv" for path in sources)
    assert any("Topics, Rules & Questions" in path.name for path in sources)


def test_normalized_csv_writes_age_band_as_text(tmp_path: Path) -> None:
    source_path = tmp_path / "school-learning.csv"
    target_path = tmp_path / "normalized.csv"
    _write_current_authoring_sheet(source_path)

    write_normalized_csv(source_path=source_path, target_path=target_path)

    with target_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows
    assert rows[0]["age_band"] == '="5-6"'
