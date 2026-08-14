from pathlib import Path


def test_sequence_bounds_migration_is_reversible_and_updates_run_identities() -> None:
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "0043_image_selection_sequence_bounds.py"
    )
    content = path.read_text(encoding="utf-8")

    assert "last_sequence_number" in content
    assert "ck_image_selection_runs_sequence_bounds" in content
    assert "uq_image_selection_runs_full_identity" in content
    assert "uq_image_selection_runs_recovery_identity" in content
    assert (
        'down_revision: str | Sequence[str] | None = "0042_image_selection_derived_recovery"'
    ) in content
    assert 'op.drop_column("image_selection_runs", "last_sequence_number")' in content
