from pathlib import Path


def test_grid_profile_gate_revision_migration_preserves_immutable_profile_history() -> None:
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "0094_grid_profile_gate_revisions.py"
    )
    content = path.read_text(encoding="utf-8")

    assert 'down_revision: str | Sequence[str] | None = "0093_board_source_cleanup"' in content
    assert '"uq_grid_calibration_profiles_cohort"' in content
    assert '"uq_grid_calibration_profiles_cohort_checksum"' in content
    assert '["cohort_id", "profile_checksum_sha256"]' in content
