import csv
import json
from pathlib import Path

from training.slm_classifier.readiness import fix_staging_sources, promote_ready_sources, scan_staging_sources


def _write_valid_sheet(path: Path) -> None:
    flags = {
        "direct_intent": False,
        "has_ambiguous_risk": False,
        "has_bullying_involved": False,
        "has_coercive_control": False,
        "has_dangerous_context": False,
        "has_emotional_distress": False,
        "has_grooming_involved": False,
        "has_hate_group_language": False,
        "has_personal_direction": False,
        "has_safety_hazard": False,
        "has_self_harm": False,
        "has_unsafe_sexual_content": False,
        "has_violence_possibility": False,
        "has_vuln_exploit": False,
        "indirect_intent": False,
        "needs_clarification": False,
    }
    rows = [
        ["Topic", "Question", "G1", "G2", "G2_all", "Flags"],
        ["Science", "Why is the sky blue?", "SCIENCE", "NEUTRAL_FACT", '["NEUTRAL_FACT"]', json.dumps(flags, sort_keys=True)],
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def _write_invalid_sheet(path: Path) -> None:
    rows = [
        ["Topic", "Question", "G1", "Flags"],
        ["Science", "Why is the sky blue?", "SCIENCE", "{}"],
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def _write_fixable_sheet(path: Path) -> None:
    rows = [
        ["Topic", "Question", "G1", "G2", "G2_all", "Flags"],
        ["Safety", "Is this risky?", "SAFETY_HAZARD", "AMBIGUOUS_RISK", '["AMBIGUOUS_RISK"]', "{}"],
        ["Feelings", "I want to disappear", "DEATH_GRIEF", "EMOTIONAL", '["EMOTIONAL"]', '{"has_self_harm": true}'],
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def test_scan_staging_sources_writes_ready_and_blocked_assessments(tmp_path: Path, monkeypatch) -> None:
    staging_dir = tmp_path / "staging"
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    staging_dir.mkdir()
    raw_dir.mkdir()
    processed_dir.mkdir()
    valid = staging_dir / "valid.csv"
    invalid = staging_dir / "invalid.csv"
    _write_valid_sheet(valid)
    _write_invalid_sheet(invalid)

    monkeypatch.setattr("training.slm_classifier.readiness.READINESS_REPORT_PATH", processed_dir / "readiness.json")

    assessments = scan_staging_sources(staging_dir=staging_dir, raw_dir=raw_dir)

    assert len(assessments) == 2
    by_name = {Path(item.path).name: item for item in assessments}
    assert by_name["valid.csv"].ready is True
    assert by_name["invalid.csv"].ready is False
    payload = json.loads((processed_dir / "readiness.json").read_text(encoding="utf-8"))
    assert payload["ready_count"] == 1
    assert payload["blocked_count"] == 1


def test_promote_ready_sources_moves_only_ready_files(tmp_path: Path, monkeypatch) -> None:
    staging_dir = tmp_path / "staging"
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    staging_dir.mkdir()
    raw_dir.mkdir()
    processed_dir.mkdir()
    valid = staging_dir / "valid.csv"
    invalid = staging_dir / "invalid.csv"
    _write_valid_sheet(valid)
    _write_invalid_sheet(invalid)

    monkeypatch.setattr("training.slm_classifier.readiness.READINESS_REPORT_PATH", processed_dir / "readiness.json")

    promoted = promote_ready_sources(staging_dir=staging_dir, raw_dir=raw_dir)

    assert [path.name for path in promoted] == ["valid.csv"]
    assert (raw_dir / "valid.csv").exists()
    assert not valid.exists()
    assert invalid.exists()
    assert (staging_dir / "invalid.csv.checklist.json").exists()


def test_fix_staging_sources_rewrites_flags_and_g2_columns_in_place(tmp_path: Path, monkeypatch) -> None:
    staging_dir = tmp_path / "staging"
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    staging_dir.mkdir()
    raw_dir.mkdir()
    processed_dir.mkdir()
    fixable = staging_dir / "fixable.csv"
    _write_fixable_sheet(fixable)

    monkeypatch.setattr("training.slm_classifier.readiness.READINESS_REPORT_PATH", processed_dir / "readiness.json")

    assessments_before = scan_staging_sources(staging_dir=staging_dir, raw_dir=raw_dir)
    assert assessments_before[0].ready is False

    fixed = fix_staging_sources(staging_dir=staging_dir)
    assert [path.name for path in fixed] == ["fixable.csv"]

    with fixable.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    first_flags = json.loads(rows[0]["Flags"])
    second_flags = json.loads(rows[1]["Flags"])
    assert set(first_flags.keys()) == {
        "direct_intent",
        "has_ambiguous_risk",
        "has_bullying_involved",
        "has_coercive_control",
        "has_dangerous_context",
        "has_emotional_distress",
        "has_grooming_involved",
        "has_hate_group_language",
        "has_personal_direction",
        "has_safety_hazard",
        "has_self_harm",
        "has_unsafe_sexual_content",
        "has_violence_possibility",
        "has_vuln_exploit",
        "indirect_intent",
        "needs_clarification",
    }
    assert first_flags["has_ambiguous_risk"] is True
    assert all(value is False for key, value in first_flags.items() if key != "has_ambiguous_risk")
    assert rows[1]["G2"] == "SELF_HARM"
    assert rows[1]["G2_all"] == '["EMOTIONAL", "SELF_HARM"]'
    assert second_flags["has_emotional_distress"] is True
    assert second_flags["has_self_harm"] is True
    assert all(
        value is False
        for key, value in second_flags.items()
        if key not in {"has_emotional_distress", "has_self_harm"}
    )

    assessments_after = scan_staging_sources(staging_dir=staging_dir, raw_dir=raw_dir)
    assert assessments_after[0].ready is True
