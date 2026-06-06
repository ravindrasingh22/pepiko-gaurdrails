import csv
import json
from pathlib import Path

from training.slm_classifier.data_pipeline import DATASET_SPLITS_PATH, LABEL_VOCAB_PATH, build_dataset_splits, build_group_id, load_jsonl_rows, validate_dataset_rows
from training.slm_classifier.source_normalizer import CANONICAL_COLUMNS, discover_source_files, expand_authoring_rows, write_canonical_jsonl_with_metadata, write_normalized_csv


def _write_current_authoring_sheet(path: Path) -> None:
    rows = [
        ["input_text", "G1_LOV_ID", "G2_LOV_ID", "FLAGS"],
        ["Should I tell my sports teacher that I did not finish library book?", "GENERIC", "PD", ""],
        ["How does unit test help me learn?", "FACT", "NEUTRAL_FACT", ""],
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
    assert len(rows) == 2
    assert rows[0]["g2"] == ["PERSONAL_DIRECTION"]
    assert "what should I do" in rows[0]["intent_phrases"]
    assert rows[0]["intent_phrases_present"] is True
    assert "guideline_tags" not in rows[0]
    assert "g3" not in rows[0]
    assert "g4" not in rows[0]


def test_source_normalizer_accepts_training_column_aliases(tmp_path: Path) -> None:
    source_path = tmp_path / "training-aliases.csv"
    rows = [
        ["Topic", "input_text", "G1_LOV_ID", "G2_LOV_ID", "FLAGS"],
        ["Science", "Why is the sky blue?", "SCIENCE", "NEUTRAL_FACT", "{}"],
    ]
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)

    parsed = expand_authoring_rows(source_path)

    assert len(parsed) == 1
    assert parsed[0]["question"] == "Why is the sky blue?"
    assert parsed[0]["g1"] == "SCIENCE"
    assert parsed[0]["g2"] == ["NEUTRAL_FACT"]


def test_source_normalizer_parses_exported_flags_without_deriving_g2(tmp_path: Path) -> None:
    source_path = tmp_path / "training-flags.csv"
    rows = [
        ["input_text", "G1_LOV_ID", "G2_LOV_ID", "FLAGS"],
        ["I feel unsafe", "GENERIC", "EMOTIONAL", "has_personal_direction=true;has_self_harm=true"],
    ]
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)

    parsed = expand_authoring_rows(source_path)

    assert parsed[0]["g2"] == ["EMOTIONAL"]
    assert parsed[0]["flags"]["has_self_harm"] is True
    assert "has_personal_direction" not in parsed[0]["flags"]


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


def test_normalized_csv_omits_age_band_column(tmp_path: Path) -> None:
    source_path = tmp_path / "school-learning.csv"
    target_path = tmp_path / "normalized.csv"
    _write_current_authoring_sheet(source_path)

    write_normalized_csv(source_path=source_path, target_path=target_path)

    with target_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows
    assert "age_band" not in rows[0]
    assert "g3" not in rows[0]
    assert "g4" not in rows[0]

def test_dataset_split_groups_keep_question_rows_stable(tmp_path: Path) -> None:
    source_path = tmp_path / "school-learning.csv"
    _write_current_authoring_sheet(source_path)
    rows = expand_authoring_rows(source_path)

    split_manifest = build_dataset_splits(rows)
    all_groups = set(split_manifest.train_ids) | set(split_manifest.test_ids)

    question_groups = {}
    for row in rows:
        key = row["question"]
        question_groups.setdefault(key, set()).add(build_group_id(row))
    assert split_manifest.train_ids
    assert all_groups
    assert all(len(group_ids) == 1 for group_ids in question_groups.values())


def test_canonical_jsonl_writes_split_and_vocab_metadata(tmp_path: Path) -> None:
    source_path = tmp_path / "school-learning.csv"
    target_jsonl = tmp_path / "canonical.jsonl"
    split_path = tmp_path / "splits.json"
    vocab_path = tmp_path / "label_vocab.json"
    _write_current_authoring_sheet(source_path)

    write_canonical_jsonl_with_metadata(
        source_path=source_path,
        target_path=target_jsonl,
        split_target_path=split_path,
        vocab_target_path=vocab_path,
    )

    assert target_jsonl.exists()
    assert split_path.exists()
    assert vocab_path.exists()
    splits = json.loads(split_path.read_text(encoding="utf-8"))
    vocab = json.loads(vocab_path.read_text(encoding="utf-8"))
    assert "train_ids" in splits
    assert "flags" in vocab
    assert "intent_families" in vocab
    assert "intent_phrases" in vocab
    assert "gl_columns" not in vocab


