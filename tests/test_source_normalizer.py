from training.slm_classifier.source_normalizer import CANONICAL_COLUMNS, discover_source_files, expand_authoring_rows


def test_source_normalizer_expands_authoring_sheet_into_canonical_rows() -> None:
    source_path = discover_source_files()[0]
    rows = expand_authoring_rows(source_path)

    assert rows
    assert set(CANONICAL_COLUMNS).issubset(rows[0].keys())
    assert rows[0]["age_band"] == "5-8"
    assert rows[1]["age_band"] == "9-12"
    assert rows[2]["age_band"] == "13-17"
    assert rows[0]["gl_01"] == 1


def test_source_normalizer_infers_missing_guideline_tags_from_gates() -> None:
    source_path = discover_source_files()[0]
    rows = expand_authoring_rows(source_path)

    assert all(row["guideline_tags"] for row in rows[:50])
    assert all(any(row[column] == 1 for column in CANONICAL_COLUMNS if column.startswith("gl_")) for row in rows[:50])
