from pathlib import Path


def test_duplicate_range_migration_extends_manual_decision_audit() -> None:
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "0040_image_selection_duplicate_range_decisions.py"
    )
    content = path.read_text(encoding="utf-8")

    assert "'selected_image', 'missing_image', 'duplicate_range'" in content
    assert "candidate_id IS NULL" in content
    assert "ck_image_selection_manual_decisions_resolution" in content
    assert "ck_image_selection_manual_decisions_candidate_resolution" in content
    assert 'down_revision: str | Sequence[str] | None = "0039_grid_calibration_profiles"' in content