def test_canonical_jsonl_omits_legacy_gl_authoring_columns(tmp_path: Path) -> None:
    source_path = tmp_path / "school-learning.csv"
    target_jsonl = tmp_path / "canonical.jsonl"
    _write_current_authoring_sheet(source_path)

    write_canonical_jsonl_with_metadata(
        source_path=source_path,
        target_path=target_jsonl,
    )

    rows = [
        json.loads(line)
        for line in target_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert rows
    assert "topic" not in rows[0]
    assert "guideline_tags" not in rows[0]
    assert "g3" not in rows[0]
    assert "g4" not in rows[0]


def test_default_canonical_dataset_is_written_as_jsonl_shards(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "school-learning.csv"
    target_dir = tmp_path / "canonical-shards"
    _write_current_authoring_sheet(source_path)
    monkeypatch.setattr("training.slm_classifier.source_normalizer.CANONICAL_DATASET", target_dir)
    monkeypatch.setattr("training.slm_classifier.source_normalizer.CANONICAL_SHARD_ROWS", 1)

    write_canonical_jsonl_with_metadata(source_path=source_path, target_path=target_dir)

    assert [path.name for path in sorted(target_dir.glob("part-*.jsonl"))] == ["part-000.jsonl", "part-001.jsonl"]
    assert len(load_jsonl_rows(target_dir)) == 2


def test_dataset_validation_does_not_require_g2_all() -> None:
    rows = [
        {
            "sample_id": "row-1",
            "question": "Why is the sky blue?",
            "context": "",
            "topic": "Science",
            "g1": "SCIENCE",
            "g2": ["NEUTRAL_FACT"],
            "intent_families": [],
            "intent_phrases": [],
        }
    ]

    validate_dataset_rows(rows)


def test_source_normalizer_uses_first_g2_label_when_g2_cell_contains_json_array(tmp_path: Path) -> None:
    source_path = tmp_path / "multi-g2.csv"
    rows = [
        ["Topic", "Question", "G1", "G2", "G2_all"],
        ["Feelings", "Kids are being mean to me", "GENERIC", '["EMOTIONAL", "BULLYING"]', '["EMOTIONAL", "BULLYING"]'],
    ]
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)

    parsed = expand_authoring_rows(source_path)

    assert len(parsed) == 1
    assert parsed[0]["g2"] == ["EMOTIONAL"]


def test_source_normalizer_uses_first_g2_label_when_g2_cell_contains_python_list_string(tmp_path: Path) -> None:
    source_path = tmp_path / "multi-g2-python-list.csv"
    rows = [
        ["Topic", "Question", "G1", "G2", "G2_all"],
        ["Feelings", "Kids are being mean to me", "GENERIC", "['BULLYING', 'EMOTIONAL']", "['BULLYING', 'EMOTIONAL']"],
    ]
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)

    parsed = expand_authoring_rows(source_path)

    assert len(parsed) == 1
    assert parsed[0]["g2"] == ["BULLYING"]


def test_source_normalizer_accepts_python_dict_string_for_flags(tmp_path: Path) -> None:
    source_path = tmp_path / "flags-python-dict.csv"
    rows = [
        ["Topic", "Question", "G1", "G2", "Flags"],
        ["Feelings", "Kids are being mean to me", "GENERIC", "BULLYING", "{'has_bullying_involved': True, 'has_emotional_distress': False}"],
    ]
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)

    parsed = expand_authoring_rows(source_path)

    assert len(parsed) == 1
    assert parsed[0]["flags"]["has_bullying_involved"] is True
    assert parsed[0]["flags"]["has_emotional_distress"] is False


def test_canonical_normalization_does_not_derive_g2_or_flags(tmp_path: Path) -> None:
    source_path = tmp_path / "consistency.csv"
    target_jsonl = tmp_path / "canonical.jsonl"
    rows = [
        ["Topic", "Question", "G1", "G2", "Flags"],
        ["Feelings", "Kids are being mean to me", "GENERIC", "BULLYING", "{}"],
        ["Feelings", "I want to disappear", "GENERIC", "EMOTIONAL", '{"has_self_harm": true}'],
    ]
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)

    write_canonical_jsonl_with_metadata(
        source_path=source_path,
        target_path=target_jsonl,
    )

    parsed = [
        json.loads(line)
        for line in target_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert parsed[0]["g2"] == ["BULLYING"]
    assert parsed[0]["flags"]["has_bullying_involved"] is False
    assert parsed[1]["g2"] == ["EMOTIONAL"]
    assert parsed[1]["flags"]["has_self_harm"] is True
    assert parsed[1]["flags"]["has_emotional_distress"] is False


def test_source_normalizer_uses_first_g2_label_when_g2_cell_contains_semicolon_list(tmp_path: Path) -> None:
    source_path = tmp_path / "multi-g2-semicolon.csv"
    rows = [
        ["Topic", "Question", "G1", "G2", "G2_all"],
        ["Feelings", "I feel unsafe and very sad", "GENERIC", "SELF_HARM;EMOTIONAL", "SELF_HARM;EMOTIONAL"],
    ]
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)

    parsed = expand_authoring_rows(source_path)

    assert len(parsed) == 1
    assert parsed[0]["g2"] == ["SELF_HARM"]
